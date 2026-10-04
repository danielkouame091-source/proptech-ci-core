"""
Module de séquestre financier et anti-double vente.
Gère le blocage des fonds dans un compte Escrow, le gel automatique des biens
pendant 3 jours, et la libération progressive des fonds pour les artisans.
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, List, Dict, Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.models import User, Property, EscrowAccount, Transaction, EscrowStatus, PropertyStatus
from app.database import SessionLocal

# Configuration du logger
escrow_logger = logging.getLogger("escrow_service")

# Durée de gel automatique d'un bien (en jours)
GEL_DUREE_JOURS = 3


class EscrowError(Exception):
    """Exception levée pour les erreurs du service de séquestre."""
    pass


def get_db():
    """Fournit une session de base de données."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────
# GESTION DU GEL ANTI-DOUBLE VENTE
# ──────────────────────────────────────────────────────────────

def geler_bien_pour_negociation(
    db: Session,
    property_id: int,
    buyer_id: int,
    duree_jours: int = GEL_DUREE_JOURS
) -> Property:
    """
    Gèle un bien pendant N jours dès qu'une négociation est initiée.
    Empêche la double vente en bloquant le bien pour les autres acheteurs.

    Règles :
    - Le bien doit être disponible (statut AVAILABLE).
    - Le bien ne doit pas être déjà gelé ou vendu.
    - Le gel est automatique et dure 3 jours par défaut.
    """
    # Récupérer le bien
    bien = db.query(Property).filter(Property.id == property_id).first()
    if not bien:
        raise EscrowError(f"Bien introuvable : id={property_id}")

    # Vérifier le statut du bien
    if bien.status == PropertyStatus.SOLD:
        raise EscrowError("Ce bien est déjà vendu.")

    if bien.status == PropertyStatus.FROZEN:
        # Vérifier si le gel a expiré
        if bien.frozen_until and bien.frozen_until > datetime.now(timezone.utc):
            raise EscrowError(
                f"Ce bien est déjà gelé jusqu'au {bien.frozen_until.isoformat()}"
            )
        # Le gel a expiré, on peut le réactiver
        escrow_logger.info(f"Gel expiré pour le bien {property_id}, réactivation.")

    # Geler le bien
    now = datetime.now(timezone.utc)
    bien.status = PropertyStatus.FROZEN
    bien.frozen_until = now + timedelta(days=duree_jours)
    bien.frozen_by_buyer_id = buyer_id
    bien.updated_at = now

    db.add(bien)
    db.commit()
    db.refresh(bien)

    escrow_logger.info(
        f"Bien {property_id} gelé pour l'acheteur {buyer_id} "
        f"jusqu'au {bien.frozen_until.isoformat()}"
    )
    return bien


def verifier_gel_bien(db: Session, property_id: int) -> Dict[str, Any]:
    """
    Vérifie si un bien est gelé et si le gel est toujours actif.
    """
    bien = db.query(Property).filter(Property.id == property_id).first()
    if not bien:
        raise EscrowError(f"Bien introuvable : id={property_id}")

    now = datetime.now(timezone.utc)
    is_frozen = (
        bien.status == PropertyStatus.FROZEN
        and bien.frozen_until is not None
        and bien.frozen_until > now
    )

    return {
        "property_id": property_id,
        "is_frozen": is_frozen,
        "frozen_until": bien.frozen_until.isoformat() if bien.frozen_until else None,
        "frozen_by_buyer_id": bien.frozen_by_buyer_id,
        "status": bien.status.value if bien.status else None,
    }


# ──────────────────────────────────────────────────────────────
# GESTION DU SÉQUESTRE FINANCIER (ESCROW)
# ──────────────────────────────────────────────────────────────

def creer_escrow(
    db: Session,
    buyer_id: int,
    property_id: int,
    amount: float,
    currency: str = "XOF"
) -> EscrowAccount:
    """
    Crée un compte séquestre pour une transaction immobilière.
    Bloque les fonds de l'acheteur.
    """
    # Vérifier l'acheteur
    buyer = db.query(User).filter(User.id == buyer_id).first()
    if not buyer:
        raise EscrowError(f"Acheteur introuvable : id={buyer_id}")

    # Vérifier le bien
    bien = db.query(Property).filter(Property.id == property_id).first()
    if not bien:
        raise EscrowError(f"Bien introuvable : id={property_id}")

    # Vérifier que le bien est gelé pour cet acheteur
    if bien.frozen_by_buyer_id != buyer_id:
        raise EscrowError("Ce bien n'est pas gelé pour cet acheteur.")

    # Vérifier le solde de l'acheteur (simulation)
    if buyer.balance < amount:
        raise EscrowError("Solde insuffisant pour créer le séquestre.")

    # Créer le compte escrow
    escrow = EscrowAccount(
        buyer_id=buyer_id,
        seller_id=bien.owner_id,
        property_id=property_id,
        amount=amount,
        currency=currency,
        status=EscrowStatus.LOCKED,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

    # Débiter le compte de l'acheteur
    buyer.balance -= amount

    db.add(escrow)
    db.add(buyer)
    db.commit()
    db.refresh(escrow)

    escrow_logger.info(
        f"Escrow créé : id={escrow.id}, montant={amount} {currency}, "
        f"acheteur={buyer_id}, bien={property_id}"
    )
    return escrow


def liberer_fonds_progressifs(
    db: Session,
    escrow_id: int,
    artisan_id: int,
    montant: float,
    description: str = ""
) -> Transaction:
    """
    Libère progressivement des fonds du séquestre vers un artisan.
    Utilisé pour payer les artisans au fur et à mesure de l'avancement des travaux.
    """
    escrow = db.query(EscrowAccount).filter(EscrowAccount.id == escrow_id).first()
    if not escrow:
        raise EscrowError(f"Escrow introuvable : id={escrow_id}")

    if escrow.status != EscrowStatus.LOCKED:
        raise EscrowError(
            f"Impossible de libérer des fonds : statut actuel = {escrow.status.value}"
        )

    if montant <= 0:
        raise EscrowError("Le montant à libérer doit être positif.")

    if escrow.amount < montant:
        raise EscrowError(
            f"Montant insuffisant dans le séquestre. "
            f"Disponible : {escrow.amount}, demandé : {montant}"
        )

    # Vérifier l'artisan
    artisan = db.query(User).filter(User.id == artisan_id).first()
    if not artisan:
        raise EscrowError(f"Artisan introuvable : id={artisan_id}")

    # Créer la transaction
    transaction = Transaction(
        escrow_id=escrow_id,
        artisan_id=artisan_id,
        amount=montant,
        description=description,
        status="completed",
        created_at=datetime.now(timezone.utc)
    )

    # Mettre à jour le solde de l'escrow
    escrow.amount -= montant
    escrow.updated_at = datetime.now(timezone.utc)

    # Créditer l'artisan
    artisan.balance += montant

    db.add(transaction)
    db.add(escrow)
    db.add(artisan)
    db.commit()
    db.refresh(transaction)

    escrow_logger.info(
        f"Fonds libérés : escrow={escrow_id}, artisan={artisan_id}, "
        f"montant={montant}, reste={escrow.amount}"
    )
    return transaction


def valider_transaction_finale(
    db: Session,
    escrow_id: int,
    validator_id: int,
    validation_type: str = "terrain"
) -> EscrowAccount:
    """
    Valide la transaction finale et libère les fonds restants vers le vendeur.
    Pour les terrains, une validation supplémentaire (topographe) est requise.
    """
    escrow = db.query(EscrowAccount).filter(EscrowAccount.id == escrow_id).first()
    if not escrow:
        raise EscrowError(f"Escrow introuvable : id={escrow_id}")

    if escrow.status not in [EscrowStatus.LOCKED, EscrowStatus.PARTIAL_RELEASED]:
        raise EscrowError(
            f"Impossible de valider : statut actuel = {escrow.status.value}"
        )

    # Vérification spécifique pour les terrains
    if validation_type == "terrain":
        # Vérifier que le validateur est un topographe agréé
        validator = db.query(User).filter(User.id == validator_id).first()
        if not validator or validator.role != "topographe":
            raise EscrowError(
                "La validation d'un terrain nécessite un topographe agréé."
            )
        # Vérifier que le topographe a une géolocalisation valide
        # (déjà validé par le middleware de géolocalisation)
        escrow_logger.info(
            f"Validation terrain par topographe {validator_id} pour escrow {escrow_id}"
        )

    # Libérer les fonds restants vers le vendeur
    montant_restant = escrow.amount
    if montant_restant > 0:
        seller = db.query(User).filter(User.id == escrow.seller_id).first()
        if not seller:
            raise EscrowError(f"Vendeur introuvable : id={escrow.seller_id}")

        seller.balance += montant_restant
        db.add(seller)

        # Créer une transaction pour le vendeur
        transaction = Transaction(
            escrow_id=escrow_id,
            artisan_id=escrow.seller_id,
            amount=montant_restant,
            description="Libération finale des fonds au vendeur",
            status="completed",
            created_at=datetime.now(timezone.utc)
        )
        db.add(transaction)

    # Mettre à jour le statut de l'escrow
    escrow.status = EscrowStatus.COMPLETED
    escrow.amount = 0
    escrow.updated_at = datetime.now(timezone.utc)
    escrow.completed_at = datetime.now(timezone.utc)

    # Mettre à jour le statut du bien
    bien = db.query(Property).filter(Property.id == escrow.property_id).first()
    if bien:
        bien.status = PropertyStatus.SOLD
        bien.updated_at = datetime.now(timezone.utc)
        db.add(bien)

    db.add(escrow)
    db.commit()
    db.refresh(escrow)

    escrow_logger.info(
        f"Transaction finale validée : escrow={escrow_id}, "
        f"type={validation_type}, validateur={validator_id}"
    )
    return escrow


def annuler_escrow(
    db: Session,
    escrow_id: int,
    reason: str = "Annulation"
) -> EscrowAccount:
    """
    Annule un séquestre et rembourse l'acheteur.
    """
    escrow = db.query(EscrowAccount).filter(EscrowAccount.id == escrow_id).first()
    if not escrow:
        raise EscrowError(f"Escrow introuvable : id={escrow_id}")

    if escrow.status == EscrowStatus.COMPLETED:
        raise EscrowError("Impossible d'annuler un séquestre déjà complété.")

    # Rembourser l'acheteur
    buyer = db.query(User).filter(User.id == escrow.buyer_id).first()
    if buyer:
        buyer.balance += escrow.amount
        db.add(buyer)

    # Mettre à jour le statut
    escrow.status = EscrowStatus.CANCELLED
    escrow.amount = 0
    escrow.updated_at = datetime.now(timezone.utc)
    escrow.cancellation_reason = reason

    # Libérer le bien
    bien = db.query(Property).filter(Property.id == escrow.property_id).first()
    if bien:
        bien.status = PropertyStatus.AVAILABLE
        bien.frozen_until = None
        bien.frozen_by_buyer_id = None
        bien.updated_at = datetime.now(timezone.utc)
        db.add(bien)

    db.add(escrow)
    db.commit()
    db.refresh(escrow)

    escrow_logger.info(f"Escrow annulé : id={escrow_id}, raison={reason}")
    return escrow
