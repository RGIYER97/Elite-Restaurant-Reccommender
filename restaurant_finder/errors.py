"""Domain-specific exceptions with user-safe messages."""


class GoogleMapsError(RuntimeError):
    """Base exception for Google Maps Platform requests."""


class InvalidLocationError(GoogleMapsError):
    """The submitted location or request was not understood."""


class AuthenticationError(GoogleMapsError):
    """The key, API enablement, restrictions, or billing is invalid."""


class RateLimitError(GoogleMapsError):
    """Google rejected the request because its quota was exhausted."""


class GoogleServiceError(GoogleMapsError):
    """Google or the network failed while servicing the request."""
