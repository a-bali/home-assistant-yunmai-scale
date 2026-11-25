"""Minimal stand-in for homeassistant.components.bluetooth."""
from enum import Enum

CALLBACKS = []


class BluetoothScanningMode(str, Enum):
    ACTIVE = "active"
    PASSIVE = "passive"


class BluetoothChange(str, Enum):
    ADVERTISEMENT = "advertisement"


class BluetoothServiceInfoBleak:
    pass


def async_set_fallback_availability_interval(hass, address, interval):
    return None


def async_register_callback(hass, callback, matcher, mode):
    CALLBACKS.append((callback, matcher, mode))
    return lambda: CALLBACKS.remove((callback, matcher, mode))


def async_ble_device_from_address(hass, address, connectable=True):
    return None


def async_clear_advertisement_history(hass, address):
    return None
