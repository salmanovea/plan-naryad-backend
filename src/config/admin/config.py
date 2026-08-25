from fastapi import FastAPI
from sqladmin import Admin

from starlette.routing import Route

from src.config.admin.auth import CALLBACK_PATH, build_admin_auth
from src.config.admin.model_admin.contractor import ContractAdmin, ContractorAdmin
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


ADMIN_BASE_URL = "/pn/admin"


def init_admin(app: FastAPI) -> Admin:
    auth_backend = build_admin_auth(ADMIN_BASE_URL)
    admin = Admin(
        app=app,
        engine=async_engine,
        title="Plan-naryad Admin",
        base_url=ADMIN_BASE_URL,
        authentication_backend=auth_backend,
    )

    if auth_backend is not None:
        admin.admin.router.routes.insert(0, Route(CALLBACK_PATH, endpoint=auth_backend.callback, name="oauth_callback"))
        admin.admin.router.routes.insert(0, Route("/login", endpoint=auth_backend.authorize_redirect, name="sso_login"))

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
