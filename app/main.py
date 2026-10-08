from flask import Flask, request, jsonify
from database import db, User, Property, EscrowAccount
from utils.security_vpn import anti_vpn_middleware
from utils.geolocation import validate_ivorian_territory
from services.escrow_service import EscrowService
from services.analytics_ai import FounderAnalyticsService
import os

app = Flask(__name__)

# Configuration de la base de données SQLite locale (évolutif vers PostgreSQL)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'proptech.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialisation de SQLAlchemy avec l'application Flask
db.init_app(app)

with app.app_context():
    db.create_all()

# ==========================================
# 1. ROUTE DE TEST / ACCUEIL
# ==========================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "project": "PropTech-CI Core Infrastructure",
        "status": "SECURE",
        "country": "Côte d'Ivoire",
        "message": "Guichet unique foncier, BTP et séquestre opérationnel."
    }), 200

# ==========================================
# 2. ROUTE DE NÉGOCIATION (Anti-Double Vente - Gel 3 jours)
# ==========================================
@app.route('/api/v1/property/negotiate', methods=['POST'])
@anti_vpn_middleware
def negotiate_property():
    data = request.get_json()
    property_id = data.get('property_id')
    buyer_id = data.get('buyer_id')

    if not property_id or not buyer_id:
        return jsonify({"error": "Paramètres manquants (property_id, buyer_id requis)."}), 400

    try:
        result = EscrowService.initiate_property_negotiation(property_id, buyer_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 409 # Conflict (ex: déjà gelé)

# ==========================================
# 3. ROUTE DE SÉQUESTRE FINANCIER (Géolocalisée + Sécurisée)
# ==========================================
@app.route('/api/v1/escrow/deposit', methods=['POST'])
@anti_vpn_middleware
def create_escrow_deposit():
    data = request.get_json()
    
    # Récupération des données GPS transmises par l'application mobile/web
    lat = data.get('latitude')
    lon = data.get('longitude')
    accuracy = data.get('accuracy', 10.0)
    is_mocked = data.get('is_mocked', False)
    
    property_id = data.get('property_id')
    buyer_id = data.get('buyer_id')
    amount = data.get('amount')

    if None in [lat, lon, property_id, buyer_id, amount]:
        return jsonify({"error": "Données incomplètes pour valider la transaction sécurisée."}), 400

    # Validation rigoureuse de la position physique en Côte d'Ivoire
    is_valid_geo, geo_message = validate_ivorian_territory(lat, lon, accuracy, is_mocked)
    if not is_valid_geo:
        return jsonify({
            "error": "Validation territoriale échouée",
            "message": geo_message
        }, 403)

    try:
        result = EscrowService.deposit_to_escrow(property_id, buyer_id, amount)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

# ==========================================
# 4. TABLEAU DE BORD DU FONDATEUR (Analytics & Risques)
# ==========================================
@app.route('/api/v1/admin/dashboard', methods=['GET'])
@anti_vpn_middleware
def founder_dashboard():
    # Optionnel : Ajoutez ici un contrôle de rôle Administrateur
    try:
        report = FounderAnalyticsService.generate_executive_dashboard_report()
        return jsonify(report), 200
    except Exception as e:
        return jsonify({"error": f"Erreur lors de la génération du rapport : {str(e)}"}), 500

if __name__ == '__main__':
    # Lancement du serveur de développement local Flask sur le Mac
    app.run(host='0.0.0.0', port=5000, debug=True)
