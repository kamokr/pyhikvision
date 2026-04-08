# pyhikvision

Python wrapper around Hikvision HCNetSDK.

This wrapper is organized in three levels:
- Low level: direct SDK bindings in `hikvision.sdk` for raw HCNetSDK access.
- Mid level: convenience wrappers in `hikvision.net_dvr` for common operations.
- High level: `hikvision.HikvisionDevice` for Pythonic login, search, and playback workflows.

## Dependencies

Runtime: no third-party Python modules are required beyond the standard
library.

Build-time requirements (from `pyproject.toml`): `setuptools`,
`setuptools-scm`, and `wheel`.

Optional development dependency: `pytest` (for tests).

## Quickstart

Runnable examples are available in the [examples directory](examples/):

- [connect.py](examples/connect.py) - high-level login and device info.
- [search.py](examples/search.py) - recording search over a time window.
- [playback.py](examples/playback.py) - playback and packet consumption.
- [login_logout.py](examples/login_logout.py) - mid-level init/login/logout flow.

Note: SDK timeout settings are process-global and applied on first
initialization. Later initialize/connect calls with different timeout values are
ignored while the SDK remains initialized.

## Integration tests

```bash
export HIKVISION_TEST_HOST=192.168.1.10
export HIKVISION_TEST_PORT=8000
export HIKVISION_TEST_USERNAME=admin
export HIKVISION_TEST_PASSWORD='your_password'

pytest -q -m integration
```

## Build instructions

```bash
python -m build
```