# app/analytics_ai.py
"""
Module d'analyse backend et de génération de rapports pour le fondateur.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models import (
    User, Property, EscrowAccount, Transaction,
    UserRole, PropertyStatus, EscrowStatus
)

analytics_logger = logging.getLogger("analytics_ai")


def analyser_tendances_transactions(db: Session, periode_jours: int = 30) -> Dict[str, Any]:
    date_debut = datetime.now(timezone.utc) - timedelta(days=periode_jours)

    total_escrows = db.query(EscrowAccount).filter(
        EscrowAccount.created_at >= date_debut
    ).count()

    escrows_completes = db.query(EscrowAccount).filter(
        EscrowAccount.created_at >= date_debut,
        EscrowAccount.status == EscrowStatus.COMPLETED
    ).count()

    escrows_annules = db.query(EscrowAccount).filter(
        EscrowAccount.created_at >= date_debut,
        EscrowAccount.status == EscrowStatus.CANCELLED
    ).count()

    montant_total = db.query(func.sum(EscrowAccount.amount)).filter(
        EscrowAccount.created_at >= date_debut
    ).scalar() or 0.0

    taux_conversion = (escrows_completes / total_escrows * 100) if total_escrows > 0 else 0

    ventes_par_ville = db.query(
        Property.city,
        func.count(EscrowAccount.id).label("nb_ventes"),
        func.sum(EscrowAccount.amount).label("montant_total")
    ).join(
        EscrowAccount, EscrowAccount.property_id == Property.id
    ).filter(
        EscrowAccount.created_at >= date_debut,
        EscrowAccount.status == EscrowStatus.COMPLETED
    ).group_by(Property.city).all()

    villes_stats = [
        {"ville": v[0], "nb_ventes": v[1], "montant_total": float(v[2]) if v[2] else 0.0}
        for v in ventes_par_ville
    ]

    biens_par_statut = db.query(
        Property.status, func.count(Property.id).label("nb")
    ).group_by(Property.status).all()

    statuts_stats = {s[0].value if s[0] else "unknown": s[1] for s in biens_par_statut}

    return {
        "periode_jours": periode_jours,
        "date_debut": date_debut.isoformat(),
        "total_escrows": total_escrows,
        "escrows_completes": escrows_completes,
        "escrows_annules": escrows_annules,
        "taux_conversion_pct": round(taux_conversion, 2),
        "montant_total_sequestre": float(montant_total),
        "villes_stats": villes_stats,
        "biens_par_statut": statuts_stats
    }


def detecter_zones_forte_demande_artisans(db: Session, periode_jours: int = 90, top_n: int = 5) -> List[Dict[str, Any]]:
    date_debut = datetime.now(timezone.utc) - timedelta(days=periode_jours)

    resultats = db.query(
        Property.city,
        func.count(Transaction.id).label("nb_transactions"),
        func.count(func.distinct(Transaction.artisan_id)).label("nb_artisans"),
        func.sum(Transaction.amount).label("montant_total")
    ).join(
        EscrowAccount, Transaction.escrow_id == EscrowAccount.id
    ).join(
        Property, EscrowAccount.property_id == Property.id
    ).filter(
        Transaction.created_at >= date_debut
    ).group_by(Property.city).order_by(
        desc("nb_transactions")
    ).limit(top_n).all()

    zones = []
    for r in resultats:
        zones.append({
            "ville": r[0],
            "nb_transactions": r[1],
            "nb_artisans_actifs": r[2],
            "montant_total": float(r[3]) if r[3] else 0.0,
            "indice_demande": round(r[1] / max(r[2], 1), 2)
        })
    return zones


def detecter_anomalies_fraude(db: Session, periode_jours: int = 30) -> List[Dict[str, Any]]:
    date_debut = datetime.now(timezone.utc) - timedelta(days=periode_jours)
    anomalies = []

    avg_amount = db.query(func.avg(EscrowAccount.amount)).filter(
        EscrowAccount.created_at >= date_debut
    ).scalar() or 0.0

    seuil_eleve = avg_amount * 3
    grosses = db.query(EscrowAccount).filter(
        EscrowAccount.created_at >= date_debut,
        EscrowAccount.amount > seuil_eleve
    ).all()

    for t in grosses:
        anomalies.append({
            "type": "montant_anormalement_eleve",
            "escrow_id": t.id,
            "montant": t.amount,
            "moyenne": round(avg_amount, 2),
            "ratio": round(t.amount / avg_amount, 2) if avg_amount > 0 else None,
            "buyer_id": t.buyer_id,
            "property_id": t.property_id
        })

    escrows_recents = db.query(EscrowAccount).filter(
        EscrowAccount.created_at >= date_debut,
        EscrowAccount.status == EscrowStatus.CANCELLED
    ).all()

    for e in escrows_recents:
        if e.updated_at and e.created_at:
            duree = (e.updated_at - e.created_at).total_seconds() / 3600
            if duree < 24:
                anomalies.append({
                    "type": "annulation_rapide",
                    "escrow_id": e.id,
                    "duree_heures": round(duree, 2),
                    "buyer_id": e.buyer_id,
                    "property_id": e.property_id,
                    "raison": e.cancellation_reason
                })

    annulations_par_user = db.query(
        EscrowAccount.buyer_id,
        func.count(EscrowAccount.id).label("nb_annulations")
    ).filter(
        EscrowAccount.created_at >= date_debut,
        EscrowAccount.status == EscrowStatus.CANCELLED
    ).group_by(EscrowAccount.buyer_id).having(
        func.count(EscrowAccount.id) > 3
    ).all()

    for a in annulations_par_user:
        anomalies.append({
            "type": "utilisateur_avec_annulations_repetees",
            "user_id": a[0],
            "nb_annulations": a[1]
        })

    prix_moyens = db.query(
        Property.city, func.avg(Property.price).label("prix_moyen")
    ).group_by(Property.city).all()
    prix_moyens_dict = {p[0]: float(p[1]) for p in prix_moyens if p[1]}

    biens_vendus = db.query(Property).filter(
        Property.status == PropertyStatus.SOLD,
        Property.updated_at >= date_debut
    ).all()

    for b in biens_vendus:
        if b.city in prix_moyens_dict:
            pm = prix_moyens_dict[b.city]
            if b.price < pm * 0.5:
                anomalies.append({
                    "type": "prix_anormalement_bas",
                    "property_id": b.id,
                    "ville": b.city,
                    "prix": b.price,
                    "prix_moyen_ville": round(pm, 2),
                    "ratio": round(b.price / pm, 2)
                })

    anomalies.sort(key=lambda x: x.get("ratio", 0), reverse=True)
    return anomalies


def generer_rapport_fondateur(db: Session, periode_jours: int = 30) -> Dict[str, Any]:
    rapport = {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "periode_jours": periode_jours,
        "tendances": analyser_tendances_transactions(db, periode_jours),
        "zones_demande_artisans": detecter_zones_forte_demande_artisans(db, periode_jours),
        "alertes_fraude": detecter_anomalies_fraude(db, periode_jours),
    }
    nb_alertes = len(rapport["alertes_fraude"])
    nb_zones = len(rapport["zones_demande_artisans"])
    rapport["resume_executif"] = {
        "nb_transactions": rapport["tendances"]["total_escrows"],
        "taux_conversion": rapport["tendances"]["taux_conversion_pct"],
        "montant_total_sequestre": rapport["tendances"]["montant_total_sequestre"],
        "nb_zones_demande": nb_zones,
        "nb_alertes_fraude": nb_alertes,
        "niveau_risque": (
            "CRITIQUE" if nb_alertes > 10
            else "ÉLEVÉ" if nb_alertes > 5
            else "MODÉRÉ" if nb_alertes > 2
            else "FAIBLE"
        )
    }
    analytics_logger.info(f"Rapport fondateur généré : {nb_alertes} alertes, {nb_zones} zones")
    return rapport


def generer_rapport_alertes_fraude(db: Session, periode_jours: int = 30) -> Dict[str, Any]:
    anomalies = detecter_anomalies_fraude(db, periode_jours)
    par_type = defaultdict(list)
    for a in anomalies:
        par_type[a["type"]].append(a)
    stats_par_type = {t: {"count": len(items), "items": items[:10]} for t, items in par_type.items()}
    return {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "periode_jours": periode_jours,
        "total_alertes": len(anomalies),
        "alertes_par_type": stats_par_type,
        "toutes_les_alertes": anomalies
    }


def generer_rapport_artisans(db: Session, periode_jours: int = 90) -> Dict[str, Any]:
    date_debut = datetime.now(timezone.utc) - timedelta(days=periode_jours)

    total_artisans = db.query(User).filter(User.role == UserRole.ARTISAN).count()

    artisans_actifs = db.query(
        func.count(func.distinct(Transaction.artisan_id))
    ).filter(Transaction.created_at >= date_debut).scalar() or 0

    montant_total = db.query(func.sum(Transaction.amount)).filter(
        Transaction.created_at >= date_debut
    ).scalar() or 0.0

    top_artisans = db.query(
        User.id, User.full_name,
        func.sum(Transaction.amount).label("montant_total"),
        func.count(Transaction.id).label("nb_transactions")
    ).join(
        Transaction, Transaction.artisan_id == User.id
    ).filter(
        Transaction.created_at >= date_debut,
        User.role == UserRole.ARTISAN
    ).group_by(User.id, User.full_name).order_by(
        desc("montant_total")
    ).limit(10).all()

    return {
        "genere_le": datetime.now(timezone.utc).isoformat(),
        "periode_jours": periode_jours,
        "total_artisans": total_artisans,
        "artisans_actifs": artisans_actifs,
        "taux_activite_pct": round((artisans_actifs / total_artisans * 100) if total_artisans > 0 else 0, 2),
        "montant_total_paye": float(montant_total),
        "top_artisans": [
            {"id": a[0], "nom": a[1], "montant_total": float(a[2]), "nb_transactions": a[3]}
            for a in top_artisans
        ]
    }
