from sqlalchemy import Column, Integer, String, Float
from .database import Base

class BienImmobilier(Base):
    __tablename__ = "biens"

    id = Column(Integer, primary_key=True, index=True)
    titre = Column(String, index=True)
    ville = Column(String, index=True)
    prix = Column(Float)