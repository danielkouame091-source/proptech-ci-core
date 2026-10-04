from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/biens", tags=["Biens"])


@router.post("/", response_model=schemas.BienOut, status_code=201)
def creer_bien(data: schemas.BienCreate, db: Session = Depends(get_db)):
    bien = models.Bien(**data.model_dump())
    db.add(bien)
    db.commit()
    db.refresh(bien)
    return bien


@router.get("/", response_model=list[schemas.BienOut])
def lister_biens(
    commune: Optional[str] = None,
    disponible: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Bien)
    if commune:
        q = q.filter(models.Bien.commune.ilike(commune))
    if disponible is not None:
        q = q.filter(models.Bien.disponible == disponible)
    return q.order_by(models.Bien.id).all()


@router.get("/{bien_id}", response_model=schemas.BienOut)
def lire_bien(bien_id: int, db: Session = Depends(get_db)):
    bien = db.get(models.Bien, bien_id)
    if not bien:
        raise HTTPException(404, "Bien introuvable")
    return bien


@router.put("/{bien_id}", response_model=schemas.BienOut)
def modifier_bien(bien_id: int, data: schemas.BienUpdate, db: Session = Depends(get_db)):
    bien = db.get(models.Bien, bien_id)
    if not bien:
        raise HTTPException(404, "Bien introuvable")
    for champ, valeur in data.model_dump(exclude_unset=True).items():
        setattr(bien, champ, valeur)
    db.commit()
    db.refresh(bien)
    return bien


@router.delete("/{bien_id}", status_code=204)
def supprimer_bien(bien_id: int, db: Session = Depends(get_db)):
    bien = db.get(models.Bien, bien_id)
    if not bien:
        raise HTTPException(404, "Bien introuvable")
    if bien.baux:
        raise HTTPException(409, "Ce bien a des baux : suppression impossible")
    db.delete(bien)
    db.commit()
