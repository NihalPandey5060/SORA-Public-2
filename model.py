from sqlalchemy import Column, Integer, String, Text # type: ignore #
from db import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    first_name = Column(String)
    last_name = Column(String)

class MenuItem(Base):
    __tablename__ = "menu_items"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
    description = Column(Text)
    price = Column(Integer)
    category = Column(String, index=True)