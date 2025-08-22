
from pydantic import BaseModel, Field
from typing import Optional

class ChatRequest(BaseModel):
    text: str = Field(..., description="User message text")

class CarFilters(BaseModel):
    brand: Optional[str] = None
    model: Optional[str] = None
    price_max: Optional[float] = None
    year_min: Optional[int] = None
    km_max: Optional[int] = None

class FinanceRequest(BaseModel):
    price: float
    down_payment: float = 0.0
    term_months: int = 48
    annual_rate: Optional[float] = None

class Car(BaseModel):
    id: str
    brand: str
    model: str
    year: int
    km: int
    price: float
    location: str
