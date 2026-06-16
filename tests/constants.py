"""Shared test constants.

`API` is the configured API prefix (`app_config.project_api_prefix`) so tests
build URLs from the same prefix the routers are mounted under, instead of a
hardcoded `/api/v1`.
"""

from src.config.settings import app_config

API = app_config.project_api_prefix
