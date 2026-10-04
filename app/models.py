# app/models.py
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum,
    ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
import enum


class UserRole(str, enum.Enum):
    BUYER = "buyer"
    SELLER = "seller"
    TOPOGRAPHE = "topographe"
    ARTISAN = "artisan"
    ADMIN = "admin"


class PropertyStatus(str, enum.Enum):
    AVAILABLE = "available"
    FROZEN = "frozen"
    SOLD = "sold"
    UNAVAILABLE = "unavailable"


class EscrowStatus(str, enum.Enum):
    LOCKED = "locked"
    PARTIAL_RELEASED = "partial_released"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(Enum(UserRole), default=UserRole.BUYER)
    balance = Column(Float, default=0.0)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    properties = relationship("Property", back_populates="owner", foreign_keys="Property.owner_id")
    escrows_buyer = relationship("EscrowAccount", foreign_keys="EscrowAccount.buyer_id", back_populates="buyer")
    escrows_seller = relationship("EscrowAccount", foreign_keys="EscrowAccount.seller_id", back_populates="seller")


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    city = Column(String, index=True, nullable=False)
    address = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(Enum(PropertyStatus), default=PropertyStatus.AVAILABLE)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    frozen_until = Column(DateTime, nullable=True)
    frozen_by_buyer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="properties", foreign_keys=[owner_id])
    frozen_by_buyer = relationship("User", foreign_keys=[frozen_by_buyer_id])
    escrows = relationship("EscrowAccount", back_populates="property")


class EscrowAccount(Base):
    __tablename__ = "escrow_accounts"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="XOF")
    status = Column(Enum(EscrowStatus), default=EscrowStatus.LOCKED)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    buyer = relationship("User", foreign_keys=[buyer_id], back_populates="escrows_buyer")
    seller = relationship("User", foreign_keys=[seller_id], back_populates="escrows_seller")
    property = relationship("Property", back_populates="escrows")
    transactions = relationship("Transaction", back_populates="escrow")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    escrow_id = Column(Integer, ForeignKey("escrow_accounts.id"), nullable=False)
    artisan_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    escrow = relationship("EscrowAccount", back_populates="transactions")
    artisan = relationship("User", foreign_keys=[artisan_id])


class SecurityLog(Base):
    __tablename__ = "security_logs"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, index=True, nullable=False)
    reason = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)
    headers = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class GeoLog(Base):
    __tablename__ = "geo_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy = Column(Float, nullable=True)
    is_valid = Column(Boolean, default=False)
    is_mocked = Column(Boolean, default=False)
    reason = Column(Text, nullable=True)
    nearest_city = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
