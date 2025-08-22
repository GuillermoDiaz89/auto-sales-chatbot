# app/router.py
from typing import Dict, Any, List
from app.nlp.tools import search_cars, search_cars_count

def _fmt_mxn(x) -> str:
    return f"${int(float(x)):,}"

def _fmt_km(x) -> str:
    return f"{int(float(x)):,} km"

def _format_car(c: Dict[str, Any]) -> str:
    ver = str(c.get("version") or "").strip()
    ver_part = f" {ver}" if ver else ""
    return (
        f"*#{c['id']} {c['brand']} {c['model']}{ver_part} {int(c['year'])}*\n"
        f"{_fmt_km(c['km'])} • {_fmt_mxn(c['price'])} • {c.get('location','Online')}"
    )

# ---------- NUEVO: chips/encabezado compacto ----------
def _chips_from_filters(f: Dict[str, Any]) -> str:
    chips: List[str] = []
    if f.get("brand"):   chips.append(str(f["brand"]).title())
    if f.get("model"):   chips.append(str(f["model"]).title())
    if f.get("version"): chips.append(str(f["version"]).title())

    y_min = f.get("year_min"); y_max = f.get("year_max")
    if y_min and not y_max:    chips.append(f"año desde {int(y_min)}")
    elif y_max and not y_min:  chips.append(f"hasta {int(y_max)}")
    elif y_min and y_max:      chips.append(f"{int(y_min)}–{int(y_max)}")

    if f.get("price_min"): chips.append(f"desde {_fmt_mxn(f['price_min'])}")
    if f.get("price_max"): chips.append(f"hasta {_fmt_mxn(f['price_max'])}")

    if f.get("km_max"): chips.append(f"hasta {int(f['km_max']):,} km")

    return "Todos los autos" if not chips else " • ".join(chips)

# ---------- NUEVO: tarjeta numerada con CTA ----------
def _format_card(idx: int, c: Dict[str, Any]) -> str:
    ver = str(c.get("version") or "").strip()
    ver_part = f" {ver}" if ver else ""
    title = f"{c['brand']} {c['model']}{ver_part} {int(c['year'])}".strip()
    line1 = f"{idx}) {title} — {_fmt_mxn(c['price'])}"
    line2 = f"   {_fmt_km(c.get('km', 0))} • {c.get('location','Online')} • ID {c['id']}"
    line3 = f"   Acciones: cotiza {idx} con 40k · detalles {idx}"
    return "\n".join([line1, line2, line3])

def _format_filters(filters: Dict[str, Any]) -> str:
    chips = []
    if filters.get("brand"):
        chips.append(f"marca={str(filters['brand']).title()}")
    if filters.get("model"):
        chips.append(f"modelo={str(filters['model']).title()}")
    if filters.get("version"):
        chips.append(f"versión={str(filters['version']).title()}")
    if filters.get("year_min"):
        chips.append(f"año≥{int(filters['year_min'])}")
    if filters.get("year_max"):
        chips.append(f"año≤{int(filters['year_max'])}")
    if filters.get("price_min"):
        chips.append(f"precio≥${int(float(filters['price_min'])):,.0f}")
    if filters.get("price_max"):
        chips.append(f"precio≤${int(float(filters['price_max'])):,.0f}")
    if filters.get("km_max"):
        chips.append(f"km≤{int(filters['km_max']):,}")
    return "*Filtros:* " + ", ".join(chips) if chips else "*Filtros:* (sin filtros)"

def retrieve_cars(filters: Dict[str, Any], offset: int = 0, limit: int = 5) -> str:
    """
    Construye el mensaje de respuesta UX-friendly con encabezado tipo chips y paginación.
    - offset/limit permiten 'ver más N'
    """
    total_count = search_cars_count(filters)

    # 1) Sin resultados
    if total_count == 0:
        chips = _chips_from_filters(filters)
        msg = f"🔎 Búsqueda: {chips}   |   0 resultados\n\n"
        msg += "No encontré autos con esos criterios."
        if filters.get("price_max"):
            msg += f" No hay unidades por debajo de {_fmt_mxn(filters['price_max'])}."
        return msg + "\n¿Ajustamos presupuesto o marca/modelo?"

    # 2) Offset fuera de rango
    if offset >= total_count:
        chips = _chips_from_filters(filters)
        return (
            f"🔎 Búsqueda: {chips}   |   {total_count} resultados\n\n"
            "Ya no hay más resultados. Puedes ajustar la búsqueda (ej. *≤$350,000* o *Nissan 2021*)."
        )

    # 3) Página solicitada
    cars = search_cars(filters, limit=limit, offset=offset)  # lista de dicts

    # Echo de marca/modelo/versión si todos coinciden (ayuda a formar chips)
    if cars and not filters.get("brand"):
        brands_set = {c["brand"] for c in cars}
        if len(brands_set) == 1:
            filters["brand"] = next(iter(brands_set))
    if cars and not filters.get("model"):
        models_set = {c["model"] for c in cars}
        if len(models_set) == 1:
            filters["model"] = next(iter(models_set))
    if cars and not filters.get("version"):
        versions_set = {str(c.get("version") or "").strip().lower() for c in cars}
        versions_set.discard("")
        if len(versions_set) == 1:
            filters["version"] = next(iter(versions_set))

    # 4) Seguridad: página vacía
    if not cars:
        chips = _chips_from_filters(filters)
        msg = f"🔎 Búsqueda: {chips}   |   {total_count} resultados\n\n"
        msg += "No encontré autos en esta página. Intenta con otros filtros."
        return msg

    # 5) Título/encabezado
    shown_now = len(cars)
    shown_total = min(offset + shown_now, total_count)
    remaining = max(total_count - shown_total, 0)
    chips = _chips_from_filters(filters)
    header = f"🔎 Búsqueda: {chips}   |   {total_count} resultado{'s' if total_count != 1 else ''}\n\n*Te recomiendo:*"

    # 6) Cuerpo numerado (1..N de la página)
    body_lines: List[str] = [header, ""]
    for i, car in enumerate(cars, start=1):
        body_lines.append(_format_card(i, car))
        body_lines.append("")  # salto

    # 7) Footer con call-to-action claro
    if remaining > 0:
        sugeridos = min(remaining, 5)
        body_lines.append(f"Ver {sugeridos} más: escribe `ver {sugeridos} más`  (quedan {remaining}).")
    else:
        body_lines.append("No hay más resultados para mostrar. ¿Ajustamos la búsqueda (precio, año, marca/modelo)?")

    # 8) Cierre de cotización
    body_lines.append(
        "Para cotizar: `cotiza <número de opción> con 40 mil pesos` o `cotiza <ID del auto> con 40 mil pesos`."
    )

    return "\n".join(body_lines)