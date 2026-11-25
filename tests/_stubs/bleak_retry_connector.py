"""Minimal stand-in for bleak_retry_connector."""


class BleakClientWithServiceCache:
    pass


async def establish_connection(*args, **kwargs):
    raise AssertionError("establish_connection must not run in these tests")
