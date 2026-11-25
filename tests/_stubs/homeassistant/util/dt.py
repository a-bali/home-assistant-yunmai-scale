"""Minimal stand-in for homeassistant.util.dt."""
from datetime import datetime


def now():
    return datetime.now().astimezone()
