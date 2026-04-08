#!/usr/bin/env python3
import datetime
import os

import hikvision as hik

now = datetime.datetime.now()
start = now - datetime.timedelta(minutes=60)

host = os.getenv("HIKVISION_TEST_HOST", "192.168.1.10")
port = int(os.getenv("HIKVISION_TEST_PORT", "8000"))
username = os.getenv("HIKVISION_TEST_USERNAME", "admin")
password = os.getenv("HIKVISION_TEST_PASSWORD", "your_password")

with hik.HikvisionDevice(host, port, username, password) as device:
    records = device.search_recordings(channel=33, start=start, stop=now)
    print("Found", len(records), "recordings")
    for record in records[:3]:
        print(f"file: {record.filename}, from: {record.start}, to: {record.stop}, size: {record.size}")