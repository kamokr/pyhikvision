import datetime
import importlib
import os

import pytest


pytestmark = pytest.mark.integration


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not set")
    return value


def test_device_login_search_and_playback_smoke():
    device_mod = importlib.import_module("hikvision.device")
    HikvisionDevice = device_mod.HikvisionDevice

    host = _require_env("HIKVISION_TEST_HOST")
    port = int(os.getenv("HIKVISION_TEST_PORT", "8000"))
    username = _require_env("HIKVISION_TEST_USERNAME")
    password = _require_env("HIKVISION_TEST_PASSWORD")
    channel = int(os.getenv("HIKVISION_TEST_CHANNEL", "33")) # Default to 33 which is the first IP channel on many Hikvision devices
    search_window_minutes = int(os.getenv("HIKVISION_TEST_SEARCH_WINDOW_MINUTES", "10"))

    now = datetime.datetime.now()
    start = now - datetime.timedelta(minutes=search_window_minutes)

    with HikvisionDevice(host, port, username, password) as device:
        assert device.is_connected is True

        recordings = device.search_recordings(
            channel=channel,
            start=start,
            stop=now,
        )
        assert isinstance(recordings, list)

        if not recordings:
            pytest.skip("No recordings found in the selected time window")

        first = recordings[0]
        playback_start = first.start
        playback_stop = min(first.stop, first.start + datetime.timedelta(seconds=10))
        if playback_stop <= playback_start:
            pytest.skip("Recording has invalid or zero playback duration")

        stream = device.open_playback(channel=channel, start=playback_start, stop=playback_stop)
        try:
            stream.play(device_mod.PlaybackMode.STEP)
            packet = stream.next_packet(timeout=5.0)
            if packet is None:
                pytest.skip("Playback opened but no packet arrived within timeout")

            assert packet.packet_type in (
                device_mod.PlaybackPacketType.FILE_HEADER,
                device_mod.PlaybackPacketType.VIDEO_I_FRAME,
                device_mod.PlaybackPacketType.VIDEO_B_FRAME,
                device_mod.PlaybackPacketType.VIDEO_P_FRAME,
                device_mod.PlaybackPacketType.AUDIO,
                device_mod.PlaybackPacketType.DATA_PRIVATE,
            )
            assert isinstance(packet.data, bytes)
            assert len(packet.data) > 0
        finally:
            stream.close()

    assert device.is_connected is False
