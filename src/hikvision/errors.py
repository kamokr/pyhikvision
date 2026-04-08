from importlib import import_module
from typing import Optional

from hikvision.sdk import error_codes


class HikvisionSdkError(Exception):
    """Base exception for all SDK-related errors.
    
    This is the base class for all exceptions raised by the Hikvision SDK. It is not meant to be raised directly, but can be used to catch any SDK-related error.
    
    Attributes:
        operation: The name of the SDK operation that failed, e.g. "Login", "StartPlayback", etc.
        error_code: The integer error code returned by the SDK, e.g. 1 for "NET_DVR_PASSWORD_ERROR".
        message: An optional human-readable message describing the error in more detail.
    """
    def __init__(self, operation: str, error_code: int, message: Optional[str] = None):
        self.operation = operation
        self.error_code = int(error_code)
        details = message or _format_error(error_code)
        super().__init__(f"{operation} failed: {details} (code={self.error_code})")


class HikvisionDeviceError(HikvisionSdkError):
    """Exception raised for device-specific errors."""
    pass


def _format_error(error_code: int) -> str:
    for name, value in vars(error_codes).items():
        if name.startswith("NET_DVR_") and isinstance(value, int) and value == int(error_code):
            return name
    return "NET_DVR_UNKNOWN_ERROR"


__all__ = [
    "HikvisionSdkError",
    "HikvisionDeviceError",
]