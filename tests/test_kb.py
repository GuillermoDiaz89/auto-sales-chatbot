from app.nlp.retriever import kb_answer

def test_kb_answer_no_index(monkeypatch):
    # Simula que NO hay índice ni metadatos
    monkeypatch.setattr("app.nlp.retriever._load_index", lambda: (None, []))

    ans = kb_answer("¿Cuál es la garantía?")
    txt = ans["answer"].lower()

    # Mensaje útil cuando no hay índice
    assert "no está construida" in txt or "no esta construida" in txt