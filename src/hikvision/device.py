from __future__ import annotations

import contextlib
import ctypes
import datetime
import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Set

from hikvision.constants import DEFAULT_CONNECT_TIMEOUT_MS, DEFAULT_RECV_TIMEOUT_MS
from hikvision.enums import RecordingFileType
from hikvision.errors import (
    HikvisionDeviceError,
    HikvisionSdkError,
)
from .net import dvr
from .playback_stream import PlaybackMode, PlaybackStream


LOG = logging.getLogger(__name__)


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
        self._login_cb = dvr.make_login_result_callback(self._on_login_result)

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
            raise dvr.LoginError("NET_DVR_Login_V40", -1, "not connected")
        return self._device_info

    def connect(self) -> None:
        if self._user_id is not None:
            return

        dvr.init(self._connect_timeout_ms, self._recv_timeout_ms)

        try:
            login_result = dvr.login(
                host=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                login_result_callback=self._login_cb,
            )
        except dvr.LoginError:
            with contextlib.suppress(HikvisionSdkError):
                dvr.cleanup()
            raise

        device_info = login_result.device_info
        serial_number = ctypes.cast(device_info.struDeviceV30.sSerialNumber, ctypes.c_char_p).value
        self._device_info = DeviceInfo(
            serial_number=(serial_number or b"").decode("ascii", errors="ignore"),
            start_channel=int(device_info.struDeviceV30.byStartChan),
            num_channels=int(device_info.struDeviceV30.byChanNum),
            start_dchannel=int(device_info.struDeviceV30.byStartDChan),
            num_dchannels=int(device_info.struDeviceV30.byIPChanNum),
        )
        self._user_id = login_result.user_id

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
            dvr.logout(user_id)
        finally:
            dvr.cleanup()

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
            raise dvr.SearchError("NET_DVR_FindFile", -1, "not connected")

        find_handle = dvr.find_file(
            self._user_id,
            int(channel),
            start,
            stop,
            file_type=int(file_type),
        )

        results: List[Recording] = []

        try:
            while True:
                next_result = dvr.find_next_file(find_handle)
                status = next_result.status

                if status == dvr.FindNextStatus.SUCCESS:
                    entry = next_result.entry
                    if entry is None:
                        raise dvr.SearchError("NET_DVR_FindNextFile", status, "missing file data")
                    results.append(
                        Recording(
                            filename=entry.filename,
                            size=entry.size,
                            start=entry.start,
                            stop=entry.stop,
                        )
                    )
                    continue

                if status in (dvr.FindNextStatus.NO_FIND, dvr.FindNextStatus.NO_MORE_FILE):
                    break

                if status == dvr.FindNextStatus.FINDING:
                    time.sleep(self._search_poll_interval_s)
                    continue

                if status == dvr.FindNextStatus.EXCEPTION:
                    raise dvr.SearchError("NET_DVR_FindNextFile", status, "device search exception")

                raise dvr.SearchError("NET_DVR_FindNextFile", status, "unexpected search status")
        finally:
            try:
                dvr.find_close(find_handle)
            except dvr.SearchError as exc:
                LOG.warning("NET_DVR_FindClose failed with code=%s", exc.error_code)

        return results

    def open_playback(
        self,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
    ) -> PlaybackStream:
        if self._user_id is None:
            raise dvr.PlaybackError("NET_DVR_PlayBackByTime", -1, "not connected")

        stream = PlaybackStream(
            user_id=self._user_id,
            channel=int(channel),
            start=start,
            stop=stop,
            packet_queue_size=self._packet_queue_size,
        )
        self._playbacks.add(stream)
        return stream

    def start_playback(
        self,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
        *,
        mode: PlaybackMode = PlaybackMode.STREAM,
    ) -> PlaybackStream:
        """Open and start playback in a single call."""

        stream = self.open_playback(channel=channel, start=start, stop=stop)
        stream.start(mode)
        return stream

    @staticmethod
    def _on_login_result(_lUserID, _dwResult, _lpDeviceInfo, _pUser):
        # Keeping a callback reference is required by ctypes API; no-op body.
        return None
