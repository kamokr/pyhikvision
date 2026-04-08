"""Hikvision SDK Python bindings.

This package provides Python bindings for the Hikvision SDK, allowing users to interact with Hikvision devices such as cameras and DVRs. It includes both high-level, user-friendly interfaces for common tasks, as well as low-level access to the raw SDK functions for advanced users. The main modules are:
- `hikvision`: High-level, Pythonic interface for common operations like login, search, and playback.
- `hikvision.net_dvr`: Middle-level bindings that provide a more Pythonic interface while still allowing access to the underlying SDK functions.
- `hikvision.sdk`: Low-level bindings that expose the raw C API functions and data structures of the Hikvision SDK."""
from __future__ import annotations

from .device import *
from .playback_stream import *

__all__ = [
    "HikvisionDevice",
    "HikvisionDeviceError",
    "PlaybackMode",
    "PlaybackPacket",
    "PlaybackPacketType",
    "PlaybackStream",
    "TransportType",
]

try:
    from importlib.metadata import version

    __version__ = version("pyhikvision")
except Exception:
    __version__ = "0.0.0"