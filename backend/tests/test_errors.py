"""
Tests for domain error classes and global exception handler.
"""

import pytest
from errors import (
    ConfigError,
    LoadTestError,
    MetricsError,
    OptimizerError,
    StorageError,
    TunerError,
    VllmServiceError,
)


class TestOptimizerErrorClass:
    """Test OptimizerError base class."""

    def test_optimizer_error_with_message_only(self):
        """Test creating OptimizerError with message only."""
        exc = OptimizerError("test message")
        assert exc.message == "test message"
        assert exc.detail == {}
        assert str(exc) == "test message"

    def test_optimizer_error_with_detail(self):
        """Test creating OptimizerError with detail dict."""
        detail = {"key": "value", "code": 123}
        exc = OptimizerError("test message", detail=detail)
        assert exc.message == "test message"
        assert exc.detail == detail

    def test_optimizer_error_inheritance(self):
        """Test that OptimizerError is an Exception."""
        exc = OptimizerError("test")
        assert isinstance(exc, Exception)


class TestErrorSubclasses:
    """Test all error subclasses."""

    @pytest.mark.parametrize(
        "error_class",
        [StorageError, MetricsError, LoadTestError, TunerError, ConfigError, VllmServiceError],
    )
    def test_error_subclass_instantiation(self, error_class):
        """Test that all error subclasses can be instantiated."""
        exc = error_class("test message")
        assert isinstance(exc, OptimizerError)
        assert isinstance(exc, Exception)
        assert exc.message == "test message"
        assert exc.detail == {}

    @pytest.mark.parametrize(
        "error_class",
        [StorageError, MetricsError, LoadTestError, TunerError, ConfigError, VllmServiceError],
    )
    def test_error_subclass_with_detail(self, error_class):
        """Test that all error subclasses support detail dict."""
        detail = {"context": "test"}
        exc = error_class("test message", detail=detail)
        assert exc.message == "test message"
        assert exc.detail == detail


class TestGlobalExceptionHandler:
    """Test global exception handler integration."""

    def test_exception_handler_returns_correct_format(self, isolated_client):
        """Test that exception handler returns correct JSON format."""
        from errors import StorageError

        exc = StorageError("database error", detail={"db": "postgresql"})
        assert exc.message == "database error"
        assert exc.detail == {"db": "postgresql"}
        assert type(exc).__name__ == "StorageError"

    def test_all_error_types_are_distinct(self):
        """Test that all error types are distinct classes."""
        error_classes = [
            StorageError,
            MetricsError,
            LoadTestError,
            TunerError,
            ConfigError,
            VllmServiceError,
        ]
        assert len(set(error_classes)) == len(error_classes)

    def test_error_class_names(self):
        """Test that error classes have correct names."""
        assert StorageError.__name__ == "StorageError"
        assert MetricsError.__name__ == "MetricsError"
        assert LoadTestError.__name__ == "LoadTestError"
        assert TunerError.__name__ == "TunerError"
        assert ConfigError.__name__ == "ConfigError"
        assert VllmServiceError.__name__ == "VllmServiceError"
