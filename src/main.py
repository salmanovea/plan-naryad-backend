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
from src.config.redis import redis
from src.external.report.auth import get_report_service_token
from src.middlewares.raport_auth import RaportAuthBackend, on_auth_error, validate_auth_settings

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

# Fail fast: a half-configured auth block would otherwise show up as «everybody has access».
validate_auth_settings()

# CORS is added last, therefore it wraps the authentication middleware — without that a 401
# would come back without CORS headers and the browser would report a network error instead.
app.add_middleware(
    AuthenticationMiddleware,
    backend=RaportAuthBackend(
        redis_client=redis,
        service_token_provider=get_report_service_token,
        public_routes=(app.docs_url or "", app.openapi_url or "", "/health", "/favicon.ico"),
        # The admin UI is skipped here and closed by its own sign-in form (src/config/admin/auth.py):
        # a browser cannot attach a Bearer header, so a 401 here would make it unreachable.
        public_route_prefixes=("/pn/admin",),
    ),
    on_error=on_auth_error,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_config.cors_origins,
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
