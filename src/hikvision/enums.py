from enum import IntEnum


class RecordingFileType(IntEnum):
    ALL = 0xFF
    CONTINUOUS = 0
    MOTION_DETECTION = 1
    ALARM = 2
    ALARM_OR_MOTION = 3
    ALARM_AND_MOTION = 4
    COMMAND_TRIGGER = 5
    MANUAL = 6
    INTELLIGENT = 7