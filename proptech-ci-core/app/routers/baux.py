from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/baux", tags=["Baux"])


@router.post("/", response_model=schemas.BailOut, status_code=201)
def creer_bail(data: schemas.BailCreate, db: Session = Depends(get_db)):
    bien = db.get(models.Bien, data.bien_id)
    if not bien:
        raise HTTPException(404, "Bien introuvable")
    if not bien.disponible:
        raise HTTPException(409, "Ce bien n'est pas disponible")
    if not db.get(models.Locataire, data.locataire_id):
        raise HTTPException(404, "Locataire introuvable")
    if data.date_fin and data.date_fin <= data.date_debut:
        raise HTTPException(422, "date_fin doit être après date_debut")

    bail = models.Bail(
        bien_id=data.bien_id,
        locataire_id=data.locataire_id,
        date_debut=data.date_debut,
        date_fin=data.date_fin,
        loyer_mensuel=data.loyer_mensuel or bien.loyer_mensuel,
        caution=data.caution,
    )
    bien.disponible = False
    db.add(bail)
    db.commit()
    db.refresh(bail)
    return bail


@router.get("/", response_model=list[schemas.BailOut])
def lister_baux(db: Session = Depends(get_db)):
    return db.query(models.Bail).order_by(models.Bail.id).all()


@router.get("/{bail_id}", response_model=schemas.BailOut)
def lire_bail(bail_id: int, db: Session = Depends(get_db)):
    bail = db.get(models.Bail, bail_id)
    if not bail:
        raise HTTPException(404, "Bail introuvable")
    return bail


@router.post("/{bail_id}/resilier", response_model=schemas.BailOut)
def resilier_bail(bail_id: int, db: Session = Depends(get_db)):
    bail = db.get(models.Bail, bail_id)
    if not bail:
        raise HTTPException(404, "Bail introuvable")
    if bail.statut != "actif":
        raise HTTPException(409, "Bail déjà résilié")
    bail.statut = "resilie"
    bail.bien.disponible = True
    db.commit()
    db.refresh(bail)
    return bail
