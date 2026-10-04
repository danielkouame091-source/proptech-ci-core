from fastapi import Depends, FastAPI
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .routers import baux, biens, locataires, paiements

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PropTech CI Core", version="0.1.0")

app.include_router(biens.router)
app.include_router(locataires.router)
app.include_router(baux.router)
app.include_router(paiements.router)


@app.get("/", tags=["Général"])
def accueil():
    return {"app": "PropTech CI Core", "docs": "/docs"}


@app.get("/stats", tags=["Général"])
def stats(db: Session = Depends(get_db)):
    total_encaisse = db.query(func.coalesce(func.sum(models.Paiement.montant), 0)).scalar()
    return {
        "biens_total": db.query(models.Bien).count(),
        "biens_disponibles": db.query(models.Bien).filter_by(disponible=True).count(),
        "baux_actifs": db.query(models.Bail).filter_by(statut="actif").count(),
        "total_encaisse_fcfa": total_encaisse,
    }
