"""
Module de sécurité réseau et anti-VPN.
Analyse les en-têtes HTTP pour détecter et bloquer les VPN, proxys, Tor et émulateurs.
Enregistre automatiquement les tentatives suspectes.
"""

import ipaddress
import logging
from datetime import datetime, timezone
from typing import Optional, Set, List

from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session

# Configuration du logger pour les tentatives suspectes
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - SECURITY - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("security_alerts.log"),
        logging.StreamHandler()
    ]
)
security_logger = logging.getLogger("security_vpn")

# ──────────────────────────────────────────────────────────────
# Liste des plages d'IP connues comme appartenant à des VPN/proxys/Tor
# À compléter avec une source à jour (ex: IP2Proxy, MaxMind, etc.)
# ──────────────────────────────────────────────────────────────
KNOWN_VPN_PROXY_RANGES: Set[str] = {
    # Exemples de plages Tor exit nodes
    "185.220.100.0/22",
    "185.220.101.0/24",
    "185.220.102.0/23",
    "185.220.104.0/21",
    # Plages NordVPN (exemple)
    "37.120.128.0/17",
    "185.93.2.0/23",
    # Plages ExpressVPN (exemple)
    "194.242.0.0/16",
    # Plages Surfshark (exemple)
    "45.133.192.0/22",
}

# En-têtes suspects indiquant un proxy ou un VPN
SUSPICIOUS_HEADERS: List[str] = [
    "Via",
    "X-Forwarded-For",
    "Forwarded",
    "X-Real-IP",
    "X-Proxy-ID",
    "X-Scraper-ID",
    "X-Forwarded-Proto",
    "CF-Connecting-IP",
    "True-Client-IP",
]

# Mots-clés d'émulateurs dans le User-Agent
EMULATOR_USER_AGENTS: List[str] = [
    "emulator", "simulator", "genymotion", "bluestacks",
    "nox", "andy", "memu", "ldplayer", "android sdk built for",
    "virtualbox", "vmware", "qemu", "xen", "parallels"
]


def get_client_ip(request: Request) -> str:
    """
    Extrait l'IP réelle du client en tenant compte des en-têtes de proxy.
    Ordre de priorité : CF-Connecting-IP > X-Forwarded-For > X-Real-IP > remote_addr.
    """
    # Cloudflare
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    # X-Forwarded-For (prendre la première IP de la liste)
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()

    # X-Real-IP
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()

    # Fallback sur l'adresse directe
    return request.client.host if request.client else "0.0.0.0"


def is_ip_in_vpn_range(ip_str: str) -> bool:
    """
    Vérifie si une IP appartient à une plage connue de VPN/proxy/Tor.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        for cidr in KNOWN_VPN_PROXY_RANGES:
            network = ipaddress.ip_network(cidr, strict=False)
            if ip in network:
                return True
    except ValueError:
        pass
    return False


def detect_emulator(user_agent: Optional[str]) -> bool:
    """
    Détecte si le User-Agent correspond à un émulateur.
    """
    if not user_agent:
        return False
    ua_lower = user_agent.lower()
    return any(keyword in ua_lower for keyword in EMULATOR_USER_AGENTS)


def log_suspicious_attempt(
    db: Session,
    ip: str,
    reason: str,
    user_agent: Optional[str] = None,
    extra_headers: Optional[dict] = None
) -> None:
    """
    Enregistre une tentative suspecte en base de données et dans le fichier de log.
    """
    # Log fichier
    security_logger.warning(
        f"Tentative bloquée | IP={ip} | Raison={reason} | "
        f"UA={user_agent} | Headers={extra_headers}"
    )

    # Log en base (si un modèle SecurityLog existe)
    # À décommenter après avoir créé le modèle SecurityLog dans models.py
    # try:
    #     security_log = SecurityLog(
    #         ip_address=ip,
    #         reason=reason,
    #         user_agent=user_agent,
    #         headers=str(extra_headers),
    #         created_at=datetime.now(timezone.utc)
    #     )
    #     db.add(security_log)
    #     db.commit()
    # except Exception as e:
    #     security_logger.error(f"Erreur enregistrement SecurityLog: {e}")
    #     db.rollback()


async def security_middleware(request: Request, call_next):
    """
    Middleware FastAPI qui analyse chaque requête entrante.
    Bloque avec 403 Forbidden si un VPN/proxy/Tor/émulateur est détecté.
    """
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    headers_dict = dict(request.headers)

    # 1. Vérification IP dans les plages VPN/proxy/Tor
    if is_ip_in_vpn_range(client_ip):
        log_suspicious_attempt(
            db=None,  # Injecter la session DB via dépendance si nécessaire
            ip=client_ip,
            reason="IP dans plage VPN/Proxy/Tor",
            user_agent=user_agent,
            extra_headers=headers_dict
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : utilisation de VPN/Proxy/Tor détectée."
        )

    # 2. Vérification de la présence d'en-têtes de proxy suspects
    suspicious_headers_found = [
        h for h in SUSPICIOUS_HEADERS
        if h.lower() in [k.lower() for k in headers_dict.keys()]
    ]
    # Si plus de 3 en-têtes suspects sont présents, c'est très probablement un proxy
    if len(suspicious_headers_found) > 3:
        log_suspicious_attempt(
            db=None,
            ip=client_ip,
            reason=f"Trop d'en-têtes proxy suspects : {suspicious_headers_found}",
            user_agent=user_agent,
            extra_headers=headers_dict
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : configuration réseau suspecte détectée."
        )

    # 3. Détection d'émulateur
    if detect_emulator(user_agent):
        log_suspicious_attempt(
            db=None,
            ip=client_ip,
            reason="User-Agent d'émulateur détecté",
            user_agent=user_agent,
            extra_headers=headers_dict
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : émulateur détecté."
        )

    # 4. Vérification de la cohérence IP directe vs X-Forwarded-For
    direct_ip = request.client.host if request.client else None
    xff_ip = request.headers.get("X-Forwarded-For")
    if xff_ip and direct_ip:
        # Si l'IP directe est privée mais que le XFF est public, c'est suspect
        try:
            direct_ip_obj = ipaddress.ip_address(direct_ip)
            if direct_ip_obj.is_private:
                xff_first = xff_ip.split(",")[0].strip()
                xff_ip_obj = ipaddress.ip_address(xff_first)
                if not xff_ip_obj.is_private:
                    log_suspicious_attempt(
                        db=None,
                        ip=client_ip,
                        reason="Incohérence IP directe privée / X-Forwarded-For public",
                        user_agent=user_agent,
                        extra_headers=headers_dict
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Accès refusé : configuration réseau incohérente."
                    )
        except ValueError:
            pass

    # Requête autorisée
    response = await call_next(request)
    return response


def get_client_ip_safe(request: Request) -> str:
    """
    Version utilitaire pour extraire l'IP de manière sécurisée.
    """
    return get_client_ip(request)
