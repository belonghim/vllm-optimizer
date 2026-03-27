"""
Domain error classes for vLLM Optimizer.

This module defines a flat hierarchy of domain-specific exceptions
for error handling across the backend.
"""


class OptimizerError(Exception):
    """Base exception for all optimizer domain errors."""

    def __init__(self, message: str, detail: dict | None = None):
        """Initialize optimizer error.

        Args:
            message: Error message
            detail: Optional error detail dictionary
        """
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


class StorageError(OptimizerError):
    """Raised when storage operations fail."""

    pass


class MetricsError(OptimizerError):
    """Raised when metrics collection or querying fails."""

    pass


class LoadTestError(OptimizerError):
    """Raised when load test execution fails."""

    pass


class TunerError(OptimizerError):
    """Raised when auto-tuner operations fail."""

    pass


class ConfigError(OptimizerError):
    """Raised when configuration operations fail."""

    pass


class VllmServiceError(OptimizerError):
    """Raised when vLLM service operations fail."""

    pass
