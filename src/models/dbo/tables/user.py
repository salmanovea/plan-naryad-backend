from typing import List, Optional

from sqlalchemy import ARRAY, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.dbo.base_model import Base
from src.models.dbo.mixins import IDMixin, RaportMixin


class User(IDMixin, RaportMixin, Base):
    """User directory synced from Raport (`GET /api/v1/users`).

    `groups` holds Keycloak role/group names; `project_ids` / `contractor_ids`
    store the Raport ids the user is scoped to (the matching local rows live in
    `wf_projects` / `contractors`, keyed by the same `raport_id`).
    """

    __tablename__ = "users"

    last_name: Mapped[Optional[str]] = mapped_column(String(255))
    first_name: Mapped[Optional[str]] = mapped_column(String(255))
    middle_name: Mapped[Optional[str]] = mapped_column(String(255))
    shown_name: Mapped[Optional[str]] = mapped_column(String(500))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    is_external: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    groups: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    project_ids: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)
    contractor_ids: Mapped[List[str]] = mapped_column(ARRAY(String), default=list)

    def __str__(self) -> str:
        return self.shown_name or self.email or str(self.id)
