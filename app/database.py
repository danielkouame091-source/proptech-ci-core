from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    role = db.Column(db.String(50), default="USER") # USER, TOPOGRAPHER, ADMIN, SELLER, BUYER
    biometric_hash = db.Column(db.String(255), nullable=True) # Empreinte / CNI
    properties = db.relationship('Property', backref='owner', lazy=True)

class Property(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    city = db.Column(db.String(100), nullable=False) # ex: Abidjan, Yamoussoukro
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Gestion du statut et de la règle anti-double vente (Gel de 3 jours)
    status = db.Column(db.String(50), default="AVAILABLE") # AVAILABLE, LOCKED_FOR_NEGOTIATION, SOLD_AND_REGISTERED
    lock_expires_at = db.Column(db.DateTime, nullable=True)
    current_negotiator_id = db.Column(db.Integer, nullable=True)

class EscrowAccount(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('property.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="HELD_IN_ESCROW") # HELD_IN_ESCROW, RELEASED_TO_SELLER, REFUNDED
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    released_at = db.Column(db.DateTime, nullable=True)
    validated_by = db.Column(db.Integer, nullable=True)
