# 📖 Kavak AI Agent

## 📝 Descripción

Este proyecto implementa un **asistente virtual (chatbot)** que simula a un agente comercial de **Kavak**, con las siguientes capacidades:

- Responder preguntas frecuentes sobre **políticas, garantías, seguros y propuesta de valor**.  
- Recomendar autos del catálogo (CSV provisto).  
- Ofrecer planes de financiamiento con una tasa del **10% anual** a plazos de **3–6 años**.  
- Conectarse con **WhatsApp mediante Twilio Sandbox** para una experiencia conversacional real.  
- Utilizar un enfoque de **Retrieval-Augmented Generation (RAG)** para minimizar alucinaciones y responder con información de la base de conocimiento (PDF de Kavak).  

---

## 🛠️ Stack Tecnológico

- **Lenguaje**: Python 3.10+  
- **Framework web**: FastAPI  
- **Mensajería**: Twilio WhatsApp Sandbox  
- **LLM API**: OpenAI (modelo `gpt-4o-mini`)  
- **Embeddings**: Sentence-Transformers (`all-MiniLM-L6-v2`)  
- **Motor de búsqueda semántica**: FAISS  
- **Gestión de entornos**: `.env` con `python-dotenv`  
- **Exposición local**: ngrok  

---

## ⚙️ Flujo de Funcionamiento

1. **Indexación de la KB**
   - Convierte el PDF de Kavak en texto.
   - Genera embeddings con `all-MiniLM-L6-v2`.
   - Crea un índice FAISS (`kb.index`) y guarda metadatos (`kb_meta.json`).

2. **Consulta (Retriever)**
   - Convierte la consulta a embedding.
   - Recupera los fragmentos más relevantes.
   - Construye un prompt con el contexto.

3. **Generación de Respuesta**
   - Envía el prompt al modelo `gpt-4o-mini`.
   - Si hay contexto → responde citando fragmentos.  
   - Si no hay contexto → responde con fallback:  
     *“Lo siento, no tengo información disponible sobre ese tema. ¿Quieres que te ponga en contacto con un agente de Kavak?”*

4. **Integración con WhatsApp**
   - FastAPI expone `/whatsapp/webhook`.
   - Twilio Sandbox reenvía mensajes entrantes a ese endpoint.
   - El bot responde con TwiML (mensajes de texto).

---

## 🎯 UX y Manejo de Errores

- **Filtros anti-alucinación** → fuerza fallback si no hay información válida.  
- **Respuestas con contexto** → incluyen fuentes resumidas.  
- **Errores en API** → mensajes amigables.  
- **FAISS sin coincidencias** → fallback a agente humano.  
- **UX en WhatsApp**:  
  - Mensajes concisos, con *negritas* y listas.  
  - Truncamiento de textos largos con `…`.  

---

## 🛠️ Requisitos

- Python 3.10+  
- Cuenta en [OpenAI](https://platform.openai.com/) con API Key  
- Cuenta en [Twilio](https://www.twilio.com/) con acceso al WhatsApp Sandbox  
- [ngrok](https://ngrok.com/) instalado  

Instalación de dependencias:

```bash
pip install -r requirements.txt


## 🚀 Instalación y Ejecución Local
Clonar repo y crear entorno virtual


git clone https://github.com/<tu-repo>.git
cd kavak-agent
python -m venv .venv
.venv\Scripts\activate   # Windows
source .venv/bin/activate   # Linux/Mac
Crear archivo .env (basado en .env.example)


OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4o-mini
TWILIO_ACCOUNT_SID=your_twilio_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
PUBLIC_BASE_URL=https://your-ngrok-url.ngrok-free.app
Ejecutar FastAPI


uvicorn app.main:app --host 0.0.0.0 --port 8000
Exponer con ngrok


ngrok http 8000
Copia la URL pública y configúrala en Twilio Sandbox → “When a message comes in”.

Probar desde WhatsApp

Abre WhatsApp en tu celular.

Envía un mensaje al número del Sandbox: +1 415 523 8886.

El bot responderá usando la KB + RAG.


📊 Roadmap hacia Producción
 Dockerizar la aplicación

 Desplegar en cloud (AWS ECS/Fargate o Azure App Service)

 Manejo de estado de conversación en Redis/DynamoDB

 Integrar catálogo CSV en recomendaciones de autos

 Calcular financiamiento dinámico

 Integrar métricas (Twilio callbacks + logs en CloudWatch/ELK)

 Pruebas unitarias con pytest

▶️ Manual de Interacción del Usuario
Ejemplos de interacción en WhatsApp:

🔎 Consultar políticas
Usuario:
¿Cuál es la política de garantía?

Bot:
La política de garantía de Kavak es de 7 días o 300 km, lo que ocurra primero.

🛡️ Preguntar por seguros
Usuario:
¿Qué incluye el seguro de Kavak?

Bot:
El seguro de Kavak incluye cobertura básica de daños, robo total y responsabilidad civil.

🚗 Recomendación de autos
Usuario:
Quiero un Nissan por menos de 300 mil pesos

Bot:


Te recomiendo:
- Nissan Versa 2020 – $280,000
- Nissan March 2019 – $250,000
💰 Calcular financiamiento
Usuario:
Quiero financiar un auto de 300,000 con un enganche de 50,000 a 36 meses

Bot:


Pago mensual estimado: $7,235
Monto total financiado: $260,000
❌ Preguntas fuera de la KB
Usuario:
¿Dónde están las sucursales de Ford?

Bot:
Lo siento, no tengo información disponible sobre ese tema.

⚠️ Ejemplo de uso en Python

from app.nlp.retriever import kb_answer

res = kb_answer("¿Cuál es la garantía?")
print(res["answer"])
for s in res["sources"]:
    print("-", s["text"])
🧪 Pruebas
Ejecutar la suite de tests:


pytest -v
👨‍💻 Autor
Guillermo Díaz
LinkedIn · GitHub



