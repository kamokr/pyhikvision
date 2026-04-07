import importlib
import os
import platform
import sys

import pytest


class DummyLib:
    def __getattr__(self, _name):
        def _fn(*_args, **_kwargs):
            return 0
        return _fn


def import_fresh_sdk(monkeypatch, sdk_dir):
    # Force env override so import does not depend on packaged resources.
    monkeypatch.setenv("HIKVISION_SDK_PATH", str(sdk_dir))

    loaded = {}

    import ctypes

    def fake_cdll(path):
        loaded["path"] = path
        return DummyLib()

    monkeypatch.setattr(ctypes, "CDLL", fake_cdll)

    sys.modules.pop("hikvision.sdk", None)
    module = importlib.import_module("hikvision.sdk")
    return module, loaded


def test_env_override_loads_from_override_dir(monkeypatch, tmp_path):
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()

    if sys.platform.startswith("win"):
        lib_name = "HCNetSDK.dll"
    else:
        lib_name = "libhcnetsdk.so"

    lib_path = sdk_dir / lib_name
    lib_path.write_bytes(b"")

    _module, loaded = import_fresh_sdk(monkeypatch, sdk_dir)
    assert loaded["path"] == str(lib_path)


def test_env_override_missing_directory_raises(monkeypatch, tmp_path):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setenv("HIKVISION_SDK_PATH", str(missing))

    sys.modules.pop("hikvision.sdk", None)
    with pytest.raises(FileNotFoundError):
        importlib.import_module("hikvision.sdk")


def test_platform_vendor_info_linux_x86_64(monkeypatch, tmp_path):
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    (sdk_dir / "libhcnetsdk.so").write_bytes(b"")

    monkeypatch.setattr(sys, "platform", "linux", raising=False)
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")

    module, _loaded = import_fresh_sdk(monkeypatch, sdk_dir)

    rel_dir, names = module._platform_vendor_info()
    assert rel_dir.endswith("vendor/linux-x86_64")
    assert "libhcnetsdk.so" in names


def test_platform_vendor_info_windows_amd64_alias(monkeypatch, tmp_path):
    sdk_dir = tmp_path / "sdk"
    sdk_dir.mkdir()
    (sdk_dir / "HCNetSDK.dll").write_bytes(b"")

    monkeypatch.setattr(sys, "platform", "win32", raising=False)
    monkeypatch.setattr(platform, "machine", lambda: "AMD64")

    module, _loaded = import_fresh_sdk(monkeypatch, sdk_dir)

    rel_dir, names = module._platform_vendor_info()
    assert rel_dir.endswith("vendor/win-amd64")
    assert "HCNetSDK.dll" in names