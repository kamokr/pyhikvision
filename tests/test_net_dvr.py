import ctypes
import datetime
import importlib

import pytest


dvr_mod = importlib.import_module("hikvision.net.dvr")


@pytest.fixture(autouse=True)
def reset_sdk_state():
    dvr_mod._sdk_refcount = 0
    dvr_mod._sdk_connect_timeout_ms = None
    dvr_mod._sdk_recv_timeout_ms = None
    yield
    dvr_mod._sdk_refcount = 0
    dvr_mod._sdk_connect_timeout_ms = None
    dvr_mod._sdk_recv_timeout_ms = None


def test_init_cleanup_uses_refcounted_lifecycle(monkeypatch):
    calls = {"init": 0, "set_connect": [], "set_recv": [], "cleanup": 0}

    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_Init", lambda: calls.update({"init": calls["init"] + 1}) or 1)
    monkeypatch.setattr(
        dvr_mod.sdk,
        "NET_DVR_SetConnectTime",
        lambda timeout_ms, retries: calls["set_connect"].append((timeout_ms, retries)) or 1,
    )
    monkeypatch.setattr(
        dvr_mod.sdk,
        "NET_DVR_SetRecvTimeOut",
        lambda timeout_ms: calls["set_recv"].append(timeout_ms) or 1,
    )
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_Cleanup", lambda: calls.update({"cleanup": calls["cleanup"] + 1}) or 1)

    dvr_mod.init(connect_timeout_ms=1234, recv_timeout_ms=5678)
    dvr_mod.init(connect_timeout_ms=1234, recv_timeout_ms=5678)

    assert calls["init"] == 1
    assert calls["set_connect"] == [(1234, 3)]
    assert calls["set_recv"] == [5678]
    assert dvr_mod._sdk_refcount == 2

    dvr_mod.cleanup()
    assert calls["cleanup"] == 0
    assert dvr_mod._sdk_refcount == 1

    dvr_mod.cleanup()
    assert calls["cleanup"] == 1
    assert dvr_mod._sdk_refcount == 0
    assert dvr_mod._sdk_connect_timeout_ms is None
    assert dvr_mod._sdk_recv_timeout_ms is None


def test_login_logout_wraps_sdk_structures(monkeypatch):
    callbacks = {}
    recorded = {"logout": None}

    def fake_login(login_info_ptr, device_info_ptr):
        login_info = ctypes.cast(login_info_ptr, dvr_mod.sdk.LPNET_DVR_USER_LOGIN_INFO).contents
        device_info = ctypes.cast(device_info_ptr, dvr_mod.sdk.LPNET_DVR_DEVICEINFO_V40).contents

        assert login_info.sDeviceAddress.startswith(b"127.0.0.1")
        assert login_info.wPort == 8000
        assert login_info.sUserName.startswith(b"admin")
        assert login_info.sPassword.startswith(b"password")
        assert login_info.bUseAsynLogin == 0
        callbacks["login"] = login_info.cbLoginResult

        device_info.struDeviceV30.byStartChan = 1
        device_info.struDeviceV30.byChanNum = 4
        ctypes.memmove(device_info.struDeviceV30.sSerialNumber, b"SERIAL123", len(b"SERIAL123"))
        return 7

    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_Login_V40", fake_login)
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_Logout", lambda user_id: recorded.update({"logout": user_id}) or 1)

    result = dvr_mod.login(host="127.0.0.1", port=8000, username="admin", password="password")

    assert result.user_id == 7
    assert result.device_info.struDeviceV30.byStartChan == 1
    assert result.device_info.struDeviceV30.byChanNum == 4
    assert bytes(result.device_info.struDeviceV30.sSerialNumber).split(b"\x00", 1)[0] == b"SERIAL123"
    assert callbacks["login"] is not None

    dvr_mod.logout(result.user_id)
    assert recorded["logout"] == 7


def test_login_raises_sdk_error_on_failure(monkeypatch):
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_Login_V40", lambda *_args: -1)
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_GetLastError", lambda: 23)

    with pytest.raises(dvr_mod.HikvisionSdkError, match="NET_DVR_Login_V40") as exc_info:
        dvr_mod.login(host="127.0.0.1", port=8000, username="admin", password="password")

    assert exc_info.value.error_code == 23


def test_find_file_find_next_and_find_close_use_mid_level_results(monkeypatch):
    calls = {"find_file": None, "find_close": []}
    responses = iter(
        [
            dvr_mod.FindNextStatus.FINDING,
            dvr_mod.FindNextStatus.SUCCESS,
            dvr_mod.FindNextStatus.NO_MORE_FILE,
        ]
    )

    def fake_find_file(user_id, channel, file_type, start_ptr, stop_ptr):
        start = ctypes.cast(start_ptr, dvr_mod.sdk.LPNET_DVR_TIME).contents
        stop = ctypes.cast(stop_ptr, dvr_mod.sdk.LPNET_DVR_TIME).contents
        calls["find_file"] = {
            "user_id": user_id,
            "channel": channel,
            "file_type": file_type,
            "start": start.as_datetime(),
            "stop": stop.as_datetime(),
        }
        return 42

    def fake_find_next(handle, find_data_ptr):
        status = next(responses)
        if status == dvr_mod.FindNextStatus.SUCCESS:
            find_data = ctypes.cast(find_data_ptr, dvr_mod.sdk.LPNET_DVR_FIND_DATA).contents
            find_data.sFileName = b"ch01-record.ts"
            find_data.dwFileSize = 12345
            find_data.struStartTime = dvr_mod.sdk.NET_DVR_TIME.from_datetime(datetime.datetime(2024, 1, 1, 10, 0, 0))
            find_data.struStopTime = dvr_mod.sdk.NET_DVR_TIME.from_datetime(datetime.datetime(2024, 1, 1, 10, 0, 10))
        return status

    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_FindFile", fake_find_file)
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_FindNextFile", fake_find_next)
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_FindClose", lambda handle: calls["find_close"].append(handle) or 1)

    start = datetime.datetime(2024, 1, 1, 10, 0, 0)
    stop = datetime.datetime(2024, 1, 1, 10, 5, 0)
    handle = dvr_mod.find_file(9, 1, start, stop, file_type=0)

    assert handle == 42
    assert calls["find_file"] == {
        "user_id": 9,
        "channel": 1,
        "file_type": 0,
        "start": start,
        "stop": stop,
    }

    finding = dvr_mod.find_next_file(handle)
    success = dvr_mod.find_next_file(handle)
    finished = dvr_mod.find_next_file(handle)
    dvr_mod.find_close(handle)

    assert finding.status == dvr_mod.FindNextStatus.FINDING
    assert finding.entry is None
    assert success.status == dvr_mod.FindNextStatus.SUCCESS
    assert success.entry == dvr_mod.FindFileEntry(
        filename="ch01-record.ts",
        size=12345,
        start=datetime.datetime(2024, 1, 1, 10, 0, 0),
        stop=datetime.datetime(2024, 1, 1, 10, 0, 10),
    )
    assert finished.status == dvr_mod.FindNextStatus.NO_MORE_FILE
    assert finished.entry is None
    assert calls["find_close"] == [42]


def test_make_playback_es_callback_invokes_python_callable():
    received = []

    callback = dvr_mod.make_playback_es_callback(
        lambda handle, packet_ptr, user: received.append(
            (handle, packet_ptr.contents.dwPacketType, packet_ptr.contents.dwPacketSize, user)
        )
    )

    raw = (dvr_mod.sdk.BYTE * 4)(1, 2, 3, 4)
    packet = dvr_mod.sdk.NET_DVR_PACKET_INFO_EX()
    packet.dwPacketType = 1
    packet.dwPacketSize = 4
    packet.pPacketBuffer = ctypes.cast(raw, ctypes.POINTER(dvr_mod.sdk.BYTE))

    callback(88, ctypes.pointer(packet), None)

    assert received == [(88, 1, 4, None)]


def test_playback_helpers_translate_calls_and_results(monkeypatch):
    calls = {"open": None, "callback": None, "controls": [], "stop": []}

    def fake_open(user_id, channel, start_time, stop_time, hwnd):
        calls["open"] = {
            "user_id": user_id,
            "channel": channel,
            "start": start_time.as_datetime(),
            "stop": stop_time.as_datetime(),
            "hwnd": hwnd,
        }
        return 88

    def fake_set_callback(handle, callback, user):
        calls["callback"] = {"handle": handle, "callback": callback, "user": user}
        return 1

    def fake_control(handle, control_code, in_buffer, in_len, out_buffer, out_len):
        entry = {
            "handle": handle,
            "control_code": control_code,
            "in_len": in_len,
            "out_len": out_len,
        }
        if control_code == dvr_mod.sdk.PlayBackControl.NET_DVR_SET_TRANS_TYPE:
            transport = ctypes.cast(in_buffer, ctypes.POINTER(dvr_mod.sdk.BYTE * 4)).contents
            entry["transport"] = list(transport)
        elif control_code == dvr_mod.sdk.PlayBackControl.NET_DVR_PLAYSETTIME:
            ts = ctypes.cast(in_buffer, dvr_mod.sdk.LPNET_DVR_TIME).contents
            entry["timestamp"] = ts.as_datetime()
        elif control_code == dvr_mod.sdk.PlayBackControl.NET_DVR_PLAYGETPOS:
            pos = ctypes.cast(out_buffer, ctypes.POINTER(dvr_mod.sdk.DWORD))
            pos.contents.value = 73
        calls["controls"].append(entry)
        return 1

    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_PlayBackByTime", fake_open)
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_SetPlayBackESCallBack", fake_set_callback)
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_PlayBackControl_V40", fake_control)
    monkeypatch.setattr(dvr_mod.sdk, "NET_DVR_StopPlayBack", lambda handle: calls["stop"].append(handle) or 1)

    start = datetime.datetime(2024, 1, 1, 10, 0, 0)
    stop = datetime.datetime(2024, 1, 1, 10, 5, 0)
    callback = dvr_mod.make_playback_es_callback(lambda *_args: None)

    handle = dvr_mod.open_playback_by_time(11, 1, start, stop)
    dvr_mod.set_playback_es_callback(handle, callback, user=123)
    dvr_mod.playback_set_transport_type(handle, transport_type=1)
    dvr_mod.playback_start(handle)
    position = dvr_mod.playback_get_position_percent(handle)
    dvr_mod.playback_seek(handle, datetime.datetime(2024, 1, 1, 10, 1, 30))
    dvr_mod.stop_playback(handle)

    assert handle == 88
    assert calls["open"] == {
        "user_id": 11,
        "channel": 1,
        "start": start,
        "stop": stop,
        "hwnd": 0,
    }
    assert calls["callback"] == {"handle": 88, "callback": callback, "user": 123}
    assert calls["controls"][0] == {
        "handle": 88,
        "control_code": dvr_mod.sdk.PlayBackControl.NET_DVR_SET_TRANS_TYPE,
        "in_len": 4,
        "out_len": 0,
        "transport": [1, 0, 0, 0],
    }
    assert calls["controls"][1] == {
        "handle": 88,
        "control_code": dvr_mod.sdk.PlayBackControl.NET_DVR_PLAYSTART,
        "in_len": 0,
        "out_len": 0,
    }
    assert calls["controls"][2] == {
        "handle": 88,
        "control_code": dvr_mod.sdk.PlayBackControl.NET_DVR_PLAYGETPOS,
        "in_len": 0,
        "out_len": ctypes.sizeof(dvr_mod.sdk.DWORD()),
    }
    assert calls["controls"][3] == {
        "handle": 88,
        "control_code": dvr_mod.sdk.PlayBackControl.NET_DVR_PLAYSETTIME,
        "in_len": ctypes.sizeof(dvr_mod.sdk.NET_DVR_TIME()),
        "out_len": 0,
        "timestamp": datetime.datetime(2024, 1, 1, 10, 1, 30),
    }
    assert position == 73
    assert calls["stop"] == [88]