from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.dbo.mixins import IDMixin, RaportMixin
from src.models.dbo.base_model import Base


class Contractor(IDMixin, RaportMixin, Base):
    """Contractor company.

    Operational assignments (contractor × section × floor × work) are NOT stored here —
    they are read from Raport `GET /api/v1/contractor-works` on demand, see the Р1
    decision in docs/to-be-plan.md.
    """

    __tablename__ = "contractors"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str] = mapped_column(String(100), nullable=False)
    inn: Mapped[Optional[str]] = mapped_column(String(20))
    contact_person: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    email: Mapped[Optional[str]] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(String(1000))

    def __str__(self) -> str:
        return self.name
