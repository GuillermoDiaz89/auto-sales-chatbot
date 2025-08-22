# app/nlp/retriever.py
import os
import json
import re
from typing import List, Dict, Any

import faiss
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from unidecode import unidecode
from app.texts import PROPUESTA_VALOR_KAVAK

# Carga variables de entorno
load_dotenv()

# ------------------------------------------------------------------------------------
# Config
# ------------------------------------------------------------------------------------
INDEX_DIR   = os.path.join(os.path.dirname(__file__), "..", "data", "faiss_index")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()

# Instanciamos el modelo de embeddings una vez
_EMB = SentenceTransformer("all-MiniLM-L6-v2")

# ------------------------------------------------------------------------------------
# Utilidades de índice y embeddings
# ------------------------------------------------------------------------------------
def _load_index():
    """
    Carga el índice FAISS (kb.index) y el metadata (kb_meta.json).
    Devuelve: (index, meta) o (None, []) si no existe.
    """
    index_path = os.path.join(INDEX_DIR, "kb.index")
    meta_path  = os.path.join(INDEX_DIR, "kb_meta.json")
    if not (os.path.exists(index_path) and os.path.exists(meta_path)):
        return None, []
    index = faiss.read_index(index_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return index, meta


def _embed(texts: List[str]) -> np.ndarray:
    """
    Embeddings locales con sentence-transformers.
    Devuelve vectores float32 normalizados (para similitud coseno con IndexFlatIP).
    """
    vecs = _EMB.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return vecs.astype("float32")


def _build_prompt(query: str, snippets: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Construye el prompt (mensajes) para la llamada a OpenAI.
    """
    contexto = "\n\n".join(s.get("text", "") for s in snippets)
    system = (
        "Eres un asistente de soporte de Kavak. Responde en español, "
        "de forma clara, concisa y basada EXCLUSIVAMENTE en el contexto provisto. "
        "Si la respuesta no está en el contexto, dilo explícitamente y AÑADE esta frase al final: "
        "“¿Quieres que te ponga en contacto con un agente de Kavak?”"
    )
    user = f"Pregunta del usuario: {query}\n\nContexto:\n{contexto}"
    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]


def postprocess_no_info(text: str) -> str:
    """
    Si el modelo respondió que no hay información en el contexto,
    agrega una oferta de traspaso a un agente.
    """
    NEG_PATTERNS = [
        "no hay información disponible en el contexto",
        "no encontré información relacionada",
        "no tengo información disponible en el contexto",
        "no se menciona en el contexto",
        "no se encuentra en el contexto",
        "no tengo información",
    ]
    t = (text or "").strip()
    low = t.lower()
    if any(p in low for p in NEG_PATTERNS):
        if "agente de kavak" not in low:
            t += "\n\n¿Quieres que te ponga en contacto con un agente de Kavak?"
    return t

# ------------------------------------------------------------------------------------
# API principal
# ------------------------------------------------------------------------------------
def kb_answer(query: str, k: int = 4, temperature: float = 0.2) -> Dict[str, Any]:
    """
    1) Recupera los k pasajes más relevantes de la base (FAISS + embeddings locales).
    2) Redacta la respuesta con OpenAI usando esos pasajes como contexto.
    Devuelve: {"answer": str, "sources": [snippets...]}

    Atajo: si la consulta corresponde a "propuesta de valor" de Kavak,
    devolvemos la respuesta estática (no se toca FAISS ni OpenAI).
    """
    # --- Shortcut robusto ---
    q_norm = unidecode((query or "").strip().lower())
    trigger_phrases = [
        "propuesta de valor",
        "propuesta valor",
        "valor de kavak",
        "por que kavak",
        "porque kavak",
        "por que elegir kavak",
        "por que comprar en kavak",
        "por que comprar con kavak",
        "por que elegir a kavak",
        "por que kavak",
        "por que en kavak",
        "que ofrece kavak",
        "qué ofrece kavak",
        "porque elegir kavak",
        "por que comprar con kavak",
        "por que confiar en kavak",
        "porque confiar en kavak",
    ]
    if any(kw in q_norm for kw in trigger_phrases):
        return {
            "answer": PROPUESTA_VALOR_KAVAK,
            "sources": [{"text": "Fuente: texts.py (manual)"}],
        }

    # --- Recuperación en FAISS ---
    index, meta = _load_index()
    if not index:
        return {
            "answer": "La base de conocimiento no está construida aún. Ejecuta scripts/build_faiss.py",
            "sources": [],
        }

    qv = _embed([query])
    D, I = index.search(qv, k)

    hits: List[Dict[str, Any]] = []
    for idx in I[0]:
        if isinstance(idx, (int, np.integer)) and 0 <= idx < len(meta):
            hits.append(meta[idx])

    # Si no hay pasajes relevantes → ofrecer escalar a un agente humano
    if not hits:
        return {
            "answer": (
                "No encontré información relacionada con tu criterio de búsqueda. "
                "¿Quieres que te ponga en contacto con un agente de Kavak?"
            ),
            "sources": [],
        }

    # --- Redacción con OpenAI ---
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        # Sin clave, devolvemos el contexto concatenado (mejor que nada)
        contexto = "\n\n".join(h.get("text", "") for h in hits)
        return {
            "answer": (
                "No tengo acceso al modelo de lenguaje (falta OPENAI_API_KEY). "
                "A continuación, el contexto relevante encontrado:\n\n" + contexto
            ),
            "sources": hits,
        }

    try:
        client = OpenAI(api_key=api_key)
        messages = _build_prompt(query, hits)
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=600,
        )
        answer = (completion.choices[0].message.content or "").strip()
    except Exception as e:
        # Fallo de red / API / cuota
        contexto = "\n\n".join(h.get("text", "") for h in hits)
        answer = (
            f"No pude generar la respuesta automáticamente ({e}). "
            "Te comparto el contexto relevante encontrado:\n\n" + contexto
        )

    # Defensa por si el modelo devuelve vacío
    if not answer:
        answer = (
            "No encontré información suficiente referente a tu pregunta. "
            "¿Quieres que te ponga en contacto con un agente de Kavak?"
        )

    # 🔎 Detecta respuestas de "no info" con más variantes
    ans_l = answer.lower()
    NOINFO_PATTERNS = [
        r"\bno (?:tengo|dispongo|cuento) (?:informaci[oó]n|info)\b",
        r"\bno (?:hay|existe) (?:informaci[oó]n|datos)\b",
        r"\bno encontr[ée] (?:informaci[oó]n|datos)\b",
        r"\bno se menciona\b",
        r"\bno (?:est[aá]|figura|aparece) en el contexto\b",
        r"\bno .* en el contexto\b",
        r"(?:contexto|proporcionado).*(?:sin|no).*informaci[oó]n",
        r"no tengo informaci[oó]n disponible en el contexto",
    ]
    if any(re.search(p, ans_l) for p in NOINFO_PATTERNS):
        if "agente de kavak" not in ans_l:
            answer += "\n\n¿Quieres que te ponga en contacto con un agente de Kavak?"

    # Post-procesa por si el modelo dijo “no info” con otras frases
    answer = postprocess_no_info(answer)

    return {"answer": answer, "sources": hits}