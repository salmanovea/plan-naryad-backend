from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.dbo.base_model import Base
from src.models.dbo.mixins import IDMixin, RaportMixin

if TYPE_CHECKING:
    from src.models.dbo.tables.contractor import Contractor


class Contract(IDMixin, RaportMixin, Base):
    """Contractor contract synced from Raport.

    Terminology (docs/sync-mapping.md §1.3): the contract identifier field is
    `subject` (Raport unified `number` → `subject`).
    """

    __tablename__ = "contracts"

    contractor_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("contractors.id", name="fk_contracts_contractor_id"),
        nullable=True,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(500))
    subject: Mapped[Optional[str]] = mapped_column(Text)
    is_warranty_letter: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    contractor: Mapped[Optional["Contractor"]] = relationship()

    def __str__(self) -> str:
        return self.name or self.subject or str(self.id)
