class SatelliteError(Exception):
    """Base class for acquisition failures."""


class InvalidAOIError(SatelliteError):
    pass


class InvalidDateError(SatelliteError):
    pass


class NoSceneFoundError(SatelliteError):
    pass


class InvalidScenePairError(SatelliteError):
    pass


class AuthenticationError(SatelliteError):
    pass


class ProcessAPIAuthError(AuthenticationError):
    pass


class NoCredentialsError(AuthenticationError):
    pass


class CatalogUnavailableError(SatelliteError):
    pass


class CatalogNoMatchError(CatalogUnavailableError):
    pass


class CatalogAmbiguousError(CatalogUnavailableError):
    pass


class CatalogValidationError(CatalogUnavailableError):
    pass


class DownloadError(SatelliteError):
    pass


class ProcessAPIRequestError(DownloadError):
    def __init__(self, message: str, diagnostics: dict | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class IntegrityError(DownloadError):
    pass


class RateLimitError(CatalogUnavailableError):
    pass
