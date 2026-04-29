from sqladmin import ModelView


class BaseAdmin(ModelView):
    """Shared defaults for all admin views."""

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    column_default_sort = [("id", False)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]
