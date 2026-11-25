"""Drive the real connection loop through the pre-ready race.

``_attribute_pre_ready_frame`` and the ignored-cycle reporter are unit tested
above; this module exercises the state machine that decides to use them, because
the original defect lived in the loop's branch order rather than in any helper.
A fake BLE client replays the frame sequence observed on real hardware: live
weight frames delivered while the session is still bootstrapping, then the
scale's final frame after the session reaches ``ready``.
"""

from __future__ import annotations

import asyncio
import unittest

import conftest  # noqa: F401  (installs the Home Assistant stubs)

from custom_components.yunmai_scale import manager as manager_module
from custom_components.yunmai_scale.const import UUID_FFE4
from custom_components.yunmai_scale.manager import YunmaiScaleManager
from tests.test_pre_ready_recovery import _NullStore, make_profile


def measuring_frame(weight_kg: float) -> bytes:
    """Build a 0x01 live-weight notification."""
    body = bytearray((0x0D, 0x0E, 0x10, 0x01))
    body.extend(bytes(4))
    body.extend(int(round(weight_kg * 100)).to_bytes(2, "big"))
    body.extend(bytes(2))
    body.append(0)
    body[-1] = _checksum(body)
    return bytes(body)


def measured_frame(weight_kg: float, uid: int) -> bytes:
    """Build a 0x02 final-measurement notification."""
    body = bytearray((0x0D, 0x1E, 0x10, 0x02))
    body.extend((0, 0, 0, 0, 0))  # index + unix time placeholder
    body.extend(int(uid).to_bytes(4, "big"))
    body.extend(int(round(weight_kg * 100)).to_bytes(2, "big"))
    body.extend(int(520).to_bytes(2, "big"))
    body.extend(bytes(2))
    body.append(0)
    body[-1] = _checksum(body)
    return bytes(body)


def _checksum(packet: bytearray) -> int:
    value = 0
    for byte in packet[1:-1]:
        value ^= byte
    return value


class _Characteristic:
    properties = ("write", "write-without-response")


class _Services:
    def get_characteristic(self, uuid):
        return _Characteristic()


class FakeClient:
    """Minimal stand-in for BleakClientWithServiceCache."""

    def __init__(self) -> None:
        self.services = _Services()
        self.is_connected = True
        self.writes: list[bytes] = []
        self._callback = None

    async def start_notify(self, uuid, callback, **kwargs):
        assert uuid == UUID_FFE4
        self._callback = callback

    async def stop_notify(self, uuid):
        return None

    async def disconnect(self):
        self.is_connected = False

    async def write_gatt_char(self, characteristic, packet, response=True):
        self.writes.append(packet)

    def notify(self, payload: bytes) -> None:
        assert self._callback is not None, "start_notify was never called"
        self._callback(None, bytearray(payload))


async def _run_loop(manager: YunmaiScaleManager, client: FakeClient):
    manager._client = client  # noqa: SLF001
    manager._active_generation = 1  # noqa: SLF001
    disconnected = asyncio.Event()
    return asyncio.create_task(
        manager._async_connected_loop(  # noqa: SLF001
            client,
            generation=1,
            disconnected_event=disconnected,
            adapter_index=None,
        )
    )


async def _settle(seconds: float = 0.05) -> None:
    await asyncio.sleep(seconds)


def make_manager():
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        entry_id="test",
        data={"address": "64:CF:D9:0F:CC:CB", "profiles": []},
        options={"profiles": []},
    )
    manager = YunmaiScaleManager(
        hass=object(),
        entry=entry,
        address="64:CF:D9:0F:CC:CB",
        device_name="Yunmai Scale",
        profiles=[make_profile()],
    )
    manager._store = _NullStore()  # noqa: SLF001
    return manager


class PreReadyLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._sleep = manager_module.BOOTSTRAP_SETTLE_SECONDS

    def test_pre_ready_weigh_in_is_recovered_not_dropped(self):
        async def run() -> YunmaiScaleManager:
            manager = make_manager()
            client = FakeClient()
            task = await _run_loop(manager, client)
            try:
                # Let the loop subscribe, then deliver live weight while the
                # session is still bootstrapping: this is the case that used
                # to lose the whole cycle.
                await _settle(0.01)
                client.notify(measuring_frame(81.50))
                client.notify(measuring_frame(81.90))
                await asyncio.sleep(self._sleep + 0.05)

                # Session reaches ready, then the scale finalises.
                client.notify(measured_frame(81.89, 4097))
                await _settle()
            finally:
                manager._stop_event.set()  # noqa: SLF001
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return manager

        manager = asyncio.run(run())
        self.assertEqual(len(manager.measurements), 1)
        self.assertEqual(manager.last_user_uid, 4097)
        stored = manager.get_measurement(4097)
        assert stored is not None
        self.assertAlmostEqual(stored.weight_kg, 81.89)
        self.assertEqual(manager.ignored_cycle_count, 0)

    def test_pre_ready_weigh_in_with_foreign_id_is_reported_not_stored(self):
        async def run() -> YunmaiScaleManager:
            manager = make_manager()
            client = FakeClient()
            task = await _run_loop(manager, client)
            try:
                await _settle(0.01)
                client.notify(measuring_frame(57.10))
                await asyncio.sleep(self._sleep + 0.05)
                client.notify(measured_frame(57.13, 0x2002))
                await _settle()
            finally:
                manager._stop_event.set()  # noqa: SLF001
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return manager

        manager = asyncio.run(run())
        self.assertEqual(manager.measurements, {})
        self.assertEqual(manager.ignored_cycle_count, 1)
        self.assertIn("could not be attributed", manager.last_ignored_reason or "")

    def test_pre_ready_cycle_that_recognizes_after_ready_uses_normal_path(self):
        """Recovery is a fallback: a plateau seen after ``ready`` wins."""

        async def run() -> tuple[YunmaiScaleManager, FakeClient]:
            manager = make_manager()
            client = FakeClient()
            task = await _run_loop(manager, client)
            try:
                await _settle(0.01)
                # One live frame during bootstrap, then the plateau continues
                # after `ready`, so recognition happens the normal way and the
                # fallback must not fire.
                client.notify(measuring_frame(81.70))
                await asyncio.sleep(self._sleep + 0.05)
                for weight in (81.80, 81.85, 81.90):
                    client.notify(measuring_frame(weight))
                    await _settle(0.005)
                client.notify(measured_frame(81.89, 4097))
                await _settle()
            finally:
                manager._stop_event.set()  # noqa: SLF001
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return manager, client

        manager, client = asyncio.run(run())
        self.assertEqual(len(manager.measurements), 1)
        self.assertEqual(manager.ignored_cycle_count, 0)
        # Recognition writes the profile to the scale before the final frame
        # (bootstrap = 3 writes, recognition = 3 more), which the recovery
        # path never does. Six writes therefore proves this cycle went through
        # the normal path.
        self.assertEqual(len(client.writes), 6)

    def test_normal_post_ready_weigh_in_still_works(self):
        """The recovery path must not disturb the ordinary path."""

        async def run() -> YunmaiScaleManager:
            manager = make_manager()
            client = FakeClient()
            task = await _run_loop(manager, client)
            try:
                await asyncio.sleep(self._sleep + 0.05)
                for weight in (81.60, 81.85, 81.90):
                    client.notify(measuring_frame(weight))
                    await _settle(0.005)
                client.notify(measured_frame(81.89, 4097))
                await _settle()
            finally:
                manager._stop_event.set()  # noqa: SLF001
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            return manager

        manager = asyncio.run(run())
        self.assertEqual(len(manager.measurements), 1)
        stored = manager.get_measurement(4097)
        assert stored is not None
        self.assertAlmostEqual(stored.weight_kg, 81.89)
        self.assertEqual(manager.ignored_cycle_count, 0)


if __name__ == "__main__":
    unittest.main()
