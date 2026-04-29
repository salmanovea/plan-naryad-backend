from src.config.admin.categories import CATEGORY_CONTRACTORS
from src.config.admin.model_admin.base_admin import BaseAdmin
from src.models.dbo.tables.contractor import Contractor, ContractorAssignment


class ContractorAdmin(BaseAdmin, model=Contractor):  # type: ignore[call-arg]
    category = CATEGORY_CONTRACTORS
    name = "Подрядчик"
    name_plural = "Подрядчики"
    icon = "fa-solid fa-hard-hat"

    column_list = [
        Contractor.id,
        Contractor.name,
        Contractor.short_name,
        Contractor.inn,
        Contractor.contact_person,
        Contractor.phone,
        Contractor.raport_id,
    ]
    column_details_list = [
        Contractor.id,
        Contractor.name,
        Contractor.short_name,
        Contractor.inn,
        Contractor.contact_person,
        Contractor.phone,
        Contractor.email,
        Contractor.description,
        Contractor.raport_id,
    ]
    form_columns = [
        Contractor.name,
        Contractor.short_name,
        Contractor.inn,
        Contractor.contact_person,
        Contractor.phone,
        Contractor.email,
        Contractor.description,
        Contractor.raport_id,
    ]
    column_searchable_list = [
        Contractor.name,
        Contractor.short_name,
        Contractor.inn,
        Contractor.raport_id,
    ]
    column_sortable_list = [Contractor.name, Contractor.short_name]


class ContractorAssignmentAdmin(BaseAdmin, model=ContractorAssignment):  # type: ignore[call-arg]
    category = CATEGORY_CONTRACTORS
    name = "Назначение подрядчика"
    name_plural = "Назначения подрядчиков"
    icon = "fa-solid fa-link"

    column_list = [
        ContractorAssignment.id,
        ContractorAssignment.contractor,
        ContractorAssignment.housing,
        ContractorAssignment.section,
        ContractorAssignment.work_group,
    ]
    column_details_list = [
        ContractorAssignment.id,
        ContractorAssignment.contractor,
        ContractorAssignment.housing,
        ContractorAssignment.section,
        ContractorAssignment.work_group,
        ContractorAssignment.work_type_ids,
    ]
    form_columns = [
        ContractorAssignment.contractor,
        ContractorAssignment.housing,
        ContractorAssignment.section,
        ContractorAssignment.work_group,
        ContractorAssignment.work_type_ids,
    ]
    column_sortable_list: list = []
