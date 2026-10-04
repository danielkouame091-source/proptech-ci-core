# app/security_vpn.py
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

from app.database import SessionLocal

# Configuration du logger
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
# Plages d'IP connues comme VPN/proxy/Tor (exemples à enrichir)
# ──────────────────────────────────────────────────────────────
KNOWN_VPN_PROXY_RANGES: Set[str] = {
    "185.220.100.0/22",
    "185.220.101.0/24",
    "185.220.102.0/23",
    "185.220.104.0/21",
    "37.120.128.0/17",
    "185.93.2.0/23",
    "194.242.0.0/16",
    "45.133.192.0/22",
}

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

EMULATOR_USER_AGENTS: List[str] = [
    "emulator", "simulator", "genymotion", "bluestacks",
    "nox", "andy", "memu", "ldplayer", "android sdk built for",
    "virtualbox", "vmware", "qemu", "xen", "parallels"
]


def get_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip.strip()
    return request.client.host if request.client else "0.0.0.0"


def is_ip_in_vpn_range(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        for cidr in KNOWN_VPN_PROXY_RANGES:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
    except ValueError:
        pass
    return False


def detect_emulator(user_agent: Optional[str]) -> bool:
    if not user_agent:
        return False
    ua_lower = user_agent.lower()
    return any(keyword in ua_lower for keyword in EMULATOR_USER_AGENTS)


def log_suspicious_attempt(
    ip: str,
    reason: str,
    user_agent: Optional[str] = None,
    extra_headers: Optional[dict] = None
) -> None:
    security_logger.warning(
        f"Tentative bloquée | IP={ip} | Raison={reason} | "
        f"UA={user_agent} | Headers={extra_headers}"
    )
    db = SessionLocal()
    try:
        from app.models import SecurityLog
        security_log = SecurityLog(
            ip_address=ip,
            reason=reason,
            user_agent=user_agent,
            headers=str(extra_headers),
            created_at=datetime.now(timezone.utc)
        )
        db.add(security_log)
        db.commit()
    except Exception as e:
        security_logger.error(f"Erreur enregistrement SecurityLog: {e}")
        db.rollback()
    finally:
        db.close()


async def security_middleware(request: Request, call_next):
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    headers_dict = dict(request.headers)

    if is_ip_in_vpn_range(client_ip):
        log_suspicious_attempt(
            ip=client_ip,
            reason="IP dans plage VPN/Proxy/Tor",
            user_agent=user_agent,
            extra_headers=headers_dict
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : utilisation de VPN/Proxy/Tor détectée."
        )

    suspicious_headers_found = [
        h for h in SUSPICIOUS_HEADERS
        if h.lower() in [k.lower() for k in headers_dict.keys()]
    ]
    if len(suspicious_headers_found) > 3:
        log_suspicious_attempt(
            ip=client_ip,
            reason=f"Trop d'en-têtes proxy suspects : {suspicious_headers_found}",
            user_agent=user_agent,
            extra_headers=headers_dict
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : configuration réseau suspecte détectée."
        )

    if detect_emulator(user_agent):
        log_suspicious_attempt(
            ip=client_ip,
            reason="User-Agent d'émulateur détecté",
            user_agent=user_agent,
            extra_headers=headers_dict
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : émulateur détecté."
        )

    return await call_next(request)
