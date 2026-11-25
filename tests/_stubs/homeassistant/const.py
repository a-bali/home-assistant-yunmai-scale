"""Minimal stand-in for homeassistant.const used by the test harness."""
from enum import Enum

CONF_ADDRESS = "address"
CONF_NAME = "name"


class Platform(str, Enum):
    SENSOR = "sensor"
