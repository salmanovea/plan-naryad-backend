from fastapi import FastAPI
from sqladmin import Admin

from src.config.admin.model_admin.contractor import ContractAdmin, ContractorAdmin, ContractorAssignmentAdmin
from src.config.admin.model_admin.housing import FloorAdmin, HousingAdmin, SectionAdmin
from src.config.admin.model_admin.project_structure import (
    ConstructionObjectAdmin,
    ProjectAdmin,
    QueueAdmin,
)
from src.config.admin.model_admin.sync_actions import SyncActionsAdmin
from src.config.admin.model_admin.user import UserAdmin
from src.config.admin.model_admin.work import WorkAdmin, WorkGroupAdmin, WorkSetAdmin, WorkTypeAdmin
from src.config.admin.model_admin.workforce import ArticleBDRAdmin, ArticleBDRWorkAdmin
from src.config.postgres.db_config import async_engine


def init_admin(app: FastAPI) -> Admin:
    admin = Admin(
        app=app,
        engine=async_engine,
        title="Plan-naryad Admin",
        base_url=f"/pn/admin",
    )

    # Project structure
    admin.add_view(ProjectAdmin)
    admin.add_view(QueueAdmin)
    admin.add_view(ConstructionObjectAdmin)
    admin.add_view(HousingAdmin)
    admin.add_view(SectionAdmin)
    admin.add_view(FloorAdmin)

    # Work catalog
    admin.add_view(WorkSetAdmin)
    admin.add_view(WorkGroupAdmin)
    admin.add_view(WorkTypeAdmin)
    admin.add_view(WorkAdmin)

    # Contractors
    admin.add_view(ContractorAdmin)
    admin.add_view(ContractAdmin)

    # Workforce
    admin.add_view(ArticleBDRAdmin)
    admin.add_view(ArticleBDRWorkAdmin)

    # System
    admin.add_view(UserAdmin)

    # Sync
    admin.add_view(SyncActionsAdmin)

    return admin
