"""Middle-level Hikvision SDK Python bindings.

This module provides middle-level bindings to the Hikvision SDK, exposing a more Pythonic interface while still allowing access to the underlying SDK functions. It is intended for users who want to interact with Hikvision devices without dealing with the complexities of the raw C API, but still need more control than what the high-level `hikvision` module offers. For low-level access to the SDK, see the `hikvision.sdk` module.
"""
from .net_dvr import *