
import asyncio
from app.nlp.intent import route_message

def test_route_search():
    reply = asyncio.get_event_loop().run_until_complete(route_message("u","Busco nisan versa 2020 menos de 220 mil"))
    assert "opciones" in reply.lower() or "no encontré" in reply.lower()

def test_route_finance():
    reply = asyncio.get_event_loop().run_until_complete(route_message("u","Con 40 mil de enganche, precio 250000 a 48 meses"))
    assert "precio" in reply.lower()
