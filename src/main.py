from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.authentication import AuthenticationMiddleware

from src.api.v1.alert.views import alert_router
from src.api.v1.contractor.views import contractor_router
from src.api.v1.dashboard.views import dashboard_router
from src.api.v1.fact.views import fact_router
from src.api.v1.housing.views import housing_router
from src.api.v1.plan.views import plan_router
from src.api.v1.reconciliation.views import reconciliation_router
from src.api.v1.sync.views import sync_router
from src.api.v1.work.views import work_router
from src.api.v1.workforce.views import workforce_router
from src.config.admin.config import init_admin
from src.config.logger import LoggerProvider
from src.config.postgres.db_config import async_engine
from src.config.settings import app_config
from src.middlewares.keycloak_middleware import KeycloakMiddleware

log = LoggerProvider().get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Plan-naryad API...")
    yield
    log.info("Shutting down Plan-naryad API...")
    await async_engine.dispose()


app = FastAPI(
    title=app_config.project_title,
    docs_url=app_config.project_api_prefix + app_config.project_docs_url,
    openapi_url=app_config.project_api_prefix + app_config.project_openapi_url,
    version=app_config.project_docs_version,
    lifespan=lifespan,
)

app.add_middleware(AuthenticationMiddleware, backend=KeycloakMiddleware())

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_PREFIX = app_config.project_api_prefix
app.include_router(housing_router, prefix=_PREFIX)
app.include_router(work_router, prefix=_PREFIX)
app.include_router(contractor_router, prefix=_PREFIX)
app.include_router(fact_router, prefix=_PREFIX)
app.include_router(plan_router, prefix=_PREFIX)
app.include_router(reconciliation_router, prefix=_PREFIX)
app.include_router(alert_router, prefix=_PREFIX)
app.include_router(dashboard_router, prefix=_PREFIX)
app.include_router(workforce_router, prefix=_PREFIX)
app.include_router(sync_router, prefix=_PREFIX)

init_admin(app)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    log.info("Starting server...")
    uvicorn.run(
        "src.main:app",
        host=app_config.project_host,
        port=app_config.project_port,
        reload=True,
    )
