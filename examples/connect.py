#!/usr/bin/env python3
"""High-level example: connect to a device and print basic channel metadata."""

import os

import hikvision


host = os.getenv("HIKVISION_TEST_HOST", "192.168.1.10")
port = int(os.getenv("HIKVISION_TEST_PORT", "8000"))
username = os.getenv("HIKVISION_TEST_USERNAME", "admin")
password = os.getenv("HIKVISION_TEST_PASSWORD", "your_password")

with hikvision.HikvisionDevice(host, port, username, password) as device:
    print("Connected:", device.is_connected)
    print("Serial:", device.device_info.serial_number)
    print("Analog channels:", device.device_info.start_channel, "..", device.device_info.start_channel + device.device_info.num_channels - 1)
    print("Digital channels:", device.device_info.start_dchannel, "..", device.device_info.start_dchannel + device.device_info.num_dchannels - 1)
