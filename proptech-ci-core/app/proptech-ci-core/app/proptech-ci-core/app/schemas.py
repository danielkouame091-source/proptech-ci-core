from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

MODES_PAIEMENT = ("especes", "wave", "orange_money", "mtn_money", "virement")


# ---------- Biens ----------
class BienBase(BaseModel):
    titre: str = Field(min_length=3, max_length=150)
    type_bien: str
    commune: str
    quartier: Optional[str] = None
    adresse: Optional[str] = None
    loyer_mensuel: float = Field(gt=0)


class BienCreate(BienBase):
    pass


class BienUpdate(BaseModel):
    titre: Optional[str] = None
    type_bien: Optional[str] = None
    commune: Optional[str] = None
    quartier: Optional[str] = None
    adresse: Optional[str] = None
    loyer_mensuel: Optional[float] = Field(default=None, gt=0)
    disponible: Optional[bool] = None


class BienOut(BienBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    disponible: bool


# ---------- Locataires ----------
class LocataireCreate(BaseModel):
    nom: str = Field(min_length=2)
    prenoms: str = Field(min_length=2)
    telephone: str = Field(min_length=8, max_length=20)
    piece_identite: Optional[str] = None


class LocataireOut(LocataireCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Baux ----------
class BailCreate(BaseModel):
    bien_id: int
    locataire_id: int
    date_debut: date
    date_fin: Optional[date] = None
    loyer_mensuel: Optional[float] = Field(default=None, gt=0)  # sinon loyer du bien
    caution: float = Field(default=0, ge=0)


class BailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    bien_id: int
    locataire_id: int
    date_debut: date
    date_fin: Optional[date]
    loyer_mensuel: float
    caution: float
    statut: str


# ---------- Paiements ----------
class PaiementCreate(BaseModel):
    bail_id: int
    montant: float = Field(gt=0)
    mois_concerne: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    mode: str
    reference: Optional[str] = None


class PaiementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    bail_id: int
    montant: float
    mois_concerne: str
    mode: str
    reference: Optional[str]
    date_paiement: datetime
