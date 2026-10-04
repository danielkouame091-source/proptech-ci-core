from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def test_parcours_complet():
    bien = client.post("/biens/", json={
        "titre": "Appartement F3 Cocody", "type_bien": "appartement",
        "commune": "Cocody", "loyer_mensuel": 250000,
    }).json()
    loc = client.post("/locataires/", json={
        "nom": "Kouassi", "prenoms": "Aya", "telephone": "0707070707",
    }).json()

    r = client.post("/baux/", json={
        "bien_id": bien["id"], "locataire_id": loc["id"],
        "date_debut": "2026-10-01", "caution": 500000,
    })
    assert r.status_code == 201
    bail = r.json()

    # le bien n'est plus disponible
    assert client.post("/baux/", json={
        "bien_id": bien["id"], "locataire_id": loc["id"], "date_debut": "2026-10-01",
    }).status_code == 409

    p = client.post("/paiements/", json={
        "bail_id": bail["id"], "montant": 250000,
        "mois_concerne": "2026-10", "mode": "wave",
    })
    assert p.status_code == 201
    assert client.get("/stats").json()["total_encaisse_fcfa"] == 250000

    assert client.post(f"/baux/{bail['id']}/resilier").json()["statut"] == "resilie"
    assert client.get(f"/biens/{bien['id']}").json()["disponible"] is True
