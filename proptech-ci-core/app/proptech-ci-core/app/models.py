from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class Bien(Base):
    __tablename__ = "biens"

    id = Column(Integer, primary_key=True, index=True)
    titre = Column(String(150), nullable=False)
    type_bien = Column(String(50), nullable=False)  # appartement, villa, studio, magasin...
    commune = Column(String(80), nullable=False)    # Cocody, Yopougon, Bouaké...
    quartier = Column(String(80))
    adresse = Column(String(255))
    loyer_mensuel = Column(Float, nullable=False)   # en FCFA
    disponible = Column(Boolean, default=True, nullable=False)

    baux = relationship("Bail", back_populates="bien")


class Locataire(Base):
    __tablename__ = "locataires"

    id = Column(Integer, primary_key=True, index=True)
    nom = Column(String(80), nullable=False)
    prenoms = Column(String(120), nullable=False)
    telephone = Column(String(20), nullable=False, unique=True)
    piece_identite = Column(String(50))

    baux = relationship("Bail", back_populates="locataire")


class Bail(Base):
    __tablename__ = "baux"

    id = Column(Integer, primary_key=True, index=True)
    bien_id = Column(Integer, ForeignKey("biens.id"), nullable=False)
    locataire_id = Column(Integer, ForeignKey("locataires.id"), nullable=False)
    date_debut = Column(Date, nullable=False)
    date_fin = Column(Date)
    loyer_mensuel = Column(Float, nullable=False)
    caution = Column(Float, default=0, nullable=False)
    statut = Column(String(20), default="actif", nullable=False)  # actif | resilie

    bien = relationship("Bien", back_populates="baux")
    locataire = relationship("Locataire", back_populates="baux")
    paiements = relationship("Paiement", back_populates="bail")


class Paiement(Base):
    __tablename__ = "paiements"

    id = Column(Integer, primary_key=True, index=True)
    bail_id = Column(Integer, ForeignKey("baux.id"), nullable=False)
    montant = Column(Float, nullable=False)
    mois_concerne = Column(String(7), nullable=False)  # format AAAA-MM
    mode = Column(String(30), nullable=False)          # especes, wave, orange_money, mtn_money, virement
    reference = Column(String(100))
    date_paiement = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    bail = relationship("Bail", back_populates="paiements")
