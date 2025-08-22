# tests/test_aliases_and_reco.py
import re
import pandas as pd
import pytest

# Importamos funciones del normalizer
from app.nlp.normalize import extract_preferences, canonicalize_brand

# Importamos el Recommender y monkeypatcheamos load_catalog para no leer disco
import app.reco.catalog as catmod
from app.reco.catalog import Recommender, format_recommendations


# ---------- Tests de alias / fuzzy de MARCAS ----------
@pytest.mark.parametrize(
    ("query", "expected_brand"),
    [
        ("busco nisan por menos de 300 mil", "Nissan"),
        ("quiero chevy barato",              "Chevrolet"),
        ("vw jetta 2018",                    "Volkswagen"),
        ("mercedez clase c",                 "Mercedes Benz"),
    ],
)
def test_canonicalize_brand_alias_and_fuzzy(query, expected_brand, sample_catalog_df, monkeypatch):
    # Construimos brand_list a partir del catálogo de prueba
    brand_list = sorted(sample_catalog_df["brand"].unique().tolist())

    # Debe resolver a la marca esperada
    brand = canonicalize_brand(query, brand_list)
    assert brand == expected_brand


@pytest.mark.parametrize(
    ("query", "expected_brand"),
    [
        ("busco nisan por menos de 300 mil", "Nissan"),
        ("chevy spark hasta 200k",           "Chevrolet"),
        ("vw jetta hasta 250 mil",           "Volkswagen"),
    ],
)
def test_extract_preferences_brand_mapping(query, expected_brand, sample_catalog_df, monkeypatch):
    brand_list = sorted(sample_catalog_df["brand"].unique().tolist())
    model_map = {
        b: sorted(sample_catalog_df.loc[sample_catalog_df["brand"] == b, "model"].unique().tolist())
        for b in brand_list
    }
    prefs = extract_preferences(query, brand_list=brand_list, model_list_by_brand=model_map)

    assert prefs["brand_canonical"] == expected_brand
    # Debe detectar al menos el máximo cuando hay “menos de / hasta”
    if "menos de" in query or "hasta" in query:
        assert prefs["max_price"] is not None


# ---------- Tests del Recommender con catálogo en memoria ----------
def test_recommender_filters_brand_and_price(sample_catalog_df, monkeypatch):
    # Monkeypatch: que Recommender use el DF en memoria
    monkeypatch.setattr(catmod, "load_catalog", lambda path=None: sample_catalog_df, raising=True)

    r = Recommender(path="__ignored__.csv")
    out = r.recommend_from_text("busco nisan por menos de 300 mil", top_n=10)

    assert len(out) > 0
    # Todos deben ser Nissan y tener precio <= 300000
    assert all(item["brand"] == "Nissan" for item in out)
    assert all(item["price"] <= 300000 for item in out)

    # Formato amigable
    text = format_recommendations(out[:5])
    assert "¿Quieres que te muestre opciones de financiamiento?" in text


def test_recommender_other_brand_chevy(sample_catalog_df, monkeypatch):
    monkeypatch.setattr(catmod, "load_catalog", lambda path=None: sample_catalog_df, raising=True)

    r = Recommender(path="__ignored__.csv")
    out = r.recommend_from_text("quiero chevy hasta 200 mil", top_n=10)

    # Puede devolver vacío si no hay chevrolet <= 200k en el DF de prueba,
    # pero si hay, todos deben ser Chevrolet y respetar el precio max
    for item in out:
        assert item["brand"] == "Chevrolet"
        assert item["price"] <= 200000


def test_recommender_vw_jetta(sample_catalog_df, monkeypatch):
    monkeypatch.setattr(catmod, "load_catalog", lambda path=None: sample_catalog_df, raising=True)

    r = Recommender(path="__ignored__.csv")
    out = r.recommend_from_text("vw jetta 2018 hasta 230 mil", top_n=10)

    # Si hay resultado, debe ser Volkswagen Jetta y <= 230000
    for item in out:
        assert item["brand"] == "Volkswagen"
        assert item["model"] == "Jetta"
        assert item["price"] <= 230000
