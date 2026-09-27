"""Domain-specific exceptions, translated to HTTP responses in app/main.py."""


class URLShortenerError(Exception):
    """Base class for all domain errors."""

    status_code: int = 400
    error_code: str = "error"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class InvalidURLError(URLShortenerError):
    status_code = 422
    error_code = "invalid_url"


class AliasUnavailableError(URLShortenerError):
    status_code = 409
    error_code = "alias_unavailable"


class URLNotFoundError(URLShortenerError):
    status_code = 404
    error_code = "url_not_found"


class URLGoneError(URLShortenerError):
    """Raised when a URL exists but is expired or soft-deleted."""

    status_code = 410
    error_code = "url_gone"


class RateLimitExceededError(URLShortenerError):
    status_code = 429
    error_code = "rate_limit_exceeded"


class CodeGenerationExhaustedError(URLShortenerError):
    status_code = 503
    error_code = "code_generation_exhausted"
