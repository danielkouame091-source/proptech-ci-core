# app/main.py
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine
from app import models
from app.security_vpn import security_middleware
from app.geolocation import require_cote_divoire_geolocation, GeoCoordinates
from app.analytics_ai import (
    generer_rapport_fondateur,
    generer_rapport_alertes_fraude,
    generer_rapport_artisans,
)

# Création des tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="PropTech CI Core API")

# Enregistrement du middleware de sécurité
app.middleware("http")(security_middleware)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def read_root():
    return {"message": "Bienvenue sur l'API PropTech CI Core"}


# ── Routes de géolocalisation ──
@app.post("/signer-terrain")
async def signer_terrain(
    geo: GeoCoordinates,
    validation: dict = Depends(require_cote_divoire_geolocation),
    db: Session = Depends(get_db),
):
    # Log la validation en base
    log = models.GeoLog(
        latitude=geo.latitude,
        longitude=geo.longitude,
        accuracy=geo.accuracy,
        is_valid=True,
        is_mocked=False,
        reason="Localisation validée",
        nearest_city=validation.get("nearest_city"),
    )
    db.add(log)
    db.commit()
    return {"message": "Terrain signé avec succès", "localisation_validee": validation}


# ── Routes de rapports admin ──
@app.get("/admin/rapport-fondateur")
def rapport_fondateur(periode_jours: int = 30, db: Session = Depends(get_db)):
    return generer_rapport_fondateur(db, periode_jours)


@app.get("/admin/rapport-alertes-fraude")
def rapport_alertes(periode_jours: int = 30, db: Session = Depends(get_db)):
    return generer_rapport_alertes_fraude(db, periode_jours)


@app.get("/admin/rapport-artisans")
def rapport_artisans(periode_jours: int = 90, db: Session = Depends(get_db)):
    return generer_rapport_artisans(db, periode_jours)
