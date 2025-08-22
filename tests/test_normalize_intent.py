# tests/test_normalize_intent.py
import pytest

# Importa desde tu módulo
from app.nlp.intent import normalize_intent, SYNONYMS

def _is_true_or_token(val):
    """
    La función normalize_intent puede devolver:
      - True (bool), o
      - la palabra sinónima detectada (str)
    Este helper homologa la aserción a 'truthy'.
    """
    return bool(val)

@pytest.mark.parametrize(
    "text, expected_keys_present, expected_keys_absent",
    [
        (
            "Quiero una camioneta barata en mensualidades",
            {"carroceria", "precio", "forma_pago"},
            {"km", "anio"},
        ),
        (
            "Busco un sedán económico último modelo",
            {"carroceria", "precio", "anio"},
            {"forma_pago", "km"},
        ),
        (
            "Necesito SUV con pocos km y accesible",
            {"carroceria", "km", "precio"},
            {"forma_pago"},
        ),
        (
            "Estoy interesado en crédito para un coche nuevo",
            {"forma_pago", "anio"},
            {"km", "carroceria"},
        ),
        (
            "Un hatchback usado, por favor",
            {"carroceria", "km"},   # 'usado' mapea a km (pocos-uso/recorrido) según tu diccionario
            {"precio", "forma_pago"},
        ),
    ],
)
def test_normalize_intent_basic(text, expected_keys_present, expected_keys_absent):
    result = normalize_intent(text)

    # 1) Todas las claves esperadas deben estar y ser truthy (True o token)
    for key in expected_keys_present:
        assert key in SYNONYMS, f"La clave '{key}' no existe en SYNONYMS (revisa el diccionario)."
        assert key in result, f"Se esperaba la clave '{key}' en el resultado para: {text}"
        assert _is_true_or_token(result[key]), f"Valor no truthy para '{key}' en: {text}"

    # 2) Las claves que NO deberían dispararse deben estar ausentes o en falsy
    for key in expected_keys_absent:
        if key in result:
            assert not _is_true_or_token(result[key]), f"No se esperaba '{key}' activado en: {text}"

def test_no_matches_returns_empty_dict():
    text = "Solo estoy navegando sin intención específica."
    result = normalize_intent(text)
    # No debería activar ninguna categoría
    assert isinstance(result, dict)
    assert len(result) == 0

def test_case_insensitive_and_spacing():
    text = "   QuIeRo   SuV   eConÓmiCo   "
    result = normalize_intent(text)
    # Debe detectar 'carroceria' y 'precio' sin importar mayúsculas ni espacios
    assert "carroceria" in result and _is_true_or_token(result["carroceria"])
    assert "precio" in result and _is_true_or_token(result["precio"])
