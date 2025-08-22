
import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
USE_LLM_INTENT = os.getenv("USE_LLM_INTENT", "0") == "1"

ANNUAL_RATE = float(os.getenv("ANNUAL_RATE", "0.10"))

TWILIO_VALIDATE = os.getenv("TWILIO_VALIDATE", "0") == "1"
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
