import os

# Tasa anual fija definida por Kavak
KAVAK_ANNUAL_RATE = float(os.getenv("KAVAK_ANNUAL_RATE", "0.10"))  # 10% anual por defecto

# Plazos permitidos (meses)
ALLOWED_TERMS = [36, 48, 60, 72]
DEFAULT_TERM = 48
