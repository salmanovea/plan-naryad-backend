from src.config.admin.categories import CATEGORY_SYSTEM
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.settings import ActionLog


class ActionLogAdmin(BaseAdmin, model=ActionLog):  # type: ignore[call-arg]
    """Read-only on purpose: an editable audit trail is not an audit trail."""

    category = CATEGORY_SYSTEM
    name = "Запись аудита"
    name_plural = "Аудит-журнал"
    icon = "fa-solid fa-clock-rotate-left"

    can_create = False
    can_edit = False
    can_delete = False

    column_list = [
        ActionLog.id,
        ActionLog.created_at,
        ActionLog.action,
        ActionLog.entity_type,
        ActionLog.entity_id,
        ActionLog.actor,
    ]
    column_details_list = [
        ActionLog.id,
        ActionLog.created_at,
        ActionLog.action,
        ActionLog.entity_type,
        ActionLog.entity_id,
        ActionLog.actor,
        ActionLog.payload,
    ]
    column_searchable_list = [ActionLog.action, ActionLog.actor]
    column_sortable_list = [ActionLog.created_at, ActionLog.action]
    column_default_sort = [("created_at", True)]
