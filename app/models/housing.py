from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, Optional

from ..database import Base


class Housing(Base):
    """Корпус/дом в составе ЖК"""
    __tablename__ = "housings"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    complex_name: Mapped[str] = mapped_column(String(255), nullable=False)  # Название ЖК
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    
    # Связи
    sections: Mapped[List["Section"]] = relationship(back_populates="housing", cascade="all, delete-orphan")


class Section(Base):
    """Секция в составе корпуса"""
    __tablename__ = "sections"
    
    housing_id: Mapped[str] = mapped_column(ForeignKey("housings.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    section_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Связи
    housing: Mapped["Housing"] = relationship(back_populates="sections")
    floors: Mapped[List["Floor"]] = relationship(back_populates="section", cascade="all, delete-orphan")


class Floor(Base):
    """Этаж в составе секции"""
    __tablename__ = "floors"
    
    section_id: Mapped[str] = mapped_column(ForeignKey("sections.id"))
    floor_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3... или -1 (подвал)
    name: Mapped[Optional[str]] = mapped_column(String(100))  # "1-й этаж", "Подвал", "Тех. этаж"
    description: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Связи
    section: Mapped["Section"] = relationship(back_populates="floors")