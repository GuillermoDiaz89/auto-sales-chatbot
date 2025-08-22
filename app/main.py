# app/main.py
import os
from fastapi import FastAPI, Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator

from app.schemas import ChatRequest
from app.nlp.intent import route_message
from app.texts import WELCOME_MSG
from app.config import TWILIO_VALIDATE  # bool (True/False)

app = FastAPI(title="Kavak Agent API")


def _chunk_for_whatsapp(text: str, max_len: int = 1200) -> list[str]:
    s = text or ""
    return [s[i:i + max_len] for i in range(0, len(s), max_len)] or [""]


def _twilio_signature_is_valid(url: str, form_fields: dict, signature: str | None) -> bool:
    """Valida la firma de Twilio contra la URL pública exacta y los campos del form."""
    if not TWILIO_VALIDATE:
        return True
    auth = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not auth or not signature:
        return False
    validator = RequestValidator(auth)
    return validator.validate(url, form_fields, signature)


@app.get("/")
async def root():
    return {"message": "Kavak Agent API up. See /docs for swagger and POST /chat to talk."}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest):
    # simple API for local testing
    reply = await route_message("local", req.text)
    return {"reply": reply}


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    # Lee el form una sola vez
    form = await request.form()
    body_text = (form.get("Body") or "").strip()
    from_number = form.get("From", "")
    waid = form.get("WaId") or from_number

    # Validación de firma (opcional)
    public_url = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") + str(request.url.path)
    signature = request.headers.get("X-Twilio-Signature")
    if not _twilio_signature_is_valid(public_url, dict(form), signature):
        # Firma inválida → 403 sin TwiML
        return Response(status_code=403, content="")

    # Genera respuesta
    try:
        reply_text = await route_message("whatsapp", body_text, user_id=waid)
    except Exception as e:
        reply_text = f"Lo siento, ocurrió un error procesando tu mensaje: {e}"

    # Fallback: nunca respondas vacío
    parts = [p for p in _chunk_for_whatsapp(reply_text) if p.strip()]
    if not parts:
        parts = [WELCOME_MSG]

    resp = MessagingResponse()
    for p in parts:
        resp.message(p)

    return Response(content=str(resp), media_type="application/xml")
