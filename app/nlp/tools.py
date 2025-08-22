# app/nlp/tools.py
from __future__ import annotations
import os
from typing import Dict, Any, List, Tuple

import pandas as pd
from rapidfuzz import process, fuzz, distance

# Importamos la tasa fija definida por Kavak
from app.settings import KAVAK_ANNUAL_RATE, ALLOWED_TERMS, DEFAULT_TERM

# Usamos el normalizer de nuestro motor
from app.nlp.normalize import norm_txt

# app/nlp/tools.py
from app.nlp.aliases import BRAND_ALIAS, MODEL_ALIAS, VERSION_ALIAS, STOPWORDS

# ------------------------------------------------------------
# Rutas y carga de catálogo
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
CATALOG_PATH = os.getenv("CATALOG_PATH") or os.path.join(DATA_DIR, "catalog.csv")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 1) Nombres de columnas normalizados
    df.columns = [str(c).strip().lower() for c in df.columns]

    # 2) Mapeo de sinónimos -> esquema esperado
    synonyms = {
        "id":       ["id", "stock_id", "stockid", "car_id", "codigo"],
        "brand":    ["brand", "make", "marca"],
        "model":    ["model", "modelo"],
        "year":     ["year", "anio", "año"],
        "km":       ["km", "kilometraje", "mileage", "odometer"],
        "price":    ["price", "precio", "amount", "cost"],
        "location": ["location", "ubicacion", "ciudad", "sede", "source"],
        "version":  ["version", "versión", "trim", "variant"],
    }
    rename = {}
    for target, alts in synonyms.items():
        for col in df.columns:
            if col in alts and col != target:
                rename[col] = target
    if rename:
        df = df.rename(columns=rename)

    # 3) Columnas requeridas y default de location
    if "location" not in df.columns:
        df["location"] = "Online"

    if "version" not in df.columns:
        df["version"] = ""  # opcional si el CSV no trae versión    

    required = ["id", "brand", "model", "year", "km", "price", "location"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in catalog.csv (after mapping): {missing}")

    # 4) Tipos (tolerante a errores)
    df["year"]  = pd.to_numeric(df["year"],  errors="coerce").astype("Int64")
    df["km"]    = pd.to_numeric(df["km"],    errors="coerce").fillna(0).astype(int)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)

    # 5) Auxiliares normalizados para fuzzy (usa tu norm_txt)
    #    astype(str) + fillna evita problemas si vienen NaN
    df["brand"] = df["brand"].astype(str).fillna("")
    df["model"] = df["model"].astype(str).fillna("")
    df["version"]  = df["version"].astype(str).fillna("")
    df["_brand_n"] = df["brand"].map(norm_txt)
    df["_model_n"] = df["model"].map(norm_txt)
    df["_version_n"] = df["version"].map(norm_txt) 

    return df


def _load_catalog() -> pd.DataFrame:
    if not os.path.exists(CATALOG_PATH):
        raise FileNotFoundError(
            f"catalog.csv not found at {os.path.abspath(CATALOG_PATH)}. "
            f"Set CATALOG_PATH env var or place the file in app/data/catalog.csv"
        )
    try:
        df = pd.read_csv(CATALOG_PATH)           # CSV con coma
    except Exception:
        df = pd.read_csv(CATALOG_PATH, sep=";")  # fallback si viene con ';'
    df = _normalize_columns(df)                  # SIEMPRE normalizar aquí
    return df


# ------------------------------------------------------------
# Fuzzy matching: marca/modelo tolerantes a typos
# ------------------------------------------------------------
def fuzzy_best(q: str | None, choices: List[str], score_cutoff: int = 85) -> Tuple[str | None, int]:
    if not q:
        return None, 0
    m = process.extractOne(q, choices, scorer=fuzz.token_set_ratio, score_cutoff=score_cutoff)
    return (m[0], m[1]) if m else (None, 0)


def _map_alias(s: str | None) -> str | None:
    if not s:
        return s
    return BRAND_ALIAS.get(s, s)


def _guess_brand(raw_text: str, brands: List[str]) -> str | None:
    """
    Inferencia robusta de marca:
    - Alias por token (vw->volkswagen, nizzan->nissan, etc.)
    - Luego WRatio / token_set_ratio sobre la frase
    - Última red: token por token con Levenshtein
    """
    t_full = norm_txt(raw_text)

    # 1) Alias por token: si algún token mapea directo a una marca del catálogo, úsalo
    tokens = [tok for tok in t_full.split() if len(tok) >= 3 and tok not in STOPWORDS]
    for tok in tokens:
        alias_tok = _map_alias(tok)  # <-- alias por token
        if alias_tok in brands:
            return alias_tok

    # 2) Matching sobre la frase completa (sin alias)
    m = process.extractOne(t_full, brands, scorer=fuzz.WRatio, score_cutoff=90)
    if m:
        return m[0]

    m = process.extractOne(t_full, brands, scorer=fuzz.token_set_ratio, score_cutoff=88)
    if m:
        return m[0]

    # 3) Última red: token por token con Levenshtein
    for tok in tokens:
        best = process.extractOne(tok, brands, scorer=fuzz.partial_ratio)
        if best:
            cand = best[0]
            if distance.Levenshtein.normalized_similarity(tok, cand) >= 0.80:
                return cand
    return None


def _guess_model(raw_text: str, candidate_models: List[str]) -> str | None:
    """
    Inferencia robusta de modelo (tolerante a typos) con 3 niveles:
    1) Alias por token (kix->kicks, xtrail->x-trail, corola->corolla, etc.)
    2) Matching de la frase completa (WRatio / token_set_ratio)
    3) Última red: token por token con Levenshtein
    """
    t_full = norm_txt(raw_text)
    tokens = [tok for tok in t_full.split() if len(tok) >= 3 and tok not in STOPWORDS]

    # 1) Alias por token → match directo si coincide con algún modelo del catálogo
    for tok in tokens:
        alias_tok = MODEL_ALIAS.get(tok, tok)
        if alias_tok in candidate_models:
            return alias_tok

    # 2) Matching de la frase completa
    m = process.extractOne(t_full, candidate_models, scorer=fuzz.WRatio, score_cutoff=88)
    if m:
        return m[0]
    m = process.extractOne(t_full, candidate_models, scorer=fuzz.token_set_ratio, score_cutoff=86)
    if m:
        return m[0]

    # 3) Última red: token por token con Levenshtein
    for tok in tokens:
        best = process.extractOne(tok, candidate_models, scorer=fuzz.partial_ratio)
        if best:
            cand = best[0]
            if distance.Levenshtein.normalized_similarity(tok, cand) >= 0.78:
                return cand
    return None


# ------------------------------------------------------------
# Búsqueda principal en catálogo
# ------------------------------------------------------------
# ------------------------------------------------------------
# Filtro común (devuelve el DataFrame filtrado y ordenado)
# ------------------------------------------------------------
def _filtered_df_for_search(filters: Dict[str, Any]) -> pd.DataFrame:
    df = _load_catalog().copy()
    if df.empty:
        return df

    # -------- Filtros de entrada --------
    brand_q   = norm_txt(filters.get("brand"))
    model_q   = norm_txt(filters.get("model"))
    version_q = norm_txt(filters.get("version"))
    price_max = filters.get("price_max")
    price_min = filters.get("price_min")
    km_max    = filters.get("km_max")
    year_min  = filters.get("year_min")
    raw_text  = norm_txt(filters.get("raw_text") or "")

    # -------- Vocabularios --------
    brands = df["_brand_n"].dropna().unique().tolist()
    models = df["_model_n"].dropna().unique().tolist()
    all_versions = df["_version_n"].dropna().unique().tolist() if "_version_n" in df.columns else []

    # -------- Inferencia de marca/modelo/version con locks --------
    brand_lock = None
    model_lock = None
    version_lock = None

    # Determina candidatos de versión según el subconjunto actual del DF
    if "_version_n" in df.columns:
        candidate_versions = df["_version_n"].dropna().unique().tolist()
    else:
        candidate_versions = []

    if version_q:
        vq = VERSION_ALIAS.get(version_q, version_q)
        best_ver, score_v = fuzzy_best(vq, candidate_versions, score_cutoff=85)
        if best_ver:
            version_q = best_ver
            version_lock = best_ver
    else:
        # Inferencia desde texto libre (tokens)
        if raw_text:
            for tok in raw_text.split():
                tok = tok.strip()
                if tok in VERSION_ALIAS:
                    vq = VERSION_ALIAS[tok]
                    best_ver, score_v = fuzzy_best(vq, candidate_versions, score_cutoff=80)
                    if best_ver:
                        version_lock = best_ver
                        break

    # Aplica versión si se bloqueó
    if version_lock and "_version_n" in df.columns:
        df = df[df["_version_n"] == version_lock]

    # Marca
    if not brand_q and raw_text:
        gb = _guess_brand(raw_text, brands)
        if gb:
            brand_q = gb
            brand_lock = gb
            df = df[df["_brand_n"] == gb]
    else:
        if brand_q:
            best_brand, score_b = fuzzy_best(brand_q, brands, score_cutoff=86)
            if best_brand:
                brand_q = best_brand
                brand_lock = best_brand
                df = df[df["_brand_n"] == best_brand]
            else:
                brand_q = None

    # Modelos candidatos (si hay marca bloqueada, solo de esa marca)
    candidate_models = df["_model_n"].dropna().unique().tolist() if brand_lock else models

    # Candidatos de versión (si hay modelo bloqueado, tomamos solo sus versiones)
    if model_lock:
        candidate_versions = (
            df.loc[df["_model_n"] == model_lock, "_version_n"]
            .dropna().unique().tolist()
        )
    else:
        candidate_versions = df["_version_n"].dropna().unique().tolist()

    # Modelo
    if not model_q and raw_text:
        gm = _guess_model(raw_text, candidate_models)
        if gm:
            model_q = gm
            model_lock = gm
    elif model_q:
        best_model, score_m = fuzzy_best(norm_txt(model_q), candidate_models, score_cutoff=85)
        if best_model:
            model_q = best_model
            model_lock = best_model
        else:
            model_q = None

    # Aplica modelo si está bloqueado
    if model_lock:
        df = df[df["_model_n"] == model_lock]

    # Salvaguarda final de marca (evita mezclar)
    if brand_lock is not None and not df.empty:
        df = df[df["_brand_n"] == brand_lock]

    # -------- Filtros numéricos --------
    if price_min is not None:
        try:
            df = df[df["price"] >= float(price_min)]
        except Exception:
            pass

    if price_max is not None:
        try:
            df = df[df["price"] <= float(price_max)]
        except Exception:
            pass

    if year_min is not None:
        try:
            df = df[df["year"] >= int(year_min)]
        except Exception:
            pass

    if km_max is not None:
        try:
            df = df[df["km"] <= int(km_max)]
        except Exception:
            pass

    if df.empty:
        return df

    # -------- Ordenamiento --------
    if year_min is not None:
        try:
            df["_year_diff"] = (df["year"] - int(year_min)).abs()
            df = df.sort_values(by=["_year_diff", "km", "price"], ascending=[True, True, True])
            df = df.drop(columns=["_year_diff"])
        except Exception:
            df = df.sort_values(by=["km", "year", "price"], ascending=[True, False, True])
    else:
        df = df.sort_values(by=["km", "year", "price"], ascending=[True, False, True])

    return df


# ------------------------------------------------------------
# Búsqueda principal (top-N) con offset para paginación
# ------------------------------------------------------------
def search_cars(filters: Dict[str, Any], limit: int = 5, offset: int = 0) -> List[Dict[str, Any]]:
    df = _filtered_df_for_search(filters)
    if df.empty:
        return []
    cols = ["id", "brand", "model", "year", "km", "price", "location"]
    if "version" in df.columns:
        cols.insert(3, "version")  
    page = df[cols].iloc[offset: offset + limit]
    return page.to_dict(orient="records")


# ------------------------------------------------------------
# Conteo total (para "5 de N, +K más")
# ------------------------------------------------------------
def search_cars_count(filters: Dict[str, Any]) -> int:
    df = _filtered_df_for_search(filters)
    return int(len(df))


# ------------------------------------------------------------
# Finanzas: pago mensual (amortización francesa)
# ------------------------------------------------------------
def monthly_payment(price: float, down_payment: float, term: int, annual_rate: float | None = None) -> float:
    """
    Pago mensual con amortización francesa.
    - Si no pasas annual_rate, usa KAVAK_ANNUAL_RATE de settings.
    
    - price: precio total del auto
    - down_payment: enganche
    - term: meses (int)
    - annual_rate: tasa anual en decimal (0.12 = 12%)
    """
    principal = max(float(price) - float(down_payment), 0.0)
    n = int(term)
    rate = KAVAK_ANNUAL_RATE if (annual_rate is None) else float(annual_rate)
    if n <= 0 or principal <= 0:
        return 0.0
    r = rate / 12.0
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


# ------------------------------------------------------------
# Finanzas: cálculo de mensualidades (amortización francesa)
# ------------------------------------------------------------
def finance_plan(price: float, down_payment: float, terms: tuple | list | None = None, annual_rate: float | None = None) -> dict:
    """
    Calcula mensualidades para varios plazos.
    - Si no pasas terms, usa ALLOWED_TERMS de settings.
    - Si no pasas annual_rate, usa KAVAK_ANNUAL_RATE de settings.
    """
    plan_terms = tuple(terms) if terms is not None else tuple(ALLOWED_TERMS)
    rate = KAVAK_ANNUAL_RATE if (annual_rate is None) else float(annual_rate)

    plans = []
    for term in plan_terms:
        m = monthly_payment(price=price, down_payment=down_payment, term=int(term), annual_rate=rate)
        plans.append({"term_months": int(term), "monthly": float(m)})
    return {"plans": plans}


# ------------------------------------------------------------
# Cotización por ID + enganche (usa la tasa estándar si no se especifica)
# ------------------------------------------------------------
def cotiza_car(car_id: str, down_payment: float, term: int | None = None, annual_rate: float | None = None) -> str:
    """
    Cotiza por ID + enganche:
    - term por defecto viene de DEFAULT_TERM (settings)
    - tasa por defecto viene de KAVAK_ANNUAL_RATE (settings)
    """
    df = _load_catalog()
    car = df[df["id"].astype(str) == str(car_id)]
    if car.empty:
        return f"No encontré el auto con ID {car_id}."

    brand = str(car["brand"].iloc[0])
    model = str(car["model"].iloc[0])
    year  = int(car["year"].iloc[0])
    price = float(car["price"].iloc[0])

    rate = KAVAK_ANNUAL_RATE if (annual_rate is None) else float(annual_rate)
    n = int(term if term is not None else DEFAULT_TERM)

    principal = max(price - float(down_payment), 0.0)
    r = rate / 12.0
    if n <= 0 or principal <= 0 or r <= 0:
        monthly = principal / n if n > 0 else 0.0
    else:
        monthly = principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

    return (
        f"*Cotización #{car_id}*\n"
        f"{brand} {model} {year}\n"
        f"Precio: ${price:,.0f} • Enganche: ${float(down_payment):,.0f}\n"
        f"Plazo: {n} meses • Tasa anual: {rate*100:.1f}%\n"
        f"*Mensualidad aprox:* ${monthly:,.0f}\n\n"
        f"¿Te comparto el detalle y requisitos?"
    )


# ------------------------------------------------------------
# KB / RAG: wrapper seguro (opcional, si usas retriever)
# ------------------------------------------------------------
def kb_tool(question: str) -> str:
    """
    Llama al retriever si está disponible. Si no, responde de forma segura.
    """
    try:
        from .retriever import kb_answer  # evita import circular
    except Exception:
        return "La base de conocimiento no está disponible por ahora."

    try:
        res = kb_answer(question)
        if isinstance(res, dict):
            answer = res.get("answer") or res.get("reply") or ""
            srcs = res.get("sources") or []
            suffix = ""
            if srcs:
                suffix = "\n\nFuentes:\n" + "\n".join(f"- {s}" for s in srcs)
            return (answer or "No encontré información en la base de conocimiento.") + suffix
        return str(res)
    except Exception:
        return "No pude consultar la base de conocimiento en este momento."
