import pandas as pd
import os

path = r"app\data\catalog.csv"
df = pd.read_csv(path)  # si usa ; pon: pd.read_csv(path, sep=";")

rename_map = {
    "stock_id": "id",
    "make": "brand",
    "model": "model",
    "year": "year",
    "km": "km",
    "price": "price",
}

df = df.rename(columns=rename_map)

if "location" not in df.columns:
    df["location"] = "Online"

required = ["id","brand","model","year","km","price","location"]
missing = [c for c in required if c not in df.columns]
if missing:
    raise SystemExit(f"❌ Faltan columnas después del mapeo: {missing}")

df = df[required]
df.to_csv(path, index=False)

print("✅ catalog.csv normalizado:", os.path.abspath(path))
print("✅ Columnas:", list(df.columns))
print("✅ Filas:", len(df))
