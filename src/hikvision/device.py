from __future__ import annotations

import contextlib
import ctypes
import datetime
import logging
import queue
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Iterator, List, Optional, Set

from . import errors as error_codes
from . import sdk


LOG = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT_MS = 10000
DEFAULT_RECV_TIMEOUT_MS = 10000


@dataclass(frozen=True)
class DeviceInfo:
    serial_number: str
    start_channel: int
    num_channels: int
    start_dchannel: int
    num_dchannels: int


@dataclass(frozen=True)
class Recording:
    filename: str
    size: int
    start: datetime.datetime
    stop: datetime.datetime


@dataclass(frozen=True)
class PlaybackPacket:
    packet_type: int
    timestamp: datetime.datetime
    data: bytes
    width: int
    height: int
    frame_num: int

    @property
    def packet_type_name(self) -> str:
        return PlaybackPacketType.name_from_value(self.packet_type)


class TransportType(IntEnum):
    PS = 1
    TS = 2
    RTP = 3
    MP4 = 5


class PlaybackMode(IntEnum):
    STREAM = 0
    STEP = 1


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


class PlaybackPacketType(IntEnum):
    FILE_HEADER = 0
    VIDEO_I_FRAME = 1
    VIDEO_B_FRAME = 2
    VIDEO_P_FRAME = 3
    AUDIO = 10
    DATA_PRIVATE = 11

    @classmethod
    def name_from_value(cls, value: int) -> str:
        try:
            return cls(int(value)).name
        except ValueError:
            return f"UNKNOWN({int(value)})"


class HikvisionDeviceError(Exception):
    def __init__(self, operation: str, error_code: int, message: Optional[str] = None):
        self.operation = operation
        self.error_code = int(error_code)
        details = message or _format_error(error_code)
        super().__init__(f"{operation} failed: {details} (code={self.error_code})")


class HikvisionConnectError(HikvisionDeviceError):
    pass


class HikvisionSearchError(HikvisionDeviceError):
    pass


class HikvisionPlaybackError(HikvisionDeviceError):
    pass


_sdk_lock = threading.Lock()
_sdk_refcount = 0
_sdk_connect_timeout_ms: Optional[int] = None
_sdk_recv_timeout_ms: Optional[int] = None


def _format_error(error_code: int) -> str:
    for name, value in vars(error_codes).items():
        if name.startswith("NET_DVR_") and isinstance(value, int) and value == int(error_code):
            return name
    return "NET_DVR_UNKNOWN_ERROR"


def _init_sdk(
        connect_timeout_ms: int = DEFAULT_CONNECT_TIMEOUT_MS,
        recv_timeout_ms: int = DEFAULT_RECV_TIMEOUT_MS) -> None:
    global _sdk_refcount
    global _sdk_connect_timeout_ms
    global _sdk_recv_timeout_ms

    with _sdk_lock:
        if _sdk_refcount == 0:
            if not sdk.NET_DVR_Init():
                raise HikvisionConnectError("NET_DVR_Init", sdk.NET_DVR_GetLastError())

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


def _cleanup_sdk() -> None:
    global _sdk_refcount
    global _sdk_connect_timeout_ms
    global _sdk_recv_timeout_ms

    with _sdk_lock:
        if _sdk_refcount <= 0:
            return

        _sdk_refcount -= 1
        if _sdk_refcount == 0:
            if not sdk.NET_DVR_Cleanup():
                raise HikvisionDeviceError("NET_DVR_Cleanup", sdk.NET_DVR_GetLastError())
            _sdk_connect_timeout_ms = None
            _sdk_recv_timeout_ms = None


def initialize_sdk(connect_timeout_ms: int = 10000, recv_timeout_ms: int = 10000) -> None:
    """Initialize HCNetSDK eagerly for faster subsequent device connects.

    This call is process-global and reference-counted. Call `cleanup_sdk()` when
    this eager initialization is no longer needed.
    """

    _init_sdk(connect_timeout_ms=int(connect_timeout_ms), recv_timeout_ms=int(recv_timeout_ms))


def cleanup_sdk() -> None:
    """Release one SDK initialization reference acquired by `initialize_sdk()`.

    Cleanup is process-global and reference-counted.
    """

    _cleanup_sdk()


def is_sdk_initialized() -> bool:
    """Return whether HCNetSDK is currently initialized in this process."""

    with _sdk_lock:
        return _sdk_refcount > 0


class PlaybackStream:
    def __init__(
        self,
        user_id: int,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
        packet_queue_size: int = 512,
    ):
        self._user_id = user_id
        self._channel = channel
        self._start = start
        self._stop = stop
        self._queue: queue.Queue[PlaybackPacket] = queue.Queue(maxsize=packet_queue_size)

        self._play_handle: Optional[int] = None
        self._started = False
        self._mode: Optional[PlaybackMode] = None
        self._packet_callback: Optional[Callable[[PlaybackPacket], None]] = None
        self._closed = False
        self._cb = sdk.fPlayESCallBack(self._play_es_cb)

    @property
    def handle(self) -> int:
        if self._play_handle is None:
            raise HikvisionPlaybackError("NET_DVR_PlayBackByTime", -1, "playback handle is not initialized")
        return self._play_handle

    def __enter__(self) -> "PlaybackStream":
        self.open()
        self.play(PlaybackMode.STREAM)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        if self._closed:
            raise HikvisionPlaybackError("NET_DVR_PlayBackByTime", -1, "playback stream is closed")
        if self._play_handle is not None:
            return

        handle = sdk.NET_DVR_PlayBackByTime(
            self._user_id,
            self._channel,
            sdk.NET_DVR_TIME.from_datetime(self._start),
            sdk.NET_DVR_TIME.from_datetime(self._stop),
            0,
        )
        if handle == -1:
            raise HikvisionPlaybackError("NET_DVR_PlayBackByTime", sdk.NET_DVR_GetLastError())

        self._play_handle = int(handle)

    def set_packet_callback(self, on_packet: Optional[Callable[[PlaybackPacket], None]]) -> None:
        self._packet_callback = on_packet

    def play(self, mode: PlaybackMode) -> None:
        mode = PlaybackMode(mode)
        if self._closed:
            raise HikvisionPlaybackError("NET_DVR_PlayBackByTime", -1, "playback stream is closed")

        self.open()
        self._mode = mode

        if self._started:
            return

        if not sdk.NET_DVR_SetPlayBackESCallBack(self.handle, self._cb, None):
            raise HikvisionPlaybackError("NET_DVR_SetPlayBackESCallBack", sdk.NET_DVR_GetLastError())

        trans_type = (sdk.BYTE * 4)(TransportType.TS)
        if not sdk.NET_DVR_PlayBackControl_V40(
            self.handle,
            sdk.PlayBackControl.NET_DVR_SET_TRANS_TYPE,
            ctypes.byref(trans_type),
            4,
            None,
            0,
        ):
            raise HikvisionPlaybackError("NET_DVR_PlayBackControl_V40(SET_TRANS_TYPE)", sdk.NET_DVR_GetLastError())

        if not sdk.NET_DVR_PlayBackControl_V40(
            self.handle,
            sdk.PlayBackControl.NET_DVR_PLAYSTART,
            None,
            0,
            None,
            0,
        ):
            raise HikvisionPlaybackError("NET_DVR_PlayBackControl_V40(PLAYSTART)", sdk.NET_DVR_GetLastError())

        self._started = True

    def start(self) -> None:
        # Backward-compatible alias.
        self.play(PlaybackMode.STREAM)

    def stop(self) -> None:
        self._mode = None
        if self._play_handle is None:
            return
        if not self._started:
            return

        self._started = False
        if not sdk.NET_DVR_StopPlayBack(self.handle):
            raise HikvisionPlaybackError("NET_DVR_StopPlayBack", sdk.NET_DVR_GetLastError())

    def close(self) -> None:
        if self._closed:
            return

        try:
            with contextlib.suppress(HikvisionPlaybackError):
                self.stop()
        finally:
            self._closed = True
            self._play_handle = None

    def get_position_percent(self) -> int:
        pos = sdk.DWORD()
        if not sdk.NET_DVR_PlayBackControl_V40(
            self.handle,
            sdk.PlayBackControl.NET_DVR_PLAYGETPOS,
            None,
            0,
            ctypes.byref(pos),
            ctypes.sizeof(pos),
        ):
            raise HikvisionPlaybackError("NET_DVR_PlayBackControl_V40(PLAYGETPOS)", sdk.NET_DVR_GetLastError())
        return int(pos.value)

    def seek(self, ts: datetime.datetime) -> None:
        ts_struct = sdk.NET_DVR_TIME.from_datetime(ts)
        if not sdk.NET_DVR_PlayBackControl_V40(
            self.handle,
            sdk.PlayBackControl.NET_DVR_PLAYSETTIME,
            ctypes.byref(ts_struct),
            ctypes.sizeof(ts_struct),
            None,
            0,
        ):
            raise HikvisionPlaybackError("NET_DVR_PlayBackControl_V40(PLAYSETTIME)", sdk.NET_DVR_GetLastError())

    def next_packet(self, timeout: Optional[float] = None, keyframes_only: bool = False) -> Optional[PlaybackPacket]:
        if self._mode != PlaybackMode.STEP:
            raise HikvisionPlaybackError("next_packet", -1, "next_packet is only available in STEP mode")

        deadline = None if timeout is None else time.time() + timeout

        while True:
            wait = 0.2
            if deadline is not None:
                wait = max(0.0, deadline - time.time())
                if wait == 0.0:
                    return None

            try:
                packet = self._queue.get(timeout=wait)
            except queue.Empty:
                if deadline is not None:
                    return None
                if not self._started and self._queue.empty():
                    return None
                continue

            if keyframes_only and packet.packet_type != int(PlaybackPacketType.VIDEO_I_FRAME):
                continue
            return packet

    def iter_packets(self, timeout: Optional[float] = None, keyframes_only: bool = False) -> Iterator[PlaybackPacket]:
        while True:
            packet = self.next_packet(timeout=timeout, keyframes_only=keyframes_only)
            if packet is None:
                return
            yield packet

    def _play_es_cb(self, lPlayHandle, packet_info, _user):
        if packet_info is None:
            return

        contents = packet_info.contents
        try:
            frame_dt = datetime.datetime(
                year=int(contents.dwYear),
                month=int(contents.dwMonth),
                day=int(contents.dwDay),
                hour=int(contents.dwHour),
                minute=int(contents.dwMinute),
                second=int(contents.dwSecond),
                microsecond=int(contents.dwMillisecond) * 1000,
            )
        except ValueError:
            frame_dt = datetime.datetime.fromtimestamp(0)

        if contents.dwPacketSize <= 0 or not contents.pPacketBuffer:
            return

        data_ptr = ctypes.cast(
            contents.pPacketBuffer,
            ctypes.POINTER(ctypes.c_ubyte * int(contents.dwPacketSize)),
        )
        packet = PlaybackPacket(
            packet_type=int(contents.dwPacketType),
            timestamp=frame_dt,
            data=bytes(data_ptr.contents),
            width=int(contents.wWidth),
            height=int(contents.wHeight),
            frame_num=int(contents.dwFrameNum),
        )

        if self._mode == PlaybackMode.STREAM:
            if callable(self._packet_callback):
                try:
                    self._packet_callback(packet)
                except Exception:
                    LOG.exception("packet callback failed")
            return

        if self._mode != PlaybackMode.STEP:
            return

        try:
            self._queue.put_nowait(packet)
        except queue.Full:
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(packet)


class HikvisionDevice:
    """High-level synchronous device client for login, search, and playback."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        connect_timeout_ms: int = DEFAULT_CONNECT_TIMEOUT_MS,
        recv_timeout_ms: int = DEFAULT_RECV_TIMEOUT_MS,
        search_poll_interval_s: float = 0.1,
        packet_queue_size: int = 512,
    ):
        self._host = host
        self._port = int(port)
        self._username = username
        self._password = password
        self._connect_timeout_ms = int(connect_timeout_ms)
        self._recv_timeout_ms = int(recv_timeout_ms)
        self._search_poll_interval_s = float(search_poll_interval_s)
        self._packet_queue_size = int(packet_queue_size)

        self._user_id: Optional[int] = None
        self._device_info: Optional[DeviceInfo] = None
        self._playbacks: Set[PlaybackStream] = set()
        self._login_cb = sdk.fLoginResultCallBack(self._on_login_result)

    def __enter__(self) -> "HikvisionDevice":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def is_connected(self) -> bool:
        return self._user_id is not None

    @property
    def device_info(self) -> DeviceInfo:
        if self._device_info is None:
            raise HikvisionConnectError("NET_DVR_Login_V40", -1, "not connected")
        return self._device_info

    def connect(self) -> None:
        if self._user_id is not None:
            return

        _init_sdk(self._connect_timeout_ms, self._recv_timeout_ms)

        login_info = sdk.NET_DVR_USER_LOGIN_INFO()
        device_info = sdk.NET_DVR_DEVICEINFO_V40()

        login_info.sDeviceAddress = self._host.encode("ascii")
        login_info.byUseTransport = 0
        login_info.wPort = self._port
        login_info.sUserName = self._username.encode("ascii")
        login_info.sPassword = self._password.encode("ascii")
        login_info.cbLoginResult = self._login_cb
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
            err = sdk.NET_DVR_GetLastError()
            with contextlib.suppress(HikvisionDeviceError):
                _cleanup_sdk()
            raise HikvisionConnectError("NET_DVR_Login_V40", err)

        serial_number = ctypes.cast(device_info.struDeviceV30.sSerialNumber, ctypes.c_char_p).value
        self._device_info = DeviceInfo(
            serial_number=(serial_number or b"").decode("ascii", errors="ignore"),
            start_channel=int(device_info.struDeviceV30.byStartChan),
            num_channels=int(device_info.struDeviceV30.byChanNum),
            start_dchannel=int(device_info.struDeviceV30.byStartDChan),
            num_dchannels=int(device_info.struDeviceV30.byIPChanNum),
        )
        self._user_id = int(user_id)

    def disconnect(self) -> None:
        if self._user_id is None:
            return

        for stream in list(self._playbacks):
            stream.close()
            self._playbacks.discard(stream)

        user_id = self._user_id
        self._user_id = None
        self._device_info = None

        try:
            if not sdk.NET_DVR_Logout(user_id):
                raise HikvisionConnectError("NET_DVR_Logout", sdk.NET_DVR_GetLastError())
        finally:
            _cleanup_sdk()

    def close(self) -> None:
        with contextlib.suppress(HikvisionDeviceError):
            self.disconnect()

    def search_recordings(
        self,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
        *,
        file_type: RecordingFileType = RecordingFileType.ALL,
    ) -> List[Recording]:
        if self._user_id is None:
            raise HikvisionSearchError("NET_DVR_FindFile", -1, "not connected")

        start_t = sdk.NET_DVR_TIME.from_datetime(start)
        stop_t = sdk.NET_DVR_TIME.from_datetime(stop)

        find_handle = sdk.NET_DVR_FindFile(
            self._user_id,
            int(channel),
            int(file_type),
            ctypes.byref(start_t),
            ctypes.byref(stop_t),
        )
        if find_handle == -1:
            raise HikvisionSearchError("NET_DVR_FindFile", sdk.NET_DVR_GetLastError())

        NET_DVR_FILE_SUCCESS = 1000
        NET_DVR_FILE_NOFIND = 1001
        NET_DVR_ISFINDING = 1002
        NET_DVR_NOMOREFILE = 1003
        NET_DVR_FILE_EXCEPTION = 1004

        results: List[Recording] = []
        find_data = sdk.NET_DVR_FIND_DATA()

        try:
            while True:
                status = sdk.NET_DVR_FindNextFile(find_handle, ctypes.byref(find_data))
                if status == -1:
                    raise HikvisionSearchError("NET_DVR_FindNextFile", sdk.NET_DVR_GetLastError())

                if status == NET_DVR_FILE_SUCCESS:
                    raw_name = bytes(find_data.sFileName).split(b"\x00", 1)[0]
                    results.append(
                        Recording(
                            filename=raw_name.decode("ascii", errors="ignore"),
                            size=int(find_data.dwFileSize),
                            start=find_data.struStartTime.as_datetime(),
                            stop=find_data.struStopTime.as_datetime(),
                        )
                    )
                    continue

                if status in (NET_DVR_FILE_NOFIND, NET_DVR_NOMOREFILE):
                    break

                if status == NET_DVR_ISFINDING:
                    time.sleep(self._search_poll_interval_s)
                    continue

                if status == NET_DVR_FILE_EXCEPTION:
                    raise HikvisionSearchError("NET_DVR_FindNextFile", status, "device search exception")

                raise HikvisionSearchError("NET_DVR_FindNextFile", status, "unexpected search status")
        finally:
            if not sdk.NET_DVR_FindClose(find_handle):
                LOG.warning("NET_DVR_FindClose failed with code=%s", sdk.NET_DVR_GetLastError())

        return results

    def open_playback(
        self,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
    ) -> PlaybackStream:
        if self._user_id is None:
            raise HikvisionPlaybackError("NET_DVR_PlayBackByTime", -1, "not connected")

        stream = PlaybackStream(
            user_id=self._user_id,
            channel=int(channel),
            start=start,
            stop=stop,
            packet_queue_size=self._packet_queue_size,
        )
        stream.open()
        self._playbacks.add(stream)
        return stream

    @staticmethod
    def _on_login_result(_lUserID, _dwResult, _lpDeviceInfo, _pUser):
        # Keeping a callback reference is required by ctypes API; no-op body.
        return None
