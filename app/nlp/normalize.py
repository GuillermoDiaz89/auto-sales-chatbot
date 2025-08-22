# app/nlp/normalize.py
from __future__ import annotations
import re
from typing import List, Optional, Tuple, Dict
from unidecode import unidecode

# Alias centralizados (NO importan de tools.py para evitar ciclos)
from app.nlp.aliases import BRAND_ALIAS, MODEL_ALIAS, STOPWORDS

# RapidFuzz es opcional: si no está, hacemos fallback básico
try:
    from rapidfuzz import process, fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    _HAS_RAPIDFUZZ = False


# -----------------------------------------------------------------------------
# Normalización básica
# -----------------------------------------------------------------------------
def norm_txt(s: str) -> str:
    """
    Normaliza texto: quita acentos, baja a minúsculas, colapsa espacios.
    """
    s = unidecode(s or "")
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def normalize_text(s: str) -> str:
    """
    Alias semántico por si en el futuro quieres cambiar la normalización.
    """
    return norm_txt(s)


# -----------------------------------------------------------------------------
# Parsing numérico / monetario
# -----------------------------------------------------------------------------
_NUM_TOKEN = r"(?:\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)"  # 300,000 | 300.000 | 300 | 300.5
_MULT_TOKEN = r"(k|mil|mil pesos|m|millones)?"

def parse_numeric(s: str):
    """
    Mantiene tu firma original. Parsea un número simple, removiendo $ y comas.
    """
    if s is None:
        return None
    s = s.replace(",", "").replace("$", "").strip()
    try:
        return float(s)
    except:
        return None


def _apply_multiplier(value: float, mult: Optional[str]) -> float:
    if not mult:
        return value
    mult = (mult or "").strip().lower()
    if mult in {"k", "mil", "mil pesos"}:
        return value * 1_000.0
    if mult in {"m", "millones"}:
        return value * 1_000_000.0
    return value


def parse_money_token(token: str) -> Optional[float]:
    """
    Parsea un token monetario suelto:
      "300k", "300 k", "300 mil", "300 mil pesos", "$300,000", "300.000"
    Devuelve float (pesos) o None.
    """
    if not token:
        return None
    t = norm_txt(token).replace("$", "").strip()
    # Junta "300 k" -> "300k"
    t = re.sub(r"(\d)\s+([km])\b", r"\1\2", t)

    m = re.search(rf"^({_NUM_TOKEN})\s*{_MULT_TOKEN}$", t)
    if not m:
        return None

    raw, mult = m.group(1), m.group(2)
    # normaliza separadores
    raw = raw.replace(",", "")
    # caso "300.000.000"
    if raw.count(".") > 1 and raw.count(",") == 0:
        raw = raw.replace(".", "")
    # "300.000" -> 300000 (miles europeo)
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        raw = raw.replace(".", "")

    try:
        val = float(raw)
    except ValueError:
        return None

    return _apply_multiplier(val, mult)


def parse_price_hint(text: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Extrae (min_price, max_price) desde texto:
      - "menos de 300 mil", "hasta 350k", "tope 280 mil"
      - "más de 200 mil", "desde 150k"
      - "entre 250 y 300 mil"
      - "$300,000", "300k", "300 mil"
    Si no infiere nada, retorna (None, None).
    """
    if not text:
        return None, None
    t = norm_txt(text)

    # Rango "entre X y Y"
    m = re.search(rf"entre\s+({_NUM_TOKEN}\s*{_MULT_TOKEN})\s+y\s+({_NUM_TOKEN}\s*{_MULT_TOKEN})", t)
    if m:
        v1 = parse_money_token(m.group(1))
        v2 = parse_money_token(m.group(2))
        if v1 is not None and v2 is not None:
            return (min(v1, v2), max(v1, v2))

    # Máximo
    m = re.search(rf"(menos de|hasta|tope(?: m[aá]ximo)?)\s+({_NUM_TOKEN}\s*{_MULT_TOKEN})", t)
    if m:
        v = parse_money_token(m.group(2))
        if v is not None:
            return (None, v)

    # Mínimo
    m = re.search(rf"(m[aá]s de|desde|mayor a)\s+({_NUM_TOKEN}\s*{_MULT_TOKEN})", t)
    if m:
        v = parse_money_token(m.group(2))
        if v is not None:
            return (v, None)

    # Cantidad suelta → tratar como máximo por defecto
    m = re.search(rf"({_NUM_TOKEN}\s*{_MULT_TOKEN})", t)
    if m:
        v = parse_money_token(m.group(1))
        if v is not None:
            return (None, v)

    return None, None


# -----------------------------------------------------------------------------
# Fuzzy matching helpers
# -----------------------------------------------------------------------------
def _rf_extract_one(query_norm: str, candidates: List[str], score_cutoff: int, scorer) -> Optional[int]:
    """
    RapidFuzz extractOne pero devolviendo el índice del candidato original.
    Trabaja con candidatos ya normalizados en paralelo.
    """
    norm_candidates = [normalize_text(c) for c in candidates]
    result = process.extractOne(query_norm, norm_candidates, scorer=scorer, score_cutoff=score_cutoff)
    if not result:
        return None
    # result = (matched_string, score, index)
    return result[2]


def fuzzy_pick(query: Optional[str], candidates: List[str], score_cutoff: int = 80) -> Optional[str]:
    """
    Devuelve el candidato original que mejor coincide con 'query' si supera el umbral.
    Si RapidFuzz no está disponible, usa un contains básico.
    """
    if not query or not candidates:
        return None
    qn = normalize_text(query)

    if _HAS_RAPIDFUZZ:
        idx = _rf_extract_one(qn, candidates, score_cutoff=score_cutoff, scorer=fuzz.WRatio)
        if idx is None:
            return None
        return candidates[idx]
    else:
        # Fallback simple
        for i, c in enumerate(candidates):
            if qn in normalize_text(c):
                return c
        return None


# -----------------------------------------------------------------------------
# Canonicalización de marca (alias + fuzzy)
# -----------------------------------------------------------------------------
def canonicalize_brand(text_or_brand: Optional[str], brand_list: List[str]) -> Optional[str]:
    """
    Resuelve marca canónica:
      1) Alias por token (vw->volkswagen, nisan->nissan, chevy->chevrolet) con mapeo a la forma original de brand_list.
      2) Fuzzy por tokens individuales (umbral 70).
      3) Fuzzy sobre la oración completa (umbral 70).
    Siempre devuelve la forma ORIGINAL existente en brand_list.
    """
    if not text_or_brand or not brand_list:
        return None

    # Mapa normalizado -> original (p.ej. "volkswagen" -> "Volkswagen")
    norm2orig = {normalize_text(b): b for b in brand_list}

    n = norm_txt(text_or_brand)
    tokens = [t for t in re.split(r"[^a-z0-9]+", n) if t and t not in STOPWORDS]

    # 1) Alias directos por token -> mapea a forma original
    for tok in tokens:
        alias_tok = BRAND_ALIAS.get(tok)  # p.ej. "vw" -> "volkswagen"
        if alias_tok:
            orig = norm2orig.get(normalize_text(alias_tok))
            if orig:
                return orig

    # 2) Fuzzy por token (devuelve original gracias a candidates=brand_list)
    for tok in tokens:
        m = fuzzy_pick(tok, brand_list, score_cutoff=70)
        if m:
            return m

    # 3) Fuzzy por la oración completa
    m = fuzzy_pick(text_or_brand, brand_list, score_cutoff=70)
    if m:
        return m

    return None


# -----------------------------------------------------------------------------
# Extracción de preferencias desde texto libre
# -----------------------------------------------------------------------------
def extract_preferences(
    text: str,
    brand_list: Optional[List[str]] = None,
    model_list_by_brand: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Optional[str]]:
    """
    Extrae preferencias del usuario desde texto:
      - brand (alias + fuzzy)
      - model (alias + fuzzy dentro de la marca)
      - min_price, max_price
      - year (>= 1990)
    Retorna:
    {
        "brand": None,  # reservado por si luego capturas literal
        "brand_canonical": "Nissan" | None,
        "model": None,
        "model_canonical": "Sentra" | None,
        "min_price": float|None,
        "max_price": float|None,
        "year": int|None
    }
    """
    out: Dict[str, Optional[str]] = {
        "brand": None,
        "brand_canonical": None,
        "model": None,
        "model_canonical": None,
        "min_price": None,
        "max_price": None,
        "year": None,
    }

    t = text or ""

    # 1) Marca
    brand_final = None
    if brand_list:
        brand_final = canonicalize_brand(t, brand_list)
    out["brand_canonical"] = brand_final

    # 2) Modelo (si hay marca concreta y diccionario)
    model_final = None
    if model_list_by_brand and brand_final:
        models = model_list_by_brand.get(brand_final, [])
        if models:
            # 2a) Alias por tokens (xtrail -> x-trail, corola -> corolla, etc.)
            tokens = [tok for tok in re.split(r"[^a-z0-9]+", norm_txt(t)) if tok and tok not in STOPWORDS]
            norm_models = [norm_txt(m) for m in models]

            for tok in tokens:
                alias_tok = MODEL_ALIAS.get(tok)
                if alias_tok and alias_tok in norm_models:
                    # devuelve el original que coincide con el alias normalizado
                    for m in models:
                        if norm_txt(m) == alias_tok:
                            model_final = m
                            break
                    if model_final:
                        break

            # 2b) Fuzzy tolerante si no hubo alias
            if not model_final:
                model_final = fuzzy_pick(t, models, score_cutoff=72)

    out["model"] = model_final or None
    out["model_canonical"] = model_final or None

    # 3) Precio (min/max)
    min_p, max_p = parse_price_hint(t)
    out["min_price"] = min_p
    out["max_price"] = max_p

    # 4) Año explícito (heurística)
    m_year = re.search(r"\b(19[9]\d|20[0-4]\d)\b", t)  # 1990–2049
    if m_year:
        try:
            out["year"] = int(m_year.group(1))
        except Exception:
            out["year"] = None

    return out


# -----------------------------------------------------------------------------
# Normalización de catálogo (DataFrame)
# -----------------------------------------------------------------------------
def normalize_catalog_df(df, brand_col: str = "brand", model_col: str = "model"):
    """
    Añade columnas normalizadas (brand_norm, model_norm) al DataFrame del catálogo.
    No fuerza tipos adicionales ni columnas extra; solo agrega las _norm.
    """
    if brand_col in df.columns:
        df["brand_norm"] = df[brand_col].astype(str).map(normalize_text)
    if model_col in df.columns:
        df["model_norm"] = df[model_col].astype(str).map(normalize_text)
    return df
