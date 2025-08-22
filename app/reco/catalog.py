# app/reco/catalog.py
from __future__ import annotations
import os
from typing import Dict, List, Optional, Tuple
import pandas as pd

from app.nlp.normalize import (
    normalize_catalog_df,
    extract_preferences,
    fuzzy_pick,
    norm_txt,
)

# ------------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------------
CATALOG_PATH = os.getenv("KAVAK_CATALOG_PATH", "data/catalog.csv")

# Ajustados a TU CSV:
# id,brand,model,year,km,price,location
COL_ID    = "id"
COL_BRAND = "brand"
COL_MODEL = "model"
COL_YEAR  = "year"
COL_PRICE = "price"
COL_MILE  = "km"         # <-- tu CSV
COL_CITY  = "location"   # <-- tu CSV

# ------------------------------------------------------------------------------------
# Carga y normalización
# ------------------------------------------------------------------------------------
def load_catalog(path: str = CATALOG_PATH) -> pd.DataFrame:
    """
    Carga el CSV del catálogo y añade columnas normalizadas brand_norm / model_norm.
    Exige: brand, model, price, year. (km/location son opcionales a efectos del motor)
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"No se encontró el catálogo en: {path}")

    df = pd.read_csv(path)

    required = {COL_BRAND, COL_MODEL, COL_PRICE, COL_YEAR}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"El CSV debe contener las columnas: {missing}")

    # Normaliza texto (brand/model) y tipos (year/price/km)
    df = normalize_catalog_df(df, brand_col=COL_BRAND, model_col=COL_MODEL)
    df[COL_YEAR]  = pd.to_numeric(df[COL_YEAR], errors="coerce").fillna(0).astype(int)
    df[COL_PRICE] = pd.to_numeric(df[COL_PRICE], errors="coerce").fillna(0.0).astype(float)
    if COL_MILE in df.columns:
        df[COL_MILE] = pd.to_numeric(df[COL_MILE], errors="coerce").fillna(0).astype(int)

    # Limpieza mínima
    df = df[(df[COL_PRICE] > 0) & df[COL_BRAND].notna() & df[COL_MODEL].notna()]

    return df


def build_brand_model_index(df: pd.DataFrame) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Devuelve:
      - brand_list: lista única de marcas (respetando su forma original)
      - model_list_by_brand: dict { brand: [modelos] }
    """
    brands = sorted(df[COL_BRAND].dropna().unique().tolist())
    model_map: Dict[str, List[str]] = {}
    for brand in brands:
        sub = df[df[COL_BRAND] == brand]
        model_map[brand] = sorted(sub[COL_MODEL].dropna().unique().tolist())
    return brands, model_map


# ------------------------------------------------------------------------------------
# Filtros y recomendación
# ------------------------------------------------------------------------------------
def _apply_filters(
    df: pd.DataFrame,
    brand: Optional[str],
    model: Optional[str],
    min_price: Optional[float],
    max_price: Optional[float],
    min_year: Optional[int],
) -> pd.DataFrame:
    sub = df.copy()

    if brand:
        sub = sub[sub[COL_BRAND] == brand]
    if model:
        sub = sub[sub[COL_MODEL] == model]

    if min_price is not None:
        sub = sub[sub[COL_PRICE] >= float(min_price)]
    if max_price is not None:
        sub = sub[sub[COL_PRICE] <= float(max_price)]

    if min_year is not None and min_year > 0:
        sub = sub[sub[COL_YEAR] >= int(min_year)]

    return sub


def recommend(
    df: pd.DataFrame,
    brand_list: List[str],
    model_list_by_brand: Dict[str, List[str]],
    *,
    user_text: Optional[str] = None,
    brand_hint: Optional[str] = None,
    model_hint: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_year: Optional[int] = None,
    top_n: int = 5,
) -> List[Dict]:
    """
    Motor de recomendación tolerante a errores:
    - Extrae preferencias desde user_text (marca/modelo/precio/año).
    - Aplica fuzzy matching contra lo disponible en el catálogo.
    - Filtra y ordena resultados.
    """
    brand_canon = None
    model_canon = None
    _min_price = min_price
    _max_price = max_price
    _min_year  = min_year

    # 1) Preferencias desde el texto
    if user_text:
        prefs = extract_preferences(
            user_text,
            brand_list=brand_list,
            model_list_by_brand=model_list_by_brand,
        )
        brand_canon = prefs.get("brand_canonical") or brand_canon
        model_canon = prefs.get("model_canonical") or model_canon
        _min_price  = prefs.get("min_price") if _min_price is None else _min_price
        _max_price  = prefs.get("max_price") if _max_price is None else _max_price
        _min_year   = prefs.get("year")      if _min_year  is None else _min_year

    # 2) Hints explícitos (si llegan)
    if brand_hint:
        brand_canon = fuzzy_pick(brand_hint, brand_list, score_cutoff=80) or brand_canon
    if model_hint and brand_canon:
        models = model_list_by_brand.get(brand_canon, [])
        model_canon = fuzzy_pick(model_hint, models, score_cutoff=78) or model_canon

    # 3) Filtrar
    sub = _apply_filters(df, brand_canon, model_canon, _min_price, _max_price, _min_year)
    if sub.empty:
        return []

    # 4) Orden (precio asc, año desc) y top-N
    sub = sub.sort_values(by=[COL_PRICE, COL_YEAR], ascending=[True, False]).head(top_n)

    # 5) Estructura de salida
    out: List[Dict] = []
    for _, row in sub.iterrows():
        out.append({
            "id":     int(row[COL_ID]) if COL_ID in row and pd.notnull(row[COL_ID]) else None,
            "brand":  row.get(COL_BRAND),
            "model":  row.get(COL_MODEL),
            "year":   int(row.get(COL_YEAR, 0)) if pd.notnull(row.get(COL_YEAR)) else None,
            "price":  float(row.get(COL_PRICE, 0)) if pd.notnull(row.get(COL_PRICE)) else None,
            "km":     int(row.get(COL_MILE)) if COL_MILE in row and pd.notnull(row.get(COL_MILE)) else None,
            "location": row.get(COL_CITY) if COL_CITY in row else None,
        })
    return out


# ------------------------------------------------------------------------------------
# Formato para WhatsApp / UI
# ------------------------------------------------------------------------------------
def format_recommendations(items: List[Dict]) -> str:
    if not items:
        return "No encontré opciones que cumplan con tus preferencias. ¿Quieres que te ponga en contacto con un agente de Kavak?"

    lines = []
    for it in items:
        title = f'{it["brand"]} {it["model"]} {it["year"]}'.strip()
        price = f'${it["price"]:,.0f}' if it.get("price") else "Precio no disponible"
        extra = []
        if it.get("km") is not None:
            extra.append(f'{it["km"]:,} km')
        if it.get("location"):
            extra.append(it["location"])
        suffix = f' – {", ".join(extra)}' if extra else ""
        lines.append(f"- {title} – {price}{suffix}")

    lines.append("\n¿Quieres que te muestre opciones de financiamiento?")
    return "\n".join(lines)


# ------------------------------------------------------------------------------------
# API de alto nivel
# ------------------------------------------------------------------------------------
class Recommender:
    """
    Carga el catálogo una vez y reutiliza estructuras en memoria.
    """
    def __init__(self, path: str = CATALOG_PATH):
        self.path = path
        self.df = load_catalog(path)
        self.brand_list, self.model_list_by_brand = build_brand_model_index(self.df)

    def recommend_from_text(self, user_text: str, top_n: int = 5) -> List[Dict]:
        return recommend(
            self.df,
            self.brand_list,
            self.model_list_by_brand,
            user_text=user_text,
            top_n=top_n,
        )

    def format_from_text(self, query: str, top_n: int = 5, include_finance_cta: bool = False) -> str:
        """
        Devuelve un bloque tipo:
        Te recomiendo:
        - Nissan Versa 2020 – $280,000
        - Nissan March 2019 – $250,000
        """
        items = self.recommend_from_text(query, top_n=top_n)
        if not items:
            return ("No encontré autos que cumplan con tus criterios. "
                    "¿Quieres que te ponga en contacto con un agente de Kavak?")

        lines = []
        for it in items:
            brand = str(it.get("brand", "")).strip()
            model = str(it.get("model", "")).strip()
            year  = int(it.get("year", 0)) if it.get("year") is not None else ""
            price = float(it.get("price", 0.0))
            lines.append(f"- {brand} {model} {year} – ${price:,.0f}")

        msg = "Te recomiendo:\n" + "\n".join(lines)
        if include_finance_cta:
            msg += "\n\n¿Quieres que te muestre opciones de financiamiento?"
        return msg
