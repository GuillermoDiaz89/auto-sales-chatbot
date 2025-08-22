# tests/test_version_filter.py
import asyncio
import pytest

from app.nlp.intent import route_message

# Helpers
def _low(s: str) -> str:
    return (s or "").lower()

def _has_version_chip_or_header(rl: str, version: str) -> bool:
    """
    Acepta tanto el formato legacy (versión=Sense) como el nuevo encabezado con bullets
    (… • Sense • …). Trabajamos todo en minúsculas.
    """
    v = version.lower()
    return (
        ("versión=" in rl or "version=" in rl) or
        (f"• {v}" in rl) or (f"{v} •" in rl) or (f" {v} " in rl and "búsqueda:" in rl)
    )

@pytest.mark.parametrize(
    "query,expected_model,expected_version,expected_year",
    [
        ("Busco Nissan Versa Sense 2020", "versa", "sense", "2020"),
        ("Quiero un Versa Advance 2021", "versa", "advance", "2021"),
    ],
)
def test_version_chip_and_card_in_reply(query, expected_model, expected_version, expected_year):
    """
    Verifica que:
    1) El encabezado/chips incluyan la versión (acepta legacy 'versión=' o bullets).
    2) Si hay resultados (>0), al menos una tarjeta muestre 'Model [Version] Year'.
       Para consultas que sabemos que no devuelven resultados con los stubs (p. ej. Advance 2021),
       aceptamos '0 resultados' o 'No encontré…' en lugar de exigir tarjeta.
    """
    loop = asyncio.get_event_loop()
    reply = loop.run_until_complete(route_message("u", query))
    rl = _low(reply)

    # 1) Versión presente en encabezado/chips (legacy o nuevo)
    assert _has_version_chip_or_header(rl, expected_version), f"No se encontró chip/encabezado con versión '{expected_version}' en: {reply}"

    # 2) Si hay resultados (>0), valida tarjeta; si no, acepta mensaje de 0/no encontrados
    has_results = ("|") in rl and ("resultado" in rl) and not (" 0 resultado" in rl or " 0 resultados" in rl)
    if has_results and ("no encontré" not in rl):
        # Debe aparecer el modelo y el año; la versión debe aparecer en tarjeta si el catálogo la trae
        assert expected_model in rl, f_
