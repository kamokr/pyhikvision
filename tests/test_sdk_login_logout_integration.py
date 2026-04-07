# tests/test_sdk_login_logout_integration.py
import ctypes
import importlib
import os

import pytest


pytestmark = pytest.mark.integration


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not set")
    return value


def _noop_login_cb(lUserID, dwResult, lpDeviceInfo, pUser):
    # Callback required by the login struct type.
    return None


def test_sdk_login_logout_low_level():
    host = _require_env("HIKVISION_TEST_HOST")
    port = int(os.getenv("HIKVISION_TEST_PORT", "8000"))
    username = _require_env("HIKVISION_TEST_USERNAME")
    password = _require_env("HIKVISION_TEST_PASSWORD")

    sdk = importlib.import_module("hikvision.sdk")

    # 1) Init SDK
    assert sdk.NET_DVR_Init() != 0, f"NET_DVR_Init failed, err={sdk.NET_DVR_GetLastError()}"
    try:
        sdk.NET_DVR_SetConnectTime(5000, 3)
        sdk.NET_DVR_SetRecvTimeOut(5000)

        # 2) Build login structs
        login_info = sdk.NET_DVR_USER_LOGIN_INFO()
        device_info = sdk.NET_DVR_DEVICEINFO_V40()

        login_info.sDeviceAddress = host.encode("ascii")
        login_info.wPort = port
        login_info.sUserName = username.encode("ascii")
        login_info.sPassword = password.encode("ascii")
        login_info.byUseTransport = 0
        login_info.bUseAsynLogin = 0
        login_info.byProxyType = 0
        login_info.byUseUTCTime = 0
        login_info.byLoginMode = 0
        login_info.byHttps = 0
        login_info.iProxyID = 0
        login_info.byVerifyMode = 0
        login_info.byRes3 = (sdk.BYTE * 119)(*([0] * 119))

        cb = sdk.fLoginResultCallBack(_noop_login_cb)
        login_info.cbLoginResult = cb
        login_info.pUser = None

        # 3) Login
        user_id = sdk.NET_DVR_Login_V40(ctypes.byref(login_info), ctypes.byref(device_info))
        assert user_id != -1, f"NET_DVR_Login_V40 failed, err={sdk.NET_DVR_GetLastError()}"

        # 4) Logout
        try:
            assert sdk.NET_DVR_Logout(user_id) != 0, f"NET_DVR_Logout failed, err={sdk.NET_DVR_GetLastError()}"
        finally:
            # keep callback alive until after logout
            _ = cb
    finally:
        # 5) Cleanup SDK
        assert sdk.NET_DVR_Cleanup() != 0, f"NET_DVR_Cleanup failed, err={sdk.NET_DVR_GetLastError()}"