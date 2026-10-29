"""Domain failures translated into HTTP responses by the API layer."""


class AccessError(Exception):
    """Base class for authorization and selection failures."""


class AccessDenied(AccessError):
    """The caller cannot perform the requested business operation."""


class AuthenticationRequired(AccessError):
    """An authenticated principal is required."""


class InvalidHierarchy(AccessError):
    """Selected entities do not belong to the same parent hierarchy."""


class PlanLocked(Exception):
    """A plan change refused: the day is past its transfer time, or the position already went to the contractor."""
