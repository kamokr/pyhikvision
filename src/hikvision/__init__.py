"""Hikvision SDK Python bindings."""
from __future__ import annotations

from . import net
from hikvision.constants import DEFAULT_CONNECT_TIMEOUT_MS, DEFAULT_RECV_TIMEOUT_MS
from hikvision.enums import RecordingFileType
from hikvision.errors import HikvisionDeviceError, HikvisionSdkError
from hikvision.net.dvr import LoginError, LogoutError, SearchError, PlaybackError

from .device import (
    DeviceInfo,
    HikvisionDevice,
    Recording,
)

from .playback_stream import (
    TransportType,
    PlaybackMode,
    PlaybackPacket,
    PlaybackPacketType,
    PlaybackStream
)

__all__ = [
    "DeviceInfo",
    "HikvisionDevice",
    "HikvisionDeviceError",
    "HikvisionSdkError",
    "LoginError",
    "LogoutError",
    "PlaybackError",
    "PlaybackMode",
    "PlaybackPacket",
    "PlaybackPacketType",
    "PlaybackStream",
    "SearchError",
    "DEFAULT_CONNECT_TIMEOUT_MS",
    "DEFAULT_RECV_TIMEOUT_MS",
    "RecordingFileType",
    "TransportType",
    "Recording",
]

try:
    from importlib.metadata import version

    __version__ = version("pyhikvision")
except Exception:
    __version__ = "0.0.0"