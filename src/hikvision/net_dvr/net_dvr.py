"""Lightweight Pythonic wrappers for the HCNetSDK calls used by this package."""

from __future__ import annotations

import ctypes
import datetime
from dataclasses import dataclass
from enum import IntEnum
import logging
import threading
from typing import Any, Callable, Optional

from hikvision.constants import DEFAULT_CONNECT_TIMEOUT_MS, DEFAULT_RECV_TIMEOUT_MS
from hikvision.errors import HikvisionSdkError
from ..sdk import sdk


LOG = logging.getLogger(__name__)


class RecordingFileType(IntEnum):
    ALL = 0xFF
    CONTINUOUS = 0
    MOTION_DETECTION = 1
    ALARM = 2
    ALARM_OR_MOTION = 3
    ALARM_AND_MOTION = 4
    COMMAND_TRIGGER = 5
    MANUAL = 6
    INTELLIGENT = 7


class FindNextFileStatus(IntEnum):
    SUCCESS = 1000
    NO_FIND = 1001
    FINDING = 1002
    NO_MORE_FILE = 1003
    EXCEPTION = 1004


@dataclass(frozen=True)
class DeviceInfo:
    """Parsed device information."""
    serial_number: str
    start_channel: int
    num_channels: int
    start_dchannel: int
    num_dchannels: int


@dataclass(frozen=True)
class LoginResult:
    """Result of a login operation."""
    user_id: int
    device_info: DeviceInfo


@dataclass(frozen=True)
class FindData:
    """Parsed recording file entry."""
    filename: str
    size: int
    start: datetime.datetime
    stop: datetime.datetime


@dataclass(frozen=True)
class FindNextFileResult:
    """Result of a find next file operation."""
    status: int
    data: Optional[FindData] = None


class LoginError(HikvisionSdkError):
    pass


class LogoutError(HikvisionSdkError):
    pass


class SearchError(HikvisionSdkError):
    pass


class PlaybackError(HikvisionSdkError):
    pass


def make_login_result_callback(callback: Callable[..., None]) -> Any:
    return sdk.fLoginResultCallBack(callback)


def make_playback_es_callback(callback: Callable[..., None]) -> Any:
    return sdk.fPlayESCallBack(callback)


def get_last_error() -> int:
    return int(sdk.NET_DVR_GetLastError())


_sdk_lock = threading.Lock()
_sdk_refcount = 0
_sdk_connect_timeout_ms: Optional[int] = None
_sdk_recv_timeout_ms: Optional[int] = None


def init(
    connect_timeout_ms: int = DEFAULT_CONNECT_TIMEOUT_MS,
    recv_timeout_ms: int = DEFAULT_RECV_TIMEOUT_MS,
) -> None:
    """Initialize the Hikvision SDK using the package refcounted lifecycle.
    
    This function initializes the Hikvision SDK with the specified connection
    and receive timeouts. It uses a reference counting mechanism to ensure
    that the SDK is only initialized once and cleaned up when no longer needed.

    If the SDK is already initialized with different timeout values, a warning
    is logged and the new values are ignored.

    Args:
        connect_timeout_ms: The connection timeout in milliseconds to set for the SDK.
        recv_timeout_ms: The receive timeout in milliseconds to set for the SDK.

    Raises:
        HikvisionSdkError: If the SDK initialization or configuration fails.
    """
    global _sdk_refcount
    global _sdk_connect_timeout_ms
    global _sdk_recv_timeout_ms

    with _sdk_lock:
        if _sdk_refcount == 0:
            if not sdk.NET_DVR_Init():
                raise HikvisionSdkError("NET_DVR_Init", sdk.NET_DVR_GetLastError())

            sdk.NET_DVR_SetConnectTime(connect_timeout_ms, 3)
            sdk.NET_DVR_SetRecvTimeOut(recv_timeout_ms)
            _sdk_connect_timeout_ms = int(connect_timeout_ms)
            _sdk_recv_timeout_ms = int(recv_timeout_ms)
        elif (
            _sdk_connect_timeout_ms is not None
            and _sdk_recv_timeout_ms is not None
            and (
                int(connect_timeout_ms) != _sdk_connect_timeout_ms
                or int(recv_timeout_ms) != _sdk_recv_timeout_ms
            )
        ):
            LOG.warning(
                "SDK already initialized with connect_timeout_ms=%s recv_timeout_ms=%s; ignoring new values connect_timeout_ms=%s recv_timeout_ms=%s",
                _sdk_connect_timeout_ms,
                _sdk_recv_timeout_ms,
                int(connect_timeout_ms),
                int(recv_timeout_ms),
            )

        _sdk_refcount += 1


def cleanup() -> None:
    """Release one package-managed Hikvision SDK lifecycle reference.
    
    This function decrements the SDK reference count and calls NET_DVR_Cleanup
    when the count reaches zero. It ensures that the SDK is properly cleaned up
    when no longer needed.
    
    Raises:
        HikvisionSdkError: If the SDK cleanup fails.
    """
    global _sdk_refcount
    global _sdk_connect_timeout_ms
    global _sdk_recv_timeout_ms

    with _sdk_lock:
        if _sdk_refcount <= 0:
            return

        _sdk_refcount -= 1
        if _sdk_refcount == 0:
            if not sdk.NET_DVR_Cleanup():
                raise HikvisionSdkError("NET_DVR_Cleanup", sdk.NET_DVR_GetLastError())
            _sdk_connect_timeout_ms = None
            _sdk_recv_timeout_ms = None


def login(
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        login_result_callback: Optional[Any] = None,
) -> LoginResult:
    """Log in synchronously and return the user id plus mid-level device info.

    Args:
        host: The IP address or hostname of the device.
        port: The port number to connect to.
        username: The username for authentication.
        password: The password for authentication.
        login_result_callback: Optional callback for login result.

    Returns:
        A LoginResult object containing the user id and DeviceInfo object.

    Raises:
        LoginError: If the login fails.
    """
    login_info = sdk.NET_DVR_USER_LOGIN_INFO()
    device_info = sdk.NET_DVR_DEVICEINFO_V40()

    login_info.sDeviceAddress = host.encode("ascii")
    login_info.byUseTransport = 0
    login_info.wPort = int(port)
    login_info.sUserName = username.encode("ascii")
    login_info.sPassword = password.encode("ascii")
    login_info.cbLoginResult = login_result_callback or make_login_result_callback(_noop_login_result)
    login_info.pUser = None
    login_info.bUseAsynLogin = 0
    login_info.byProxyType = 0
    login_info.byUseUTCTime = 0
    login_info.byLoginMode = 0
    login_info.byHttps = 0
    login_info.iProxyID = 0
    login_info.byVerifyMode = 0
    login_info.byRes3 = (sdk.BYTE * 119)(*([0] * 119))

    user_id = sdk.NET_DVR_Login_V40(ctypes.byref(login_info), ctypes.byref(device_info))
    if user_id == -1:
        raise LoginError("NET_DVR_Login_V40", get_last_error())

    device_v30 = device_info.struDeviceV30
    raw_serial = bytes(device_v30.sSerialNumber).split(b"\x00", 1)[0]

    return LoginResult(
        user_id=int(user_id),
        device_info=DeviceInfo(
            serial_number=raw_serial.decode("ascii", errors="ignore"),
            start_channel=int(device_v30.byStartChan),
            num_channels=int(device_v30.byChanNum),
            start_dchannel=int(device_v30.byStartDChan),
            num_dchannels=int(device_v30.byIPChanNum),
        ),
    )


def logout(user_id: int) -> None:
    """Log out a previously authenticated SDK session.

    Args:
        user_id: The user ID of the session to log out.

    Raises:
        LogoutError: If the logout fails.
    """
    if not sdk.NET_DVR_Logout(int(user_id)):
        raise LogoutError("NET_DVR_Logout", get_last_error())


def find_file(
        user_id: int,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
        *,
        file_type: int,
) -> int:
    """Start a recording search and return the SDK find handle.

    Args:
        user_id: The user ID of the session.
        channel: The channel number to search.
        start: The start time of the search range.
        stop: The stop time of the search range.
        file_type: The type of recording file to search for.

    Returns:
        The SDK find handle.

    Raises:
        SearchError: If the search fails.
    """
    start_t = sdk.NET_DVR_TIME.from_datetime(start)
    stop_t = sdk.NET_DVR_TIME.from_datetime(stop)
    find_handle = sdk.NET_DVR_FindFile(
        int(user_id),
        int(channel),
        int(file_type),
        ctypes.byref(start_t),
        ctypes.byref(stop_t),
    )
    if find_handle == -1:
        raise SearchError("NET_DVR_FindFile", get_last_error())
    return int(find_handle)


def find_next_file(find_handle: int) -> FindNextFileResult:
    """Poll a recording search handle and return its current status plus any file entry.

    Args:
        find_handle: The SDK find handle to poll.

    Returns:
        A FindNextFileResult object containing the current status and any file entry.

    Raises:
        SearchError: If the polling fails.
    """
    find_data = sdk.NET_DVR_FIND_DATA()
    status = int(sdk.NET_DVR_FindNextFile(int(find_handle), ctypes.byref(find_data)))
    if status == -1:
        raise SearchError("NET_DVR_FindNextFile", get_last_error())

    if status != FindNextFileStatus.SUCCESS:
        return FindNextFileResult(status=status)

    raw_name = bytes(find_data.sFileName).split(b"\x00", 1)[0]
    return FindNextFileResult(
        status=status,
        data=FindData(
            filename=raw_name.decode("ascii", errors="ignore"),
            size=int(find_data.dwFileSize),
            start=find_data.struStartTime.as_datetime(),
            stop=find_data.struStopTime.as_datetime(),
        ),
    )


def find_close(find_handle: int) -> None:
    """Close a recording search handle."""
    if not sdk.NET_DVR_FindClose(int(find_handle)):
        raise SearchError("NET_DVR_FindClose", get_last_error())


def open_playback_by_time(
        user_id: int,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
        *,
        hwnd: int = 0,
) -> int:
    """Open a playback session by time range and return the playback handle."""
    handle = sdk.NET_DVR_PlayBackByTime(
        int(user_id),
        int(channel),
        sdk.NET_DVR_TIME.from_datetime(start),
        sdk.NET_DVR_TIME.from_datetime(stop),
        int(hwnd),
    )
    if handle == -1:
        raise PlaybackError("NET_DVR_PlayBackByTime", get_last_error())
    return int(handle)


def set_playback_es_callback(
        play_handle: int,
        callback: Any,
        user: Optional[int] = None,
) -> None:
    """Register the ES playback callback for a playback handle."""
    if not sdk.NET_DVR_SetPlayBackESCallBack(int(play_handle), callback, user):
        raise PlaybackError("NET_DVR_SetPlayBackESCallBack", get_last_error())


def playback_set_transport_type(
        play_handle: int,
        transport_type: int,
) -> None:
    """Configure the transport type for an open playback handle."""
    trans_type = (sdk.BYTE * 4)(int(transport_type))
    if not sdk.NET_DVR_PlayBackControl_V40(
        int(play_handle),
        sdk.PlayBackControl.NET_DVR_SET_TRANS_TYPE,
        ctypes.byref(trans_type),
        4,
        None,
        0,
    ):
        raise PlaybackError("NET_DVR_PlayBackControl_V40(SET_TRANS_TYPE)", get_last_error())


def playback_start(play_handle: int) -> None:
    """Start an open playback handle."""
    if not sdk.NET_DVR_PlayBackControl_V40(
        int(play_handle),
        sdk.PlayBackControl.NET_DVR_PLAYSTART,
        None,
        0,
        None,
        0,
    ):
        raise PlaybackError("NET_DVR_PlayBackControl_V40(PLAYSTART)", get_last_error())


def playback_get_position_percent(play_handle: int) -> int:
    """Return the current playback progress as an integer percent."""
    pos = sdk.DWORD()
    if not sdk.NET_DVR_PlayBackControl_V40(
        int(play_handle),
        sdk.PlayBackControl.NET_DVR_PLAYGETPOS,
        None,
        0,
        ctypes.byref(pos),
        ctypes.sizeof(pos),
    ):
        raise PlaybackError("NET_DVR_PlayBackControl_V40(PLAYGETPOS)", get_last_error())
    return int(pos.value)


def playback_seek(play_handle: int, timestamp: datetime.datetime) -> None:
    """Seek playback to an absolute timestamp."""
    ts_struct = sdk.NET_DVR_TIME.from_datetime(timestamp)
    if not sdk.NET_DVR_PlayBackControl_V40(
        int(play_handle),
        sdk.PlayBackControl.NET_DVR_PLAYSETTIME,
        ctypes.byref(ts_struct),
        ctypes.sizeof(ts_struct),
        None,
        0,
    ):
        raise PlaybackError("NET_DVR_PlayBackControl_V40(PLAYSETTIME)", get_last_error())


def stop_playback(play_handle: int) -> None:
    """Stop and release an open playback handle."""
    if not sdk.NET_DVR_StopPlayBack(int(play_handle)):
        raise PlaybackError("NET_DVR_StopPlayBack", get_last_error())


def _noop_login_result(_lUserID, _dwResult, _lpDeviceInfo, _pUser):
    return None