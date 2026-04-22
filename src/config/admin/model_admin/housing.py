from src.config.admin.categories import CATEGORY_PROJECT_STRUCTURE
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.housing import Floor, Housing, Section


class HousingAdmin(BaseAdmin, model=Housing):  # type: ignore[call-arg]
    category = CATEGORY_PROJECT_STRUCTURE
    name = "Корпус"
    name_plural = "Корпуса"
    icon = "fa-solid fa-building"

    column_list = [
        Housing.id,
        Housing.name,
        Housing.complex_name,
        Housing.construction_object_id,
        Housing.raport_id,
    ]
    column_details_list = [
        Housing.id,
        Housing.name,
        Housing.complex_name,
        Housing.description,
        Housing.construction_object_id,
        Housing.raport_id,
    ]
    form_columns = [
        Housing.name,
        Housing.complex_name,
        Housing.description,
        Housing.construction_object_id,
        Housing.raport_id,
    ]
    column_searchable_list = [Housing.name, Housing.complex_name, Housing.raport_id]
    column_sortable_list = [Housing.name, Housing.complex_name]


class SectionAdmin(BaseAdmin, model=Section):  # type: ignore[call-arg]
    category = CATEGORY_PROJECT_STRUCTURE
    name = "Секция"
    name_plural = "Секции"
    icon = "fa-solid fa-layer-group"

    column_list = [
        Section.id,
        Section.housing_id,
        Section.name,
        Section.section_number,
        Section.raport_id,
    ]
    column_details_list = [
        Section.id,
        Section.housing_id,
        Section.name,
        Section.section_number,
        Section.description,
        Section.raport_id,
    ]
    form_columns = [
        Section.housing_id,
        Section.name,
        Section.section_number,
        Section.description,
        Section.raport_id,
    ]
    column_searchable_list = [Section.name, Section.raport_id]
    column_sortable_list = [Section.section_number, Section.name]


class FloorAdmin(BaseAdmin, model=Floor):  # type: ignore[call-arg]
    category = CATEGORY_PROJECT_STRUCTURE
    name = "Этаж"
    name_plural = "Этажи"
    icon = "fa-solid fa-stairs"

    column_list = [
        Floor.id,
        Floor.section_id,
        Floor.floor_number,
        Floor.name,
        Floor.raport_id,
    ]
    column_details_list = [
        Floor.id,
        Floor.section_id,
        Floor.floor_number,
        Floor.name,
        Floor.description,
        Floor.raport_id,
    ]
    form_columns = [
        Floor.section_id,
        Floor.floor_number,
        Floor.name,
        Floor.description,
        Floor.raport_id,
    ]
    column_searchable_list = [Floor.name, Floor.raport_id]
    column_sortable_list = [Floor.floor_number]
