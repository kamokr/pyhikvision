import ctypes
import datetime
import threading
import time

from hikvision import playback_stream as playback_mod


def _make_packet_ptr(packet_type: int = 3):
    raw = (ctypes.c_ubyte * 4)(1, 2, 3, 4)
    packet = playback_mod.sdk.NET_DVR_PACKET_INFO_EX()
    packet.dwYear = 2024
    packet.dwMonth = 1
    packet.dwDay = 1
    packet.dwHour = 10
    packet.dwMinute = 0
    packet.dwSecond = 0
    packet.dwMillisecond = 1
    packet.dwPacketType = packet_type
    packet.dwPacketSize = 4
    packet.pPacketBuffer = ctypes.cast(raw, ctypes.POINTER(playback_mod.sdk.BYTE))
    packet.wWidth = 1920
    packet.wHeight = 1080
    packet.dwFrameNum = 1
    return ctypes.pointer(packet), raw


def _make_stream(queue_size: int = 1) -> playback_mod.PlaybackStream:
    return playback_mod.PlaybackStream(
        user_id=1,
        channel=1,
        start=datetime.datetime(2024, 1, 1, 10, 0, 0),
        stop=datetime.datetime(2024, 1, 1, 10, 1, 0),
        packet_queue_size=queue_size,
    )


def test_close_unblocks_step_callback_waiting_on_full_queue(monkeypatch):
    stream = _make_stream(queue_size=1)
    stream._play_handle = 88
    stream._started = True
    stream._mode = playback_mod.PlaybackMode.STEP

    # Fill queue to force callback queue.put() to block.
    stream._queue.put(
        playback_mod.PlaybackPacket(
            packet_type=int(playback_mod.PlaybackPacketType.VIDEO_P_FRAME),
            timestamp=1,
            date_time=datetime.datetime(2024, 1, 1, 10, 0, 0),
            data=b"old",
            width=1920,
            height=1080,
            frame_num=1,
        )
    )

    stopped = []
    monkeypatch.setattr(playback_mod.net_dvr, "stop_playback", lambda handle: stopped.append(handle))

    packet_ptr, _raw = _make_packet_ptr()

    worker = threading.Thread(target=stream._play_es_cb, args=(88, packet_ptr, None), daemon=True)
    worker.start()

    deadline = time.time() + 1.0
    while time.time() < deadline and not worker.is_alive():
        time.sleep(0.01)

    assert worker.is_alive(), "callback did not block on full queue as expected"

    stream.close()

    worker.join(timeout=1.0)
    assert not worker.is_alive(), "close() should unblock callback waiting on queue.put()"
    assert stopped == [88]
