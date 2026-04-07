"""
Public API for the hikvision package.

This initializer also provides compatibility shims for legacy absolute
imports used inside device.py (import sdk / from errors import *).
"""
from __future__ import annotations

import sys

# Compatibility aliases for legacy absolute imports inside package modules.
from . import errors as _errors
from . import sdk as _sdk

sys.modules.setdefault("errors", _errors)
sys.modules.setdefault("sdk", _sdk)

# Public exports.
from .device import (
    DeviceInfo,
    HikvisionConnectError,
    HikvisionDevice,
    HikvisionDeviceError,
    HikvisionPlaybackError,
    HikvisionSearchError,
    TransportType,
    PlaybackMode,
    PlaybackPacket,
    PlaybackPacketType,
    PlaybackStream,
    cleanup_sdk,
    initialize_sdk,
    is_sdk_initialized,
    RecordingFileType,
    Recording,
)

__all__ = [
    "DeviceInfo",
    "HikvisionConnectError",
    "HikvisionDevice",
    "HikvisionDeviceError",
    "HikvisionPlaybackError",
    "HikvisionSearchError",
    "PlaybackMode",
    "PlaybackPacket",
    "PlaybackPacketType",
    "PlaybackStream",
    "cleanup_sdk",
    "initialize_sdk",
    "is_sdk_initialized",
    "RecordingFileType",
    "TransportType",
    "Recording",
]

try:
    from importlib.metadata import version

    __version__ = version("pyhikvision")
except Exception:
    __version__ = "0.0.0"