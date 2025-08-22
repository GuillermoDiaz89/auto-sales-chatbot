# app/nlp/aliases.py

# Alias comunes por si el usuario escribe abreviado o con marcas coloquiales
BRAND_ALIAS = {
    "vw": "volkswagen",
    "vokswagen": "volkswagen",
    "mercedes": "mercedes benz",
    "mercedes-benz": "mercedes benz",
    "mercedesbenz": "mercedes benz",
    "chevy": "chevrolet",
    "bmv": "bmw",
    # Nissan typos comunes
    "nisan": "nissan",
    "nizan": "nissan",
    "nisaan": "nissan",
    "nizzan": "nissan",
    "niisan": "nissan",
    "nisssan": "nissan",
    # otros
    "toyoya": "toyota",
    "hunday": "hyundai",
}

# Alias / typos comunes de modelos
MODEL_ALIAS = {
    # Nissan
    "kix": "kicks",
    "kick": "kicks",
    "xtrail": "x-trail",
    "extrail": "x-trail",
    "estrail": "x-trail",
    "x trail": "x-trail",
    "sentar": "sentra",
    "sentrea": "sentra",
    "verzza": "versa",
    "verssa": "versa",
    # Otras marcas (ejemplos)
    "corola": "corolla",
    "forte": "forte",
    "clasea": "clase a",
}

# Alias / typos comunes de versiones
VERSION_ALIAS = {
    "sense": "sense",
    "advance": "advance",
    "exclusive": "exclusive",
    "lt": "lt", "ls": "ls", "sr": "sr", "le": "le", "xe": "xe", "xl": "xl",
}

# Stopwords para limpieza de tokens en búsqueda por texto libre
STOPWORDS = {
    "busco", "buscar", "un", "una", "por", "de", "mas", "más", "menos", "hasta",
    "desde", "quiero", "necesito", "auto", "carro", "coche", "barato", "semineuvo", "seminuevo"
}
