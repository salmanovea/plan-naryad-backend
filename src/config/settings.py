import os
from typing import Optional

from pydantic_settings import BaseSettings

DOCS_URL = "/api/openapi"
OPENAPI_URL = "/api/openapi.json"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AppConfig(BaseSettings):
    project_title: str = "Plan-naryad API"
    project_host: str = "0.0.0.0"
    project_port: int = 8090
    project_api_prefix: str = "/api"
    project_docs_url: str = "/openapi"
    project_docs_version: str = "1.0.0"
    project_openapi_url: str = "/openapi.json"

    db_driver_name: str = "postgresql+asyncpg"
    db_host: str = "localhost"
    db_port: str = "5433"
    db_name: str = "plan_naryad"
    db_user: str = "pn_user"
    db_pass: str = "pn_secret"
    db_show_queries: bool = False
    db_test_database_name: str = "plan_naryad_test"

    # Business logic limits
    max_items_per_contractor: int = 10
    # Floors of one work a single contractor may get in one day plan when
    # `contractor_floor_limits` holds no row for them (decision Р8).
    default_floor_limit: int = 4
    # Until this hour (business time, see app_timezone) an unscheduled generation targets
    # today; later it targets tomorrow — today's plan has already gone out (Р3).
    plan_transfer_cutoff_hour: int = 10
    # The business timezone: fact dates and the cutoff hour are computed in it regardless
    # of the container's TZ.
    app_timezone: str = "Europe/Moscow"

    # Keycloak — connection params of the Raport client (this service has no client of its own)
    keycloak_server_url: Optional[str] = None
    keycloak_realm: Optional[str] = None
    keycloak_verify_ssl: bool = True

    # Authentication lives in src/middlewares/raport_auth and reads its own AUTH_* variables —
    # the block is copied between services as a whole, so it does not depend on this config.
    # Only the switch is duplicated here, to keep the admin UI and CORS in step with it.
    auth_enabled: bool = False

    admin_keycloak_client_id: Optional[str] = None
    admin_allowed_groups: str = "superuser"
    admin_session_ttl: int = 3600
    admin_session_secret: Optional[str] = None

    # Redis — shared cache for authorization answers.
    redis_url: str = "redis://localhost:6379"

    # Comma-separated CORS origins, or "*" for any.
    cors_allow_origins: str = "*"

    # Raport ecosystem — external data source
    report_api_url: Optional[str] = None
    report_keycloak_client_id: Optional[str] = None
    report_keycloak_client_secret: Optional[str] = None
    report_keycloak_username: Optional[str] = None
    report_keycloak_password: Optional[str] = None
    # Service client for machine-to-machine calls to Raport (its /authz endpoint). Usually a
    # different client from the one above: the client that serves password grants is public on
    # our stands, and a public client cannot issue client_credentials at all. Falls back to the
    # pair above when unset.
    report_service_client_id: Optional[str] = None
    report_service_client_secret: Optional[str] = None

    @property
    def admin_groups(self) -> set[str]:
        return {group.strip() for group in self.admin_allowed_groups.split(",") if group.strip()}

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def get_db_creds(self):
        return {
            "drivername": self.db_driver_name,
            "username": self.db_user,
            "host": self.db_host,
            "port": self.db_port,
            "database": self.db_name,
            "password": self.db_pass,
        }

    class Config:
        env_file = ".env"
        # Other blocks own their own variables (AUTH_* belongs to src/middlewares/raport_auth),
        # and they live in the same .env. Without this the service refuses to start as soon as
        # one of them appears.
        extra = "ignore"


app_config = AppConfig()
