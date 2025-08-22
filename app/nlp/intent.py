# app/nlp/intent.py
from __future__ import annotations
import re
from typing import Dict, Any, List
from unidecode import unidecode
from app.nlp.normalize import norm_txt, parse_numeric
from app.nlp.tools import finance_plan, kb_tool, search_cars_count, cotiza_car, search_cars  # funciones en tools.py
from app.router import retrieve_cars, search_cars_count  # construcción del reply (con paginación)
from app.settings import DEFAULT_TERM, ALLOWED_TERMS, KAVAK_ANNUAL_RATE
from app.texts import WELCOME_MSG, DETAILS_AFTER_QUOTE, PROPUESTA_VALOR_KAVAK

# Memoria de últimos filtros y offset para paginación
LAST_FILTERS: dict[str, Dict[str, Any]] = {}  # filtros persistentes por canal
LAST_OFFSET:  dict[str, int] = {}             # cuántos ya mostramos
LAST_LIMIT:   dict[str, int] = {}             # tamaño de la última página mostrada
LAST_PAGE:    dict[str, List[Dict[str, Any]]] = {}  # última página mostrada por canal
LAST_CTX:     dict[str, Dict[str, Any]] = {} 
LAST_TOTAL   = {}   # chat_id -> int

""" contexto de la última conversación por canal 
Regexes para detectar preguntas y respuestas
"""
# Saludos / menú
GREET_RE = re.compile(r'^\s*(hola+|buenas|hey|hi|menu|ayuda|start)\b', re.I)
# Confirmaciones / contacto (robustos)
YES_RE_RAW   = re.compile(r'^\s*(s[ií]|si|claro|vale|ok(ay)?|de acuerdo|correcto|adelante|por favor)\s*[!.…]*\s*$', re.I)
NO_RE_RAW    = re.compile(r'^\s*(no|luego|despu[eé]s|gracias)\s*[!.…]*\s*$', re.I)
# Contacto/asesor (con nombre, email y/o teléfono)
CONTACT_RE = re.compile(r'^\s*(contact(o|arme)|asesor|ll[aá]mame|llamada)\b(.*)$', re.I)
EMAIL_RE   = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
PHONE_RE   = re.compile(r'\+?\d{7,15}')

SEARCH_TRIGGERS = (
    "busca", "buscar", "encuentra", "quiero", "necesito", "muéstrame", "muestrame",
    # marcas/modelos frecuentes: (amplía tu lista si quieres)
    "nissan","toyota","chevrolet","honda","mazda","kia","volkswagen","ford","bmw",
    "sentra","versa","corolla","civic","jetta","swift","tracker",
    # años frecuentes
    "2019","2020","2021","2022","2023","2024","2025"
)

def _details_after_quote(ctx: Dict[str, Any]) -> str:
    down = int(ctx.get("down_payment") or 0)
    term = int(ctx.get("term") or 0)
    rate = KAVAK_ANNUAL_RATE * 100
    return DETAILS_AFTER_QUOTE.format(down=down, term=term, rate=rate)

def _send_lead_stub(name: str = "", email: str = "", phone: str = "", ctx: Dict[str, Any] | None = None) -> str:
    # TODO: integra CRM/Slack/Email. Por ahora solo echo.
    parts = []
    if name:  parts.append(f"Nombre: {name}")
    if email: parts.append(f"Email: {email}")
    if phone: parts.append(f"Tel: {phone}")
    if ctx and ctx.get("car_id"): parts.append(f"Interés en ID #{ctx['car_id']}")
    return " | ".join(parts) or "(sin datos)"

def _looks_like_search(t: str) -> bool:
    """¿El texto contiene señales claras de búsqueda?"""
    t = norm_txt(t)
    return any(tok in t for tok in SEARCH_TRIGGERS) \
           or bool(re.search(r"(19|20)\d{2}", t)) \
           or bool(RANGO_PRECIOS_RE.search(t)) \
           or bool(_MIN_RE.search(t)) or bool(_MAX_RE.search(t))


"""
Diccionario de sinónimos para evitar ambigüedades en las búsquedas.
De esta manera, si el usuario escribe "Suv" o "Suv 2020" entonces
buscará automóviles de carrocería de tipo Suv del año 2020.
"""
SYNONYMS = {
    "carroceria": {
        "camioneta", "suv", "sedan", "sedán", "hatchback", "hb", "pickup", "jeep", "coupe", "coupé"
    },
    "precio": {
        "barato", "barata", "baratos", "baratas", "economico", "económico", "economica", "económica", "accesible"
    },
    "forma_pago": {
        "mensualidad", "mensualidades", "credito", "crédito", "financiamiento"
    },
    "anio": {
        "nuevo", "nueva", "nuevos", "nuevas", "ultimo", "último", "modelo", "modelos", "reciente", "último modelo", "ultimo modelo"
    },
    "km": {
        "usado", "usada", "usados", "usadas", "pocos km", "con poco uso" "kilometraje", "km"
    },
}

# Esta función devuelve un diccionario con las palabras sinónimas
# que se han encontrado en el texto.
def normalize_intent(text: str) -> dict:
    t = norm_txt(text)
    out = {}
    for key, words in SYNONYMS.items():
        for w in words:
            # usa regex para coincidir palabra/frase completa
            if re.search(rf"\b{re.escape(w)}\b", t):
                out[key] = w
                break
    return out


# ---------------- Intent detection sencilla ----------------
def _detect_intent(text: str) -> str:
    t = norm_txt(text)
      # 1) Saludos/menú primero
    if GREET_RE.match(text or ""):
        return "greet"
    # 2) Ayuda explícita
    if re.search(r"(ayuda|help|qué puedes|que puedes|como me ayudas)", t):
        return "help"
    # 3) Finanzas y KB
    if re.search(r"(mensualidad|mensualidades|enganche|plazo|financia|financiamiento)", t):
        return "finance"
    if re.search(r"(garanti|devoluc|proceso|entrega|tiempo|politica)", t):
        return "kb"
    # 4) Solo buscamos si hay señales claras
    if _looks_like_search(t):
        return "search"
    # 5) Si es corto/ambiguo → menú/ayuda
    return "help"

# ---------------- Cotización por ID + enganche ----------------
# Acepta: 50k, 50 k, 50,000, 50.000, 50 000, 50 mil, 50mil, $50 000, etc.
NUM = r"(?:\d[\d\s.,]*)"  # Permite dígitos con separadores de miles (espacio, coma o punto)

# "cotiza <id> con <enganche>"
COTIZA_RE = re.compile(
    rf"(?:^|\s)cotiza\s+(\d{{1,9}})\s+"  # acepta 1..9 dígitos (1=tarjeta; >=3=ID)
    rf"(?:con|con\s+un\s+enganche\s+de)?\s*"
    rf"(\$?\s*{NUM}\s*mil|\$?\s*{NUM}\s*k|\$?\s*{NUM})",
    re.IGNORECASE
)

# Rango de precios: "entre 250 000 y 290000", "de 250k a 290k", "250 mil - 290 mil"
RANGO_PRECIOS_RE = re.compile(
    r"(?:entre|de)?\s*\$?\s*([\d\s\.,]+(?:k|mil)?)\s*(?:a|y|-)\s*\$?\s*([\d\s\.,]+(?:k|mil)?)",
    re.IGNORECASE
)

# Paginación: "ver 3 más", "siguiente 10"
PAGINATE_RE = re.compile(r"\bver\s+(?:(\d+)\s*m[aá]s|m[aá]s(?:\s+(\d+))?)\b", re.I)

# Quitar filtros: "quita precio", "quita año", "quita marca", "quita modelo", "quita km"
QUITAR_RE = re.compile(r"\bquita(?:r)?\s+(marca|modelo|a[nñ]o|year|precio|max|min|km|kilometraje)\b", re.I)

# Plazo de cotización
PLAZO_RE = re.compile(r"(?:a|en)\s*(\d{2,3})\s*(?:mes|meses)", re.I)
TASA_RE  = re.compile(r"(?:tasa|inter[eé]s)\s*(?:de)?\s*([0-9]+(?:\.[0-9]+)?)\s*%?", re.I)


def _parse_money(s: str) -> float:
    """
    Acepta '50k', '50 k', '$50,000', '50,000', '50 mil', '50mil', '50000', '50 000'
    """
    t = norm_txt(s).replace(",", "").replace("$", "").replace(" ", "").strip()
    # 'k'
    if t.endswith("k"):
        base = t[:-1].strip()
        try:
            return float(base) * 1000.0
        except Exception:
            val = parse_numeric(base)
            return float(val) * 1000.0 if val is not None else 0.0
    # 'mil'
    if t.endswith("mil"):
        base = t[:-3].strip()
        try:
            return float(base) * 1000.0
        except Exception:
            val = parse_numeric(base)
            return float(val) * 1000.0 if val is not None else 0.0
    # números normales
    val = parse_numeric(t)
    return float(val) if val is not None else 0.0


def _parse_term(text: str, default: int = DEFAULT_TERM) -> int:
    m = PLAZO_RE.search(text)
    if not m:
        return default
    try:
        term = int(m.group(1))
    except Exception:
        return default
    # ajusta a los plazos permitidos
    if term not in ALLOWED_TERMS:
        term = min(ALLOWED_TERMS, key=lambda x: abs(x - term))
    return term


# --- Price bounds (min / max) ---
_MIN_RE = re.compile(r"(?:más de|mas de|mayor a|arriba de|desde)\s*(\$?\s*[\d\s\.,]+(?:k|mil)?)", re.IGNORECASE)
_MAX_RE = re.compile(r"(?:menos de|menor a|por debajo de|hasta)\s*(\$?\s*[\d\s\.,]+(?:k|mil)?)", re.IGNORECASE)

def _extract_price_bounds(raw: str) -> tuple[float | None, float | None]:
    """
    Detecta price_min (>=) y price_max (<=) a partir de frases como:
      - "más de 290000", "mayor a 250k", "desde 200 mil"  -> min
      - "menos de 230000", "hasta 250k", "por debajo de 300 mil" -> max
    Capturamos el número pegado a la frase para no confundirlo con el año.
    """
    price_min = None
    price_max = None

    m_min = _MIN_RE.search(raw)
    if m_min:
        price_min = _parse_money(m_min.group(1))

    m_max = _MAX_RE.search(raw)
    if m_max:
        price_max = _parse_money(m_max.group(1))

    return price_min, price_max


def _apply_remove_filters(filters: Dict[str, Any], raw: str) -> Dict[str, Any]:
    """
    Si el usuario escribe 'quita <filtro>' en el MISMO mensaje,
    eliminamos esa clave de 'filters' antes de buscar.
    """
    m = QUITAR_RE.findall(raw or "")
    if not m:
        return filters

    to_remove = set()
    for token in m:
        t = token.lower()
        if t in ("marca",):
            to_remove.add("brand")
        elif t in ("modelo",):
            to_remove.add("model")
        elif t in ("año", "ano", "year"):
            to_remove.add("year_min"); to_remove.add("year_max")
        elif t in ("precio", "max", "min"):
            to_remove.add("price_min"); to_remove.add("price_max")
        elif t in ("km", "kilometraje"):
            to_remove.add("km_max")

    for k in to_remove:
        filters.pop(k, None)
    return filters

def _match_prop_valor_kavak(text):
    norm = unidecode((text or "").strip().lower())
    for kw in [
        "propuesta de valor",
        "propuesta valor",
        "valor de kavak",
        "por que kavak",
        "porque kavak",
        "por que elegir kavak",
        "por que comprar en kavak",
        "por que comprar con kavak",
    ]:
        if kw in norm:
            return True
    return False

# ---------------- Router principal ----------------
async def route_message(channel: str, text: str, user_id: str | None = None) -> str:
    """
    Orquesta la intención:
      0) Respuestas rápidas (confirmaciones, contacto, etc.)
      1) Cotización "cotiza <id> con <enganche>"
      2) Finanzas
      3) KB
      4) Búsqueda en catálogo (con paginación persistente, quita-filtros y rangos de precio)
    """
    raw = text or ""
    t = norm_txt(raw)

    # Propuesta de valor de Kavak/por qué Kavak?
    if _match_prop_valor_kavak(raw):
        return PROPUESTA_VALOR_KAVAK

    # ---MENÚ / GREET---
    if GREET_RE.match(raw):
        return WELCOME_MSG

    # 0) Confirmaciones: “sí / no” y contacto/asesor
    if YES_RE_RAW.match(raw):
        ctx = LAST_CTX.get(channel)
        if ctx and ctx.get("kind") == "quote":
            return _details_after_quote(ctx)
        return "¿De qué te comparto detalles? Puedes decir `detalles 1` o `cotiza <ID>`."

    if NO_RE_RAW.match(raw):
        return "¡Perfecto! ¿Ajustamos precio, año o prefieres otra marca/modelo?"

    m_contact = CONTACT_RE.match(raw)
    if m_contact:
        tail = (m_contact.group(3) or "").strip()
        email = EMAIL_RE.search(tail).group(0) if EMAIL_RE.search(tail) else ""
        phone = PHONE_RE.search(tail).group(0) if PHONE_RE.search(tail) else ""
        name  = tail
        for token in (email, phone):
            if token:
                name = name.replace(token, "").strip(",; ").strip()

        if not email and not phone:
            return ("Perfecto. Compárteme al menos tu *correo* (ej. `contacto Ana ana@mail.com`) "
                    "o tu *teléfono* (ej. `llámame al +52...`).")

        summary = f"Nombre: {name or '(sin nombre)'}"
        if email: summary += f" | Email: {email}"
        if phone: summary += f" | Tel: {phone}"
        if (LAST_CTX.get(channel) or {}).get("car_id"):
            summary += f" | Interés en ID #{LAST_CTX[channel]['car_id']}"

        return f"¡Listo! Un asesor te contactará en breve.\n{summary}"

    # ---------- 1) INTENT: COTIZA (captura primero) ----------
    m = COTIZA_RE.search(raw)
    if m:
        car_token = m.group(1)          # puede ser "1" (tarjeta) o "322722" (ID)
        down_s    = m.group(2)
        down_payment = _parse_money(down_s)
        term = _parse_term(raw, default=DEFAULT_TERM)

        # Resolver número de tarjeta → ID real
        car_id = None
        if car_token.isdigit() and len(car_token) <= 3:  # 1..999 como índice visible
            vis = int(car_token)
            page_map = LAST_PAGE.get(channel) or {}
            if vis in page_map:
                car_id = page_map[vis]
        else:
            # si viene un ID directo, úsalo tal cual
            car_id = car_token

        if not car_id:
            return ("No pude identificar el auto. Usa `cotiza <número>` sobre los resultados actuales "
                    "o `cotiza <ID>`.")

        reply = cotiza_car(
            car_id=car_id,
            down_payment=down_payment,
            term=term,
            annual_rate=None,
        )

        # guarda contexto para responder “sí”
        LAST_CTX[channel] = {
            "kind": "quote",
            "car_id": car_id,
            "down_payment": int(down_payment or 0),
            "term": int(term or 0),
        }

        # Nota de tasa solo si el usuario la mencionó en el mensaje
        if re.search(r"(tasa|inter[eé]s)\s*\d", raw, re.I):
            reply += f"\n\n*Nota:* La tasa la define Kavak y puede variar; estándar {KAVAK_ANNUAL_RATE*100:.1f}%."

        reply += (
            "\n\nSi quieres avanzar, escribe: `contacto <tu nombre> <correo>` "
            "o envíame *tu teléfono* con: `llámame al <número>`."
        )
        return reply

    # ---------- 1.5) PAGINACIÓN (ver 3 más / ver más 3 / ver más) ----------
    m_pag = PAGINATE_RE.search(raw)
    if m_pag:
        # cuántos quiere ver
        how_many = m_pag.group(1) or m_pag.group(2)
        step = int(how_many) if how_many else LAST_LIMIT.get(channel, 5)

        base_filters = LAST_FILTERS.get(channel)
        if not base_filters:
            return "No tengo una búsqueda previa para continuar. Dime qué estás buscando."

        prev_offset = LAST_OFFSET.get(channel, 0)
        prev_limit  = LAST_LIMIT.get(channel, 5)
        new_offset  = prev_offset + prev_limit

        total = search_cars_count(base_filters)
        if new_offset >= total:
            return ("Ya no hay más resultados. ¿Ajustamos presupuesto o marca/modelo?")

        remaining = total - new_offset
        step = min(max(step, 1), remaining)

        page_cars = search_cars(base_filters, limit=step, offset=new_offset)

        # 🔁 mapping de índice visible → id real (numeración continua)
        base_index = new_offset + 1
        page_map = LAST_PAGE.get(channel, {})
        for idx, it in enumerate(page_cars, start=base_index):
            page_map[idx] = str(it.get("id"))
        LAST_PAGE[channel] = page_map

        LAST_OFFSET[channel] = new_offset
        LAST_LIMIT[channel]  = step

        return retrieve_cars(base_filters, offset=new_offset, limit=step)

    # ---------- 2) INTENT: finanzas / KB / ayuda ----------
    intent = _detect_intent(raw)

    if intent in ("greet", "help"):
        return WELCOME_MSG

    if intent == "finance":
        price = parse_numeric(re.search(r"(\$?\s*[0-9][0-9,\.]+)", raw).group(0)) if re.search(r"(\$?\s*[0-9][0-9,\.]+)", raw) else None
        down  = None
        if m := re.search(r"(?:enganche\s*de|con)\s*([\$0-9\.,]+k|[\$0-9\.,]+|[0-9]+\s*mil)", raw, flags=re.I):
            down = _parse_money(m.group(1))
        if price is None or down is None:
            return ("Para cotizar necesito *precio* y *enganche*. "
                    "Puedes decir: `cotiza 323668 con 40k` o `mensualidades de $350,000 con 50k`.")
        plan = finance_plan(price=float(price), down_payment=float(down))
        lines = [f"Precio ${int(price):,} • Enganche ${int(down):,}"]
        lines += [f"- {p['term_months']} meses: ${p['monthly']:,.0f}" for p in plan["plans"]]
        return "*Mensualidades aproximadas:*\n" + "\n".join(lines)

    if intent == "kb":
        return kb_tool(raw)

    # ---------- 3) BÚSQUEDA (por defecto) ----------
    # ¿Es una petición de paginación? (ver más N)
    
    # Si llegamos aquí y NO hay señales de búsqueda, muestra menú (evita listar por “hola”)
    if intent != "search":
        return WELCOME_MSG
    
    m_pag = PAGINATE_RE.search(raw)
    if m_pag:
        # 1) Cuántos quiere ver ahora (si no pone número, usa el último tamaño o 5)
        step = int(m_pag.group(2)) if m_pag.group(2) else LAST_LIMIT.get(channel, 5)

        base_filters = LAST_FILTERS.get(channel)
        if not base_filters:
            return "No tengo una búsqueda previa para continuar. Dime qué estás buscando."

        # 2) Avanza desde lo ya mostrado (offset previo + tamaño previo)
        prev_offset = LAST_OFFSET.get(channel, 0)
        prev_limit  = LAST_LIMIT.get(channel, 5)
        new_offset  = prev_offset + prev_limit

        # 3) Límite por lo que realmente queda
        total = search_cars_count(base_filters)
        if new_offset >= total:
            return ("No encontré más resultados con esos filtros. "
                    "Ya no hay más resultados. ¿Ajustamos presupuesto o marca/modelo?")
        remaining = total - new_offset
        step = min(max(step, 1), remaining)

        # 4) Guarda la página que vas a mostrar (para mapear 1..N → ID)
        try:
            page_cars = search_cars(base_filters, limit=step, offset=new_offset)
        except Exception:
            page_cars = []
        LAST_PAGE[channel] = page_cars

        # 5) Actualiza estado y devuelve el texto renderizado
        LAST_OFFSET[channel] = new_offset
        LAST_LIMIT[channel]  = step
        return retrieve_cars(base_filters, offset=new_offset, limit=step)

    # ---- Nueva búsqueda o refinamiento ----
    # Mezcla: partimos de los filtros previos (si existían) y sobre-escribimos con lo que el usuario dijo hoy
    base_filters: Dict[str, Any] = LAST_FILTERS.get(channel, {}).copy()
    filters: Dict[str, Any] = {"raw_text": raw}

    # Heurística: si el texto suena a *búsqueda nueva*,
    # NO reutilizamos filtros previos (evita que se cuele un precio viejo, etc.)
    is_new_search = bool(re.search(r"\b(busco|buscar|quiero|necesito|recomienda|mu[eé]strame)\b", t))
    has_year      = bool(re.search(r"(19|20)\d{2}", t))
    has_brand     = any(mk in t for mk in ["nissan","toyota","volkswagen","ford","chevrolet","kia","honda",
                                        "bmw","mercedes benz","mazda","renault","hyundai"])
    # Si detectas versión/modelo explícitos en tu parser, puedes sumar más señales:
    has_version   = bool(re.search(r"\b(sense|advance|exclusive|active|trend|highline|comfortline|xlt|xl|limited|lt|ls|xle|xse|sport|platinum|sr|sv|sl)\b", t))

    if is_new_search or has_year or has_brand or has_version:
        base_filters = {}  # reset duro: no arrastrar estado previo
    else:
        base_filters = LAST_FILTERS.get(channel, {}).copy()

    # Normaliza las palabras sinónimas
    ni = normalize_intent(raw)
    # Si el usuario dice "usado", "pocos km", "con poco uso" → fijamos km_max
    if ni.get("km") in {
        "usado", "usada", "usados", "usadas",
        "pocos km", "poco km", "con poco uso"
    }:
        if "km_max" not in filters:
            filters["km_max"] = 100_000

    # Año mínimo
    if m := re.search(r"(19|20)\d{2}", t):
        try:
            filters["year_min"] = int(m.group(0))
        except Exception:
            pass

    # Rangos/ límites de precio
    m_range = RANGO_PRECIOS_RE.search(raw)
    if m_range:
        v1 = _parse_money(m_range.group(1))
        v2 = _parse_money(m_range.group(2))
        lo, hi = (min(v1, v2), max(v1, v2))
        if lo > 0: filters["price_min"] = lo
        if hi > 0: filters["price_max"] = hi
    else:
        pmin, pmax = _extract_price_bounds(raw)
        if pmin: filters["price_min"] = pmin
        if pmax: filters["price_max"] = pmax

    # Marca explícita (lock real lo hace search_cars con fuzzy)
    for mk in ["nissan","toyota","volkswagen","ford","chevrolet","kia","honda",
            "bmw","mercedes benz","mazda","renault","hyundai"]:
        if mk in t:
            filters["brand"] = mk
            break

    # Versión explícita (tokens típicos)
    for ver in ["sense","advance","exclusive","lt","ls","sr","le","xe","xl"]:
        if f" {ver} " in f" {t} ":
            filters["version"] = ver
            break

    VERSION_TOKENS = {
        "sense", "advance", "exclusive", "active", "trend", "highline",
        "comfortline", "xlt", "xl", "limited", "lt", "ls", "xle", "xse",
        "sport", "platinum", "sr", "sv", "sl"
    }
    has_version_token = any(tok in t for tok in VERSION_TOKENS)

    if has_version_token and "model" not in filters:
        MODEL_TOKENS = ["versa","sentra","march","kicks","altima","note","x-trail","xtrail","x trail","pathfinder","murano"]
        for mtok in MODEL_TOKENS:
            if mtok in t:
                filters["model"] = mtok
                break

    # Quitar filtros en el mismo mensaje (quita precio / año / marca / modelo / km)
    filters = _apply_remove_filters(filters, raw)

    # Merge con lo previo (para no perder marca/modelo/… al refinar)
    merged = base_filters.copy()
    merged.update({k: v for k, v in filters.items() if v is not None})
    filters = merged

    # Nueva búsqueda empieza en offset 0; guardamos estado para “ver más”
    to_save = dict(filters)
    to_save["raw_text"] = ""     # evita re-inferencias en la siguiente página
    LAST_FILTERS[channel] = to_save
    LAST_OFFSET[channel]  = 0
    LAST_LIMIT[channel]   = 5    # tamaño por defecto de página

    # Guarda la primera página mostrada (mapping índice visible → ID real)
    try:
        first_page = search_cars(filters, limit=5, offset=0)
    except Exception:
        first_page = []

    page_map = {}
    for idx, it in enumerate(first_page, start=1):  # visible 1..5
        page_map[idx] = str(it.get("id"))
    LAST_PAGE[channel] = page_map

    return retrieve_cars(filters, offset=0, limit=5)
