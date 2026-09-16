from src.config.admin.categories import CATEGORY_RECONCILIATION
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.alert import Alert


class AlertAdmin(BaseAdmin, model=Alert):  # type: ignore[call-arg]
    category = CATEGORY_RECONCILIATION
    name = "Алерт"
    name_plural = "Алерты"
    icon = "fa-solid fa-bell"

    column_list = [
        Alert.id,
        Alert.date,
        Alert.alert_type,
        Alert.level,
        Alert.housing,
        Alert.contractor,
        Alert.acknowledged,
        Alert.escalation_level,
        Alert.created_at,
    ]
    column_details_list = [
        Alert.id,
        Alert.date,
        Alert.alert_type,
        Alert.level,
        Alert.housing,
        Alert.contractor,
        Alert.recipient_id,
        Alert.recipient_role,
        Alert.message,
        Alert.acknowledged,
        Alert.acknowledged_at,
        Alert.acknowledged_by,
        Alert.escalation_level,
        Alert.escalated_at,
        Alert.created_at,
    ]
    form_columns = [
        Alert.date,
        Alert.alert_type,
        Alert.level,
        Alert.message,
        Alert.acknowledged,
    ]
    # housing / contractor are nullable — ids only, a dotted join would hide
    # system-wide alerts from every search.
    column_searchable_list = [
        Alert.date,
        Alert.alert_type,
        Alert.level,
        Alert.housing_id,
        Alert.contractor_id,
        Alert.recipient_id,
        Alert.acknowledged_by,
    ]
    column_sortable_list = [Alert.date, Alert.level, Alert.created_at]
    column_default_sort = [("created_at", True)]
