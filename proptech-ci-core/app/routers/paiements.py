from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/paiements", tags=["Paiements"])


@router.post("/", response_model=schemas.PaiementOut, status_code=201)
def enregistrer_paiement(data: schemas.PaiementCreate, db: Session = Depends(get_db)):
    if data.mode not in schemas.MODES_PAIEMENT:
        raise HTTPException(422, f"Mode invalide. Choix : {', '.join(schemas.MODES_PAIEMENT)}")
    bail = db.get(models.Bail, data.bail_id)
    if not bail:
        raise HTTPException(404, "Bail introuvable")
    if bail.statut != "actif":
        raise HTTPException(409, "Bail résilié : paiement refusé")
    paiement = models.Paiement(**data.model_dump())
    db.add(paiement)
    db.commit()
    db.refresh(paiement)
    return paiement


@router.get("/", response_model=list[schemas.PaiementOut])
def lister_paiements(bail_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.Paiement)
    if bail_id:
        q = q.filter(models.Paiement.bail_id == bail_id)
    return q.order_by(models.Paiement.id).all()
