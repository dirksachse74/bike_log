"""Domain errors, mapped to HTTP status codes by the API layer."""
from __future__ import annotations


class DomainError(Exception):
    status = 400

    def __init__(self, message: str, **details):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFound(DomainError):
    status = 404


class Conflict(DomainError):
    status = 409


class Protected(DomainError):
    status = 409
