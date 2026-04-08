from importlib import import_module
from typing import Optional

from hikvision.sdk import error_codes


class HikvisionSdkError(Exception):
    def __init__(self, operation: str, error_code: int, message: Optional[str] = None):
        self.operation = operation
        self.error_code = int(error_code)
        details = message or _format_error(error_code)
        super().__init__(f"{operation} failed: {details} (code={self.error_code})")


class HikvisionDeviceError(HikvisionSdkError):
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