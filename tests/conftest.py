# tests/conftest.py
import os
import sys
import asyncio
import importlib
import pandas as pd
import pytest
from fastapi.testclient import TestClient

# --- lo que ya tenías: asegurar event loop y sys.path ---
@pytest.fixture(autouse=True)
def fix_event_loop():
    # Útil en Windows para evitar event loops “cerrados”
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield
    finally:
        loop.close()

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------- STUBS de catálogo y settings para pruebas ----------
@pytest.fixture(autouse=True)
def stub_tools(monkeypatch):
    CARS = [
        {"id": 322722, "brand": "Nissan", "model": "Versa", "version": "Sense", "year": 2020,
         "km": 45837, "price": 265_999, "location": "Online"},
        {"id": 320505, "brand": "Nissan", "model": "Sentra", "version": "", "year": 2019,
         "km": 18383, "price": 268_999, "location": "Online"},
        {"id": 316168, "brand": "Suzuki", "model": "Swift", "version": "", "year": 2023,
         "km": 18410, "price": 298_999, "location": "Online"},
    ]

    def search_cars(filters, limit: int, offset: int):
        return CARS[offset: offset + limit]

    def search_cars_count(filters):
        return len(CARS)

    def cotiza_car(car_id, down_payment, term, annual_rate=None):
        return (
            f"Cotización #{car_id}\n"
            f"Precio: ${CARS[0]['price']:,} • Enganche: ${int(down_payment):,}\n"
            f"Plazo: {term} meses • Tasa anual: 12.0%\n"
            "Mensualidad aprox: $5,547\n"
            "¿Te comparto el detalle y requisitos?"
        )

    def finance_plan(price, down_payment):
        return {"plans": [{"term_months": 24, "monthly": 7800}]}

    def kb_tool(q):
        return "Política de devolución: 7 días."

    monkeypatch.setattr("app.nlp.tools.search_cars", search_cars, raising=False)
    monkeypatch.setattr("app.nlp.tools.search_cars_count", search_cars_count, raising=False)
    monkeypatch.setattr("app.nlp.tools.cotiza_car", cotiza_car, raising=False)
    monkeypatch.setattr("app.nlp.tools.finance_plan", finance_plan, raising=False)
    monkeypatch.setattr("app.nlp.tools.kb_tool", kb_tool, raising=False)

    # Settings de prueba
    monkeypatch.setattr("app.settings.KAVAK_ANNUAL_RATE", 0.12, raising=False)
    monkeypatch.setattr("app.settings.DEFAULT_TERM", 36, raising=False)
    monkeypatch.setattr("app.settings.ALLOWED_TERMS", {24, 36, 48}, raising=False)
    yield

# ---------- Limpia el estado global entre tests ----------
@pytest.fixture(autouse=True)
def reset_state():
    import app.nlp.intent as intent
    intent.LAST_FILTERS.clear()
    intent.LAST_OFFSET.clear()
    intent.LAST_LIMIT.clear()
    intent.LAST_PAGE.clear()
    intent.LAST_CTX.clear()
    yield

# ---------- TestClient de FastAPI ----------
@pytest.fixture()
def client(monkeypatch):
    # Desactiva validación de firma Twilio en pruebas
    try:
        monkeypatch.setattr("app.config.TWILIO_VALIDATE", False, raising=False)
    except Exception:
        pass

    # Recarga el módulo main para aplicar monkeypatches
    import app.main as m
    importlib.reload(m)
    from app.main import app
    return TestClient(app)

# Helper: POST estilo Twilio a /whatsapp
@pytest.fixture()
def post_wa(client):
    def _post(body: str, from_number: str = "whatsapp:+5215555555555"):
        return client.post(
            "/whatsapp",
            data={"From": from_number, "Body": body},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    return _post

@pytest.fixture
def sample_catalog_df():
    import pandas as pd
    data = [
        # id, brand, model, year,   km,     price,   location
        (1,  "Nissan",      "Sentra",     2015, 106104, 183999.0, "Online"),
        (2,  "Nissan",      "March",      2018,  68601, 184999.0, "Online"),
        (3,  "Nissan",      "Sentra",     2018,  99564, 199999.0, "Online"),
        (4,  "Nissan",      "Pathfinder", 2015, 103561, 218999.0, "Online"),
        (5,  "Nissan",      "Versa",      2018,  69630, 220999.0, "Online"),
        (6,  "Chevrolet",   "Aveo",       2017, 119157, 138999.0, "Online"),
        (7,  "Volkswagen",  "Jetta",      2018, 100618, 222999.0, "Online"),
        (8,  "KIA",         "Rio",        2020,  39492, 331999.0, "Online"),
        (9,  "Mercedes Benz","Clase C",   2017,  74700, 882999.0, "Online"),
    ]
    return pd.DataFrame(data, columns=["id","brand","model","year","km","price","location"])