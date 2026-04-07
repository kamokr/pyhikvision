import datetime
import importlib
import sys


class DummyLib:
    def __getattr__(self, _name):
        def _fn(*_args, **_kwargs):
            return 0
        return _fn


def test_local2ts_ts2local_roundtrip(monkeypatch, tmp_path):
    # Ensure hikvision.sdk import succeeds without real native SDK.
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    sdk_lib = sdk_dir / ("HCNetSDK.dll" if sys.platform.startswith("win") else "libhcnetsdk.so")
    sdk_lib.write_bytes(b"")

    monkeypatch.setenv("HIKVISION_SDK_PATH", str(sdk_dir))

    import ctypes

    monkeypatch.setattr(ctypes, "CDLL", lambda _path: DummyLib())

    sys.modules.pop("hikvision.sdk", None)
    sys.modules.pop("hikvision.device", None)

    device = importlib.import_module("hikvision.device")

    dt = datetime.datetime(2026, 4, 7, 12, 34, 56, 123000)
    ts = device.local2ts(dt)
    dt2 = device.ts2local(ts)

    # Conversion is millisecond precision by design.
    assert abs((dt2 - dt).total_seconds()) < 0.001