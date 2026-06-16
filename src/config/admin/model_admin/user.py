from src.config.admin.categories import CATEGORY_SYSTEM
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.user import User


class UserAdmin(BaseAdmin, model=User):  # type: ignore[call-arg]
    category = CATEGORY_SYSTEM
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"

    column_list = [
        User.id,
        User.shown_name,
        User.email,
        User.is_external,
        User.raport_id,
    ]
    column_details_list = [
        User.id,
        User.last_name,
        User.first_name,
        User.middle_name,
        User.shown_name,
        User.email,
        User.is_external,
        User.groups,
        User.project_ids,
        User.contractor_ids,
        User.raport_id,
    ]
    form_columns = [
        User.last_name,
        User.first_name,
        User.middle_name,
        User.shown_name,
        User.email,
        User.is_external,
        User.groups,
        User.project_ids,
        User.contractor_ids,
        User.raport_id,
    ]
    column_searchable_list = [User.shown_name, User.email, User.raport_id]
    column_sortable_list = [User.shown_name, User.email]
