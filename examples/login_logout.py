#!/usr/bin/env python3
import os

import hikvision


def main() -> int:
    host = os.getenv("HIKVISION_TEST_HOST", "192.168.1.10")
    port = int(os.getenv("HIKVISION_TEST_PORT", "8000"))
    username = os.getenv("HIKVISION_TEST_USERNAME", "admin")
    password = os.getenv("HIKVISION_TEST_PASSWORD", "your_password")

    user_id = None

    try:
        hikvision.net_dvr.init()

        login_result = hikvision.net_dvr.login(
            host=host,
            port=port,
            username=username,
            password=password,
        )
        user_id = login_result.user_id

        info = login_result.device_info

        print("Login OK")
        print("User ID:", user_id)
        print("Serial:", info.serial_number)
        print("Analog channels:", info.start_channel, "..", info.start_channel + info.num_channels - 1)
        print("Digital channels:", info.start_dchannel, "..", info.start_dchannel + info.num_dchannels - 1)

        hikvision.net_dvr.logout(user_id)
        user_id = None
        print("Logout OK")
        return 0
    
    except hikvision.net_dvr.LoginError as exc:
        print(exc)
        return 1
    
    finally:
        if user_id is not None:
            try:
                hikvision.net_dvr.logout(user_id)
            except hikvision.net_dvr.LogoutError:
                pass

        try:
            hikvision.net_dvr.cleanup()
        except hikvision.net_dvr.HikvisionSdkError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
