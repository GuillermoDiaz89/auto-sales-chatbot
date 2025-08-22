
from app.nlp.tools import search_cars

def test_search_cars_basic():
    filters = {"brand": "nisan", "model": "versa", "price_max": 230000}
    rows = search_cars(filters, limit=3)
    assert isinstance(rows, list)
