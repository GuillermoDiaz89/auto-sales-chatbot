
from app.nlp.tools import monthly_payment, finance_plan

def test_monthly_payment_basic():
    m = monthly_payment(250000, 50000, 48, annual_rate=0.10)
    assert m > 0

def test_finance_plan_terms():
    plan = finance_plan(200000, 20000, terms=(36,48), annual_rate=0.10)
    assert len(plan["plans"]) == 2
