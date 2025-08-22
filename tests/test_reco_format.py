from app.reco.catalog import Recommender

def test_format_from_text_nissan(tmp_path):
    path = r"C:\Users\Guillermo\OneDrive\Documents\kavak-agent\kavak-agent\app\data\catalog.csv"
    reco = Recommender(path)

    out = reco.format_from_text("busco nisan por menos de 300 mil")
    # Debe empezar con "Te recomiendo:"
    assert out.startswith("Te recomiendo:")

    # Debe contener precios formateados con $
    assert "Nissan" in out
    assert "$" in out
