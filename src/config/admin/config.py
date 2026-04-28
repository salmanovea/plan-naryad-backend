from fastapi import FastAPI
from sqladmin import Admin

from src.config.admin.model_admin.contractor import ContractorAdmin, ContractorAssignmentAdmin
from src.config.admin.model_admin.housing import FloorAdmin, HousingAdmin, SectionAdmin
from src.config.admin.model_admin.sync_actions import SyncActionsAdmin
from src.config.admin.model_admin.work import WorkGroupAdmin, WorkTypeAdmin
from src.config.admin.model_admin.workforce import WfProjectAdmin, WfProjectObjectAdmin
from src.config.postgres.db_config import async_engine


def init_admin(app: FastAPI) -> Admin:
    admin = Admin(app=app, engine=async_engine, title="Plan-naryad Admin")

    # Project structure
    admin.add_view(WfProjectAdmin)
    admin.add_view(WfProjectObjectAdmin)
    admin.add_view(HousingAdmin)
    admin.add_view(SectionAdmin)
    admin.add_view(FloorAdmin)

    # Work catalog
    admin.add_view(WorkGroupAdmin)
    admin.add_view(WorkTypeAdmin)

    # Contractors
    admin.add_view(ContractorAdmin)
    admin.add_view(ContractorAssignmentAdmin)

    # Sync
    admin.add_view(SyncActionsAdmin)

    return admin
