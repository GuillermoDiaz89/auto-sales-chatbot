# tests/test_webhook.py
def _assert_twiml_has_message(resp):
    assert resp.status_code == 200
    xml = resp.text
    assert "<Response>" in xml and "</Response>" in xml
    assert "<Message>" in xml, f"TwiML sin <Message>: {xml}"
    return xml


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_greet_returns_welcome(post_wa):
    r = post_wa("hola")
    xml = _assert_twiml_has_message(r)
    assert "asistente de Kavak" in xml or "Bienvenido a Kavak" in xml


def test_search_chips_and_results(post_wa):
    r = post_wa("Nissan Versa 2020 menos de 300k")
    xml = _assert_twiml_has_message(r)
    # Encabezado human-friendly
    assert "desde 2020" in xml
    assert "hasta $300,000" in xml
    # Tiene listado de opciones
    assert "Te recomiendo" in xml
    assert "Nissan Versa 2020" in xml


def test_quote_by_card_then_yes_details(post_wa):
    # 1) Una búsqueda para llenar LAST_PAGE
    _ = post_wa("Nissan Versa 2020 menos de 300k")
    # 2) Cotiza por número de tarjeta
    r2 = post_wa("cotiza 1 con 99k a 36 meses")
    xml2 = _assert_twiml_has_message(r2)
    assert "Cotización #322722" in xml2 or "Cotizacion #322722" in xml2

    # 3) Confirma con "sí" → debería mandar requisitos
    r3 = post_wa("si")
    xml3 = _assert_twiml_has_message(r3)
    assert "Requisitos y pasos" in xml3
    assert "tasa" in xml3.lower()


def test_contact_lead_ack(post_wa):
    # Tras cualquier mensaje, se puede pedir contacto
    r = post_wa("contacto Juan juan@mail.com")
    xml = _assert_twiml_has_message(r)
    assert "asesor te contactará" in xml or "asesor te contactara" in xml
    assert "juan@mail.com" in xml
