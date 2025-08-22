import pytest
import app.nlp.retriever as r
from app.texts import PROPUESTA_VALOR_KAVAK

@pytest.mark.parametrize("user_query", [
    "¿Cuál es la propuesta de valor de Kavak?",
    "Cual es la propuesta de valor de kavak",
    "por qué kavak",
    "por que kavak",
    "porque kavak",
    "propuesta valor kavak",
    "por que elegir kavak",
    "qué ofrece kavak",
    "que ofrece kavak",
    "por que comprar con kavak",
])
def test_propuesta_valor_shortcut_returns_constant(user_query, monkeypatch):
    """
    Verifica que para consultas relacionadas a 'propuesta de valor':
    - Se devuelva exactamente PROPUESTA_VALOR_KAVAK (mensaje estático).
    - NO se invoquen FAISS (_load_index, _embed) ni OpenAI.
    - Se devuelva la fuente manual esperada.
    """

    # Si estos se invocan, hacemos fallar explícitamente
    def _fail_index(*args, **kwargs):
        raise AssertionError("_load_index NO debe ser llamado para el atajo de propuesta de valor")

    def _fail_embed(*args, **kwargs):
        raise AssertionError("_embed NO debe ser llamado para el atajo de propuesta de valor")

    class _FailOpenAI:
        def __init__(self, *a, **k):
            pass
        class chat:
            class completions:
                @staticmethod
                def create(*a, **k):
                    raise AssertionError("OpenAI.chat.completions.create NO debe ser llamado para el atajo de propuesta de valor")

    # Parcheamos funciones/cliente que NO deben ser llamados
    monkeypatch.setattr(r, "_load_index", _fail_index, raising=True)
    monkeypatch.setattr(r, "_embed", _fail_embed, raising=True)
    monkeypatch.setattr(r, "OpenAI", _FailOpenAI, raising=True)

    monkeypatch.setenv("OPENAI_API_KEY", "dummy")

    # Ejecutamos
    out = r.kb_answer(user_query)

    # Aserciones
    assert isinstance(out, dict), "kb_answer debe retornar un dict"
    assert out.get("answer") == PROPUESTA_VALOR_KAVAK, (
        f"No devolvió el mensaje estático esperado para la query: {user_query!r}"
    )
    assert "sources" in out and isinstance(out["sources"], list), (
        "El resultado debe incluir sources como lista"
    )
    assert out["sources"] == [{"text": "Fuente: texts.py (manual)"}], (
        "Debe devolver solo la fuente manual esperada"
    )
