"""HTTP adapter for section permissions; data selectors belong to domain services."""

from fastapi import Depends, Request
from starlette.responses import JSONResponse

from src.config.settings import app_config
from src.middlewares.raport_auth.settings import auth_settings
from src.services.access import AccessScope, AccessService, PlanRole, get_access_service
from src.utils.exceptions import AccessError, AuthenticationRequired, InvalidHierarchy


def access_error_response(error: AccessError) -> JSONResponse:
    """Translate domain authorization failures into the shared response contract."""
    status_code = (
        401 if isinstance(error, AuthenticationRequired) else 400 if isinstance(error, InvalidHierarchy) else 403
    )
    return JSONResponse(status_code=status_code, content={"code": str(status_code), "message": str(error)})


async def plan_access(request: Request, service: AccessService = Depends(get_access_service)) -> AccessScope:
    """Install the authenticated principal and check access to this API operation."""
    user = request.user
    if user.is_authenticated:
        scope = AccessScope.from_user(user)
    elif auth_settings.auth_enabled:
        raise AuthenticationRequired("Требуется авторизация.")
    else:
        scope = AccessScope(PlanRole.LOCAL)
    service.initialize(scope)
    path = request.scope["route"].path.removeprefix(app_config.project_api_prefix)
    service.authorize_operation(request.method, path)
    return scope
