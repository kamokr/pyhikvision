# pyhikvision

High-level Python wrapper around Hikvision HCNetSDK.

## Quickstart

### Optional eager SDK initialization

If startup latency is preferable to first-connect latency, initialize the SDK
when your program starts:

```python
import hikvision

# optional eager initialization
hikvision.net_dvr.init()
try:
    with HikvisionDevice("192.168.1.10", 8000, "admin", "your_password") as device:
        print("Connected:", device.is_connected)
finally:
    hikvision.net_dvr.cleanup()
```

Note: SDK timeout settings are process-global and applied on first
initialization. Later initialize/connect calls with different timeout values are
ignored while the SDK remains initialized.

### 1) Login and device info

```python
import hikvision

with hikvision.HikvisionDevice("192.168.1.10", 8000, "admin", "your_password") as device:
	print("Connected:", device.is_connected)
	print("Serial:", device.device_info.serial_number)
	print("Analog channels:", device.device_info.start_channel, "..", device.device_info.start_channel + device.device_info.num_channels - 1)
	print("Digital channels:", device.device_info.start_dchannel, "..", device.device_info.start_dchannel + device.device_info.num_dchannels - 1)
```

### 2) Search recordings

```python
import datetime

import hikvision

now = datetime.datetime.now()
start = now - datetime.timedelta(minutes=10)

with hikvision.HikvisionDevice("192.168.1.10", 8000, "admin", "your_password") as device:
    records = device.search_recordings(channel=33, start=start, stop=now)
    print("Found", len(records), "recordings")
    for record in records[:3]:
        print(record.filename, record.start, record.stop, record.size)
```

### 3) Playback and read packets

```python
import datetime

import hikvision

now = datetime.datetime.now()
start = now - datetime.timedelta(minutes=2)

# optional eager initialization
hikvision.net_dvr.init()

try:
	with hikvision.HikvisionDevice("192.168.1.10", 8000, "admin", "your_password") as device:
		stream = device.start_playback(
				channel=33,
				start=start,
				stop=now,
				mode=hik.PlaybackMode.STEP)
		try:
			# Read a few packets from the ES callback queue.
			for _ in range(20):
				pkt = stream.next_packet(timeout=1.0)
				if pkt is None:
					break

				print(pkt.packet_type_name, pkt.timestamp, len(pkt.data))
		finally:
			stream.close()
finally:
	hikvision.net_dvr.cleanup()
```

### 4) Mid-level login/logout (net.dvr)

```python
from hikvision import net_dvr

net_dvr.init()
user_id = None

try:
    result = net_dvr.login("192.168.1.10", 8000, "admin", "your_password")
    user_id = result.user_id

    info = result.device_info
    print("User ID:", user_id)
    print("Serial:", info.serial_number)
    print("Analog channels:", info.start_channel, "..", info.start_channel + info.num_channels - 1)
    print("Digital channels:", info.start_dchannel, "..", info.start_dchannel + info.num_dchannels - 1)

    net_dvr.logout(user_id)
    user_id = None

finally:
    if user_id is not None:
        net_dvr.logout(user_id)
    net_dvr.cleanup()
```

See `examples/login_logout.py` for a runnable script version.

## Integration tests

```bash
export HIKVISION_TEST_HOST=192.168.1.10
export HIKVISION_TEST_PORT=8000
export HIKVISION_TEST_USERNAME=admin
export HIKVISION_TEST_PASSWORD='your_password'

pytest -q -m integration
```