from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/locataires", tags=["Locataires"])


@router.post("/", response_model=schemas.LocataireOut, status_code=201)
def creer_locataire(data: schemas.LocataireCreate, db: Session = Depends(get_db)):
    existe = db.query(models.Locataire).filter_by(telephone=data.telephone).first()
    if existe:
        raise HTTPException(409, "Ce numéro de téléphone existe déjà")
    loc = models.Locataire(**data.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@router.get("/", response_model=list[schemas.LocataireOut])
def lister_locataires(db: Session = Depends(get_db)):
    return db.query(models.Locataire).order_by(models.Locataire.id).all()


@router.get("/{locataire_id}", response_model=schemas.LocataireOut)
def lire_locataire(locataire_id: int, db: Session = Depends(get_db)):
    loc = db.get(models.Locataire, locataire_id)
    if not loc:
        raise HTTPException(404, "Locataire introuvable")
    return loc
