from sqlalchemy import String, ForeignKey, ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, Optional

from ..database import Base


class Contractor(Base):
    """Подрядчик"""
    __tablename__ = "contractors"
    
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    inn: Mapped[Optional[str]] = mapped_column(String(20))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Связи
    assignments: Mapped[List["ContractorAssignment"]] = relationship(back_populates="contractor", cascade="all, delete-orphan")


class ContractorAssignment(Base):
    """Привязка подрядчика к видам работ на объекте"""
    __tablename__ = "contractor_assignments"
    
    contractor_id: Mapped[str] = mapped_column(ForeignKey("contractors.id"))
    housing_id: Mapped[str] = mapped_column(ForeignKey("housings.id"))
    section_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sections.id"))  # null = все секции
    work_group_id: Mapped[Optional[str]] = mapped_column(ForeignKey("work_groups.id"))  # Группа работ
    work_type_ids: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)  # Конкретные виды работ
    
    # Связи
    contractor: Mapped["Contractor"] = relationship(back_populates="assignments")
    housing: Mapped["Housing"] = relationship()
    section: Mapped[Optional["Section"]] = relationship()
    work_group: Mapped[Optional["WorkGroup"]] = relationship()