"""
Module de géolocalisation et validation territoriale.
Vérifie que les actions sensibles proviennent bien de Côte d'Ivoire.
Détecte les fausses positions (mock location) et calcule la précision.
"""

import math
import logging
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone

from fastapi import Request, HTTPException, status
from pydantic import BaseModel, Field, validator

# Configuration du logger
geo_logger = logging.getLogger("geolocation")

# ──────────────────────────────────────────────────────────────
# Coordonnées des principales villes de Côte d'Ivoire
# ──────────────────────────────────────────────────────────────
CI_CITIES: Dict[str, Tuple[float, float]] = {
    "Abidjan": (5.3599, -4.0083),
    "Yamoussoukro": (6.8276, -5.2893),
    "Bouaké": (7.6906, -5.0300),
    "Daloa": (6.8776, -6.4502),
    "San-Pédro": (4.7485, -6.6363),
    "Korhogo": (9.4578, -5.6294),
    "Man": (7.4125, -7.5536),
    "Divo": (5.8394, -5.3570),
    "Gagnoa": (6.1319, -5.9506),
    "Abengourou": (6.7297, -3.4964),
}

# ──────────────────────────────────────────────────────────────
# Boîte englobante de la Côte d'Ivoire (approximative)
# Latitudes : 4.3°N à 10.8°N  |  Longitudes : -8.7°W à -2.4°W
# Source : données administratives (Humdata) et EPSG:4226
# ──────────────────────────────────────────────────────────────
CI_BOUNDING_BOX = {
    "min_lat": 4.3,
    "max_lat": 10.8,
    "min_lon": -8.7,
    "max_lon": -2.4,
}

# Rayon moyen de la Terre en mètres
EARTH_RADIUS_M = 6_371_000


class GeoCoordinates(BaseModel):
    """
    Modèle de validation des coordonnées GPS.
    """
    latitude: float = Field(..., ge=-90, le=90, description="Latitude en degrés décimaux")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude en degrés décimaux")
    accuracy: Optional[float] = Field(None, ge=0, description="Précision en mètres")
    timestamp: Optional[float] = Field(None, description="Timestamp de la position")
    is_mocked: Optional[bool] = Field(False, description="Indique si la position est simulée")
    provider: Optional[str] = Field(None, description="Fournisseur de localisation (GPS, NETWORK, etc.)")

    @validator("latitude", "longitude")
    def check_valid_coords(cls, v):
        if v is None:
            raise ValueError("Les coordonnées ne peuvent pas être nulles")
        return v


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calcule la distance en mètres entre deux points GPS (formule de Haversine).
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


def is_within_cote_divoire(latitude: float, longitude: float) -> bool:
    """
    Vérifie si les coordonnées sont dans la boîte englobante de la Côte d'Ivoire.
    """
    return (
        CI_BOUNDING_BOX["min_lat"] <= latitude <= CI_BOUNDING_BOX["max_lat"]
        and CI_BOUNDING_BOX["min_lon"] <= longitude <= CI_BOUNDING_BOX["max_lon"]
    )


def get_nearest_city(latitude: float, longitude: float) -> Optional[str]:
    """
    Retourne le nom de la ville ivoirienne la plus proche des coordonnées.
    """
    nearest = None
    min_distance = float("inf")
    for city, (city_lat, city_lon) in CI_CITIES.items():
        dist = haversine_distance(latitude, longitude, city_lat, city_lon)
        if dist < min_distance:
            min_distance = dist
            nearest = city
    return nearest


def detect_mock_location(geo: GeoCoordinates, request: Request) -> Tuple[bool, str]:
    """
    Détecte les indices de fausse position (mock location).
    Retourne (is_mocked, raison).
    """
    # 1. Vérification explicite du flag is_mocked (fourni par l'app mobile)
    if geo.is_mocked:
        return True, "Flag is_mocked activé par le client"

    # 2. Vérification de la cohérence de la précision
    if geo.accuracy is not None:
        # Une précision de 0 mètre est physiquement impossible
        if geo.accuracy == 0:
            return True, "Précision GPS nulle (impossible physiquement)"
        # Une précision extrêmement faible (< 1 mètre) en zone rurale est suspecte
        if geo.accuracy < 1:
            # Vérifier si on est en zone urbaine (proche d'une grande ville)
            nearest = get_nearest_city(geo.latitude, geo.longitude)
            if nearest:
                city_lat, city_lon = CI_CITIES[nearest]
                dist = haversine_distance(geo.latitude, geo.longitude, city_lat, city_lon)
                # Si on est à plus de 5 km de la ville mais avec une précision < 1m, suspect
                if dist > 5000:
                    return True, f"Précision anormalement faible ({geo.accuracy}m) en zone rurale"

    # 3. Vérification du fournisseur de localisation
    if geo.provider:
        provider_upper = geo.provider.upper()
        # Les fournisseurs "MOCK" ou "TEST" sont explicitement des simulations
        if "MOCK" in provider_upper or "TEST" in provider_upper or "FAKE" in provider_upper:
            return True, f"Fournisseur de localisation suspect : {geo.provider}"

    # 4. Vérification de la cohérence temporelle (si timestamp fourni)
    if geo.timestamp is not None:
        now = datetime.now(timezone.utc).timestamp()
        # Un timestamp dans le futur ou trop ancien (> 5 min) est suspect
        if geo.timestamp > now + 60:
            return True, "Timestamp de localisation dans le futur"
        if abs(now - geo.timestamp) > 300:
            return True, "Timestamp de localisation trop ancien (> 5 minutes)"

    # 5. Vérification croisée IP / GPS (si l'IP est disponible)
    client_ip = request.client.host if request.client else None
    if client_ip:
        # Ici on pourrait utiliser un service de géolocalisation IP
        # Pour l'instant, on vérifie juste que l'IP n'est pas locale
        if client_ip.startswith("127.") or client_ip.startswith("192.168."):
            # Une IP locale avec un GPS ivoirien est très suspecte (émulateur)
            if is_within_cote_divoire(geo.latitude, geo.longitude):
                return True, "IP locale avec coordonnées GPS ivoiriennes (émulateur probable)"

    return False, ""


def validate_geolocation(
    geo: GeoCoordinates,
    request: Request,
    require_cote_divoire: bool = True,
    max_accuracy_m: Optional[float] = None
) -> Dict[str, Any]:
    """
    Fonction principale de validation géographique.
    Retourne un dictionnaire avec le résultat et les métadonnées.
    """
    result = {
        "valid": False,
        "reason": "",
        "nearest_city": None,
        "distance_to_city_m": None,
        "is_within_ci": False,
        "is_mocked": False,
        "accuracy_ok": True,
    }

    # 1. Vérification de la boîte englobante Côte d'Ivoire
    within_ci = is_within_cote_divoire(geo.latitude, geo.longitude)
    result["is_within_ci"] = within_ci

    if require_cote_divoire and not within_ci:
        result["reason"] = (
            f"Coordonnées hors de Côte d'Ivoire : "
            f"lat={geo.latitude}, lon={geo.longitude}"
        )
        geo_logger.warning(result["reason"])
        return result

    # 2. Détection de mock location
    is_mocked, mock_reason = detect_mock_location(geo, request)
    result["is_mocked"] = is_mocked
    if is_mocked:
        result["reason"] = f"Fausse position détectée : {mock_reason}"
        geo_logger.warning(result["reason"])
        return result

    # 3. Vérification de la précision
    if max_accuracy_m is not None and geo.accuracy is not None:
        if geo.accuracy > max_accuracy_m:
            result["accuracy_ok"] = False
            result["reason"] = (
                f"Précision GPS insuffisante : {geo.accuracy}m "
                f"(max autorisé : {max_accuracy_m}m)"
            )
            geo_logger.warning(result["reason"])
            return result

    # 4. Identification de la ville la plus proche
    nearest = get_nearest_city(geo.latitude, geo.longitude)
    result["nearest_city"] = nearest
    if nearest:
        city_lat, city_lon = CI_CITIES[nearest]
        result["distance_to_city_m"] = haversine_distance(
            geo.latitude, geo.longitude, city_lat, city_lon
        )

    # 5. Validation réussie
    result["valid"] = True
    result["reason"] = "Localisation validée"
    return result


async def require_cote_divoire_geolocation(
    request: Request,
    geo: GeoCoordinates,
    max_accuracy_m: float = 100.0
) -> Dict[str, Any]:
    """
    Dépendance FastAPI pour les routes sensibles.
    Lève une HTTPException 403 si la localisation n'est pas valide.
    """
    validation = validate_geolocation(
        geo=geo,
        request=request,
        require_cote_divoire=True,
        max_accuracy_m=max_accuracy_m
    )

    if not validation["valid"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=validation["reason"]
        )

    return validation


# ──────────────────────────────────────────────────────────────
# Exemple d'utilisation dans une route FastAPI
# ──────────────────────────────────────────────────────────────
"""
from fastapi import APIRouter, Depends, Request
from app.geolocation import GeoCoordinates, require_cote_divoire_geolocation

router = APIRouter()

@router.post("/signer-terrain")
async def signer_terrain(
    request: Request,
    geo: GeoCoordinates,
    validation: dict = Depends(require_cote_divoire_geolocation)
):
    return {
        "message": "Terrain signé avec succès",
        "localisation_validee": validation
    }
"""
