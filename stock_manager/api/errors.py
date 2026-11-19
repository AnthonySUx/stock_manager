"""Stable error codes for new API endpoints."""


class APIError(Exception):
    """Expose a stable code and optional parameters alongside English detail."""

    def __init__(self, status_code: int, code: str, detail: str = "", **params):
        super().__init__(detail or code)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.params = params
