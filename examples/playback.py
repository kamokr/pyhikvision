#!/usr/bin/env python3
import datetime
import os

import hikvision

now = datetime.datetime.now()
start = now - datetime.timedelta(minutes=10)
stop = start + datetime.timedelta(minutes=1)

host = os.getenv("HIKVISION_TEST_HOST", "192.168.1.10")
port = int(os.getenv("HIKVISION_TEST_PORT", "8000"))
username = os.getenv("HIKVISION_TEST_USERNAME", "admin")
password = os.getenv("HIKVISION_TEST_PASSWORD", "your_password")

hikvision.net_dvr.init()  # optional, eagerly initialize the SDK before creating any devices

try:
    with hikvision.HikvisionDevice(host, port, username, password) as device:
        stream = device.start_playback(
            channel=33,
            start=start,
            stop=stop,
            mode=hikvision.PlaybackMode.STEP,
        )
        try:
            # read a few packets from the ES callback queue.
            for _ in range(20):
                pkt = stream.next_packet(timeout=1.0)
                if pkt is None:
                    break

                print(pkt.packet_type_name, pkt.timestamp, len(pkt.data))

        finally:
            stream.close()

finally:
    hikvision.net_dvr.cleanup()