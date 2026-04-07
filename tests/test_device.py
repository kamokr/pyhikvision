import ctypes
import datetime
import importlib
import sys

import pytest


class DummyLib:
    def __getattr__(self, _name):
        def _fn(*_args, **_kwargs):
            return 0

        return _fn


def import_fresh_device(monkeypatch, sdk_dir):
    sdk_dir.mkdir()
    monkeypatch.setenv("HIKVISION_SDK_PATH", str(sdk_dir))
    if sys.platform.startswith("win"):
        (sdk_dir / "HCNetSDK.dll").write_bytes(b"")
    else:
        (sdk_dir / "libhcnetsdk.so").write_bytes(b"")

    monkeypatch.setattr(ctypes, "CDLL", lambda _path: DummyLib())

    for module_name in ("hikvision", "hikvision.device", "hikvision.sdk"):
        sys.modules.pop(module_name, None)

    return importlib.import_module("hikvision.device")


def test_connect_disconnect_success(monkeypatch, tmp_path):
    device_mod = import_fresh_device(monkeypatch, tmp_path / "sdk")

    monkeypatch.setattr(device_mod, "_init_sdk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(device_mod, "_cleanup_sdk", lambda *_args, **_kwargs: None)

    def fake_login(_login_info_ptr, device_info_ptr):
        device_info = ctypes.cast(device_info_ptr, device_mod.sdk.LPNET_DVR_DEVICEINFO_V40).contents
        device_info.struDeviceV30.byStartChan = 1
        device_info.struDeviceV30.byChanNum = 4
        device_info.struDeviceV30.byStartDChan = 33
        device_info.struDeviceV30.byIPChanNum = 8
        ctypes.memmove(device_info.struDeviceV30.sSerialNumber, b"SERIAL123", len(b"SERIAL123"))
        return 7

    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Login_V40", fake_login)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Logout", lambda _user_id: 1)

    device = device_mod.HikvisionDevice("127.0.0.1", 8000, "admin", "password")
    device.connect()

    assert device.is_connected is True
    assert device.device_info.serial_number.startswith("SERIAL123")
    assert device.device_info.start_channel == 1
    assert device.device_info.num_channels == 4

    device.disconnect()
    assert device.is_connected is False


def test_search_recordings_returns_results(monkeypatch, tmp_path):
    device_mod = import_fresh_device(monkeypatch, tmp_path / "sdk")

    monkeypatch.setattr(device_mod, "_init_sdk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(device_mod, "_cleanup_sdk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Login_V40", lambda *_args: 9)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Logout", lambda _user_id: 1)

    statuses = iter([1002, 1000, 1003])
    calls = {"closed": None}

    def fake_find_next(_find_handle, find_data_ptr):
        status = next(statuses)
        if status == 1000:
            fd = ctypes.cast(find_data_ptr, device_mod.sdk.LPNET_DVR_FIND_DATA).contents
            fd.sFileName = b"ch01-record.ts"
            fd.dwFileSize = 12345
            fd.struStartTime = device_mod.sdk.NET_DVR_TIME.from_datetime(datetime.datetime(2024, 1, 1, 10, 0, 0))
            fd.struStopTime = device_mod.sdk.NET_DVR_TIME.from_datetime(datetime.datetime(2024, 1, 1, 10, 0, 10))
        return status

    monkeypatch.setattr(device_mod.sdk, "NET_DVR_FindFile", lambda *_args: 42)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_FindNextFile", fake_find_next)
    monkeypatch.setattr(
        device_mod.sdk,
        "NET_DVR_FindClose",
        lambda handle: calls.update({"closed": handle}) or 1,
    )

    device = device_mod.HikvisionDevice("127.0.0.1", 8000, "admin", "password")
    device.connect()

    records = device.search_recordings(
        channel=1,
        start=datetime.datetime(2024, 1, 1, 10, 0, 0),
        stop=datetime.datetime(2024, 1, 1, 10, 5, 0),
    )

    assert len(records) == 1
    assert records[0].filename == "ch01-record.ts"
    assert records[0].size == 12345
    assert calls["closed"] == 42


def test_playback_stream_receives_packets(monkeypatch, tmp_path):
    device_mod = import_fresh_device(monkeypatch, tmp_path / "sdk")

    monkeypatch.setattr(device_mod, "_init_sdk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(device_mod, "_cleanup_sdk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Login_V40", lambda *_args: 11)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Logout", lambda _user_id: 1)

    callback_holder = {}

    monkeypatch.setattr(device_mod.sdk, "NET_DVR_PlayBackByTime", lambda *_args: 88)
    monkeypatch.setattr(
        device_mod.sdk,
        "NET_DVR_SetPlayBackESCallBack",
        lambda _handle, cb, _user: callback_holder.update({"cb": cb}) or 1,
    )
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_PlayBackControl_V40", lambda *_args: 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_StopPlayBack", lambda _handle: 1)

    device = device_mod.HikvisionDevice("127.0.0.1", 8000, "admin", "password")
    device.connect()

    stream = device.open_playback(
        channel=1,
        start=datetime.datetime(2024, 1, 1, 10, 0, 0),
        stop=datetime.datetime(2024, 1, 1, 10, 5, 0),
    )
    stream.play(device_mod.PlaybackMode.STEP)

    raw = (device_mod.sdk.BYTE * 4)(1, 2, 3, 4)
    pkt = device_mod.sdk.NET_DVR_PACKET_INFO_EX()
    pkt.dwPacketType = 1
    pkt.dwPacketSize = 4
    pkt.pPacketBuffer = ctypes.cast(raw, ctypes.POINTER(device_mod.sdk.BYTE))
    pkt.dwYear = 2024
    pkt.dwMonth = 1
    pkt.dwDay = 1
    pkt.dwHour = 10
    pkt.dwMinute = 0
    pkt.dwSecond = 0
    pkt.dwMillisecond = 100

    callback_holder["cb"](88, ctypes.pointer(pkt), None)

    packet = stream.next_packet(timeout=0.1)
    assert packet is not None
    assert packet.packet_type == 1
    assert packet.data == b"\x01\x02\x03\x04"
    assert packet.packet_type_name == "VIDEO_I_FRAME"

    stream.close()


def test_playback_packet_type_name_from_value(monkeypatch, tmp_path):
    device_mod = import_fresh_device(monkeypatch, tmp_path / "sdk")

    assert device_mod.PlaybackPacketType.name_from_value(0) == "FILE_HEADER"
    assert device_mod.PlaybackPacketType.name_from_value(10) == "AUDIO"
    assert device_mod.PlaybackPacketType.name_from_value(999) == "UNKNOWN(999)"


def test_playback_stream_callback_in_stream_mode(monkeypatch, tmp_path):
    device_mod = import_fresh_device(monkeypatch, tmp_path / "sdk")

    monkeypatch.setattr(device_mod, "_init_sdk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(device_mod, "_cleanup_sdk", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Login_V40", lambda *_args: 11)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Logout", lambda _user_id: 1)

    callback_holder = {}

    monkeypatch.setattr(device_mod.sdk, "NET_DVR_PlayBackByTime", lambda *_args: 88)
    monkeypatch.setattr(
        device_mod.sdk,
        "NET_DVR_SetPlayBackESCallBack",
        lambda _handle, cb, _user: callback_holder.update({"cb": cb}) or 1,
    )
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_PlayBackControl_V40", lambda *_args: 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_StopPlayBack", lambda _handle: 1)

    received = []

    device = device_mod.HikvisionDevice("127.0.0.1", 8000, "admin", "password")
    device.connect()

    stream = device.open_playback(
        channel=1,
        start=datetime.datetime(2024, 1, 1, 10, 0, 0),
        stop=datetime.datetime(2024, 1, 1, 10, 5, 0),
    )
    stream.set_packet_callback(lambda pkt: received.append(pkt))
    stream.play(device_mod.PlaybackMode.STREAM)

    raw = (device_mod.sdk.BYTE * 4)(1, 2, 3, 4)
    pkt = device_mod.sdk.NET_DVR_PACKET_INFO_EX()
    pkt.dwPacketType = 1
    pkt.dwPacketSize = 4
    pkt.pPacketBuffer = ctypes.cast(raw, ctypes.POINTER(device_mod.sdk.BYTE))
    pkt.dwYear = 2024
    pkt.dwMonth = 1
    pkt.dwDay = 1
    pkt.dwHour = 10
    pkt.dwMinute = 0
    pkt.dwSecond = 0
    pkt.dwMillisecond = 100

    callback_holder["cb"](88, ctypes.pointer(pkt), None)

    assert len(received) == 1
    assert received[0].packet_type_name == "VIDEO_I_FRAME"

    with pytest.raises(device_mod.HikvisionPlaybackError):
        stream.next_packet(timeout=0.1)

    stream.stop()


def test_public_initialize_cleanup_and_state(monkeypatch, tmp_path):
    device_mod = import_fresh_device(monkeypatch, tmp_path / "sdk")

    calls = {"init": 0, "set_connect": [], "set_recv": [], "cleanup": 0}

    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Init", lambda: calls.update({"init": calls["init"] + 1}) or 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_SetConnectTime", lambda timeout_ms, retries: calls["set_connect"].append((timeout_ms, retries)) or 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_SetRecvTimeOut", lambda timeout_ms: calls["set_recv"].append(timeout_ms) or 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Cleanup", lambda: calls.update({"cleanup": calls["cleanup"] + 1}) or 1)

    assert device_mod.is_sdk_initialized() is False

    device_mod.initialize_sdk(connect_timeout_ms=1234, recv_timeout_ms=5678)
    assert device_mod.is_sdk_initialized() is True
    assert calls["init"] == 1
    assert calls["set_connect"] == [(1234, 3)]
    assert calls["set_recv"] == [5678]

    device_mod.cleanup_sdk()
    assert device_mod.is_sdk_initialized() is False
    assert calls["cleanup"] == 1


def test_eager_initialize_makes_connect_skip_sdk_init(monkeypatch, tmp_path):
    device_mod = import_fresh_device(monkeypatch, tmp_path / "sdk")

    calls = {"init": 0, "cleanup": 0}

    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Init", lambda: calls.update({"init": calls["init"] + 1}) or 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_SetConnectTime", lambda *_args: 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_SetRecvTimeOut", lambda *_args: 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Cleanup", lambda: calls.update({"cleanup": calls["cleanup"] + 1}) or 1)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Login_V40", lambda *_args: 17)
    monkeypatch.setattr(device_mod.sdk, "NET_DVR_Logout", lambda _user_id: 1)

    device_mod.initialize_sdk()
    assert calls["init"] == 1

    device = device_mod.HikvisionDevice("127.0.0.1", 8000, "admin", "password")
    device.connect()
    assert calls["init"] == 1

    device.disconnect()
    assert calls["cleanup"] == 0

    device_mod.cleanup_sdk()
    assert calls["cleanup"] == 1
