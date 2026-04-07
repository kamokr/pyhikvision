# pyhikvision

High-level Python wrapper around Hikvision HCNetSDK.

## Quickstart

### 1) Login and device info

```python
from hikvision import HikvisionDevice

with HikvisionDevice("192.168.1.10", 8000, "admin", "your_password") as device:
	print("Connected:", device.is_connected)
	print("Serial:", device.device_info.serial_number)
	print("Analog channels:", device.device_info.start_channel, "..", device.device_info.start_channel + device.device_info.num_channels - 1)
    print("Digital channels:", device.device_info.start_dchannel, "..", device.device_info.start_dchannel + device.device_info.num_dchannels - 1)
```

### 2) Search recordings

```python
import datetime

from hikvision import HikvisionDevice

now = datetime.datetime.now()
start = now - datetime.timedelta(minutes=10)

with HikvisionDevice("192.168.1.10", 8000, "admin", "your_password") as device:
	records = device.search_recordings(channel=33, start=start, stop=now)
	print("Found", len(records), "recordings")
	for r in records[:3]:
		print(r.filename, r.start, r.stop, r.size)
```

### 3) Playback and read packets

```python
import datetime

from hikvision import HikvisionDevice, PlaybackMode, PlaybackPacketType

now = datetime.datetime.now()
start = now - datetime.timedelta(minutes=2)

with HikvisionDevice("192.168.1.10", 8000, "admin", "your_password") as device:
	stream = device.open_playback(channel=33, start=start, stop=now)
	try:
		stream.play(PlaybackMode.STEP)

		# Read a few packets from the ES callback queue.
		for _ in range(20):
			pkt = stream.next_packet(timeout=1.0)
			if pkt is None:
				break
			if pkt.packet_type == PlaybackPacketType.VIDEO_I_FRAME:
				print("I-frame", pkt.timestamp, len(pkt.data))
	finally:
		stream.close()
```

## Integration tests

```bash
export HIKVISION_TEST_HOST=192.168.1.10
export HIKVISION_TEST_PORT=8000
export HIKVISION_TEST_USERNAME=admin
export HIKVISION_TEST_PASSWORD='your_password'

pytest -q -m integration
```