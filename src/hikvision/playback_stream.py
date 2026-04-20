from __future__ import annotations

import contextlib
import ctypes
import datetime
import logging
import queue
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, Iterator, Optional

from . import sdk
from . import net_dvr


LOG = logging.getLogger(__name__)


class PlaybackMode(IntEnum):
    STREAM = 0
    STEP = 1


class TransportType(IntEnum):
    PS = 1
    TS = 2
    RTP = 3
    MP4 = 5


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


@dataclass(frozen=True)
class PlaybackPacket:
    packet_type: int
    timestamp: int
    date_time: datetime.datetime
    data: bytes
    width: int
    height: int
    frame_num: int

    @property
    def packet_type_name(self) -> str:
        return PlaybackPacketType.name_from_value(self.packet_type)


def local2ts(dt: datetime.datetime):
    return int(datetime.datetime.timestamp(dt)*1000)


def ts2local(ts: int):
    return datetime.datetime.fromtimestamp(ts/1000)


class PlaybackStream:
    def __init__(
        self,
        user_id: int,
        channel: int,
        start: datetime.datetime,
        stop: datetime.datetime,
        packet_queue_size: int = 150,
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
        self._closing = False
        self._closed = False
        self._cb = net_dvr.make_playback_es_callback(self._play_es_cb)

    @property
    def handle(self) -> int:
        if self._play_handle is None:
            raise net_dvr.PlaybackError("NET_DVR_PlayBackByTime", -1, "playback handle is not initialized")
        return self._play_handle

    def __enter__(self) -> "PlaybackStream":
        self.start(PlaybackMode.STREAM)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        if self._closed:
            raise net_dvr.PlaybackError("NET_DVR_PlayBackByTime", -1, "playback stream is closed")
        if self._play_handle is not None:
            return

        handle = net_dvr.open_playback_by_time(
            self._user_id,
            self._channel,
            self._start,
            self._stop,
        )

        self._play_handle = int(handle)

    def set_packet_callback(self, on_packet: Optional[Callable[[PlaybackPacket], None]]) -> None:
        self._packet_callback = on_packet

    def start(self, mode: PlaybackMode = PlaybackMode.STREAM) -> None:
        mode = PlaybackMode(mode)
        if self._closed:
            raise net_dvr.PlaybackError("NET_DVR_PlayBackByTime", -1, "playback stream is closed")

        self.open()
        self._mode = mode

        if self._started:
            return

        net_dvr.set_playback_es_callback(self.handle, self._cb)
        net_dvr.playback_set_transport_type(self.handle, TransportType.TS)
        net_dvr.playback_start(self.handle)

        self._started = True

    def play(self, mode: PlaybackMode = PlaybackMode.STREAM) -> None:
        """Convenience alias for start()."""

        self.start(mode)

    def _release_handle(self) -> None:
        if self._play_handle is None:
            return

        handle = self._play_handle
        was_step_mode = self._mode == PlaybackMode.STEP
        self._started = False
        self._mode = None
        self._play_handle = None

        if was_step_mode:
            # If the ES callback is blocked on queue.put() because the queue is full,
            # free one slot so shutdown can proceed.
            with contextlib.suppress(queue.Empty):
                self._queue.get_nowait()

        net_dvr.stop_playback(handle)

    def stop(self) -> None:
        if self._play_handle is None or not self._started:
            self._mode = None
            return
        self._release_handle()

    def close(self) -> None:
        if self._closed:
            return

        self._closing = True
        try:
            with contextlib.suppress(net_dvr.PlaybackError):
                self._release_handle()
        finally:
            self._closed = True
            self._closing = False
            self._started = False
            self._mode = None
            self._play_handle = None

    def get_position_percent(self) -> int:
        return net_dvr.playback_get_position_percent(self.handle)

    def seek(self, ts: datetime.datetime) -> None:
        net_dvr.playback_seek(self.handle, ts)

    def next_packet(self, timeout: Optional[float] = None, keyframes_only: bool = False) -> Optional[PlaybackPacket]:
        if self._mode != PlaybackMode.STEP:
            raise net_dvr.PlaybackError("next_packet", -1, "next_packet is only available in STEP mode")

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
        
        if self._closing:
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
            timestamp=local2ts(frame_dt),
            date_time=frame_dt,
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

        # In STEP mode we preserve packet order and do not drop frames.
        self._queue.put(packet)