"""Load the real BM6 connector with lightweight dependency stubs.

Tests run without Home Assistant, Bluetooth hardware or network access.
The cipher stub is an identity transform: notification tests validate packet
handling and parsing, NOT AES cryptographic correctness.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components/bm6/bm6_connect.py"


def module(name, **attributes):
    mod = types.ModuleType(name)
    mod.__dict__.update(attributes)
    sys.modules[name] = mod
    return mod


@pytest.fixture
def bm6(monkeypatch):
    for name in (
        "bm6_testpkg", "bm6_testpkg.const", "bleak", "bleak.backends",
        "bleak.backends.characteristic", "bleak.backends.scanner",
        "bleak_retry_connector", "Crypto", "Crypto.Cipher", "habluetooth",
        "homeassistant", "homeassistant.core", "homeassistant.components",
        "homeassistant.components.bluetooth",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    class IdentityCipher:
        def encrypt(self, value):
            return bytes(value)
        def decrypt(self, value):
            return bytes(value)

    class AES:
        MODE_CBC = 2
        @staticmethod
        def new(*args):
            return IdentityCipher()

    constants = dict(
        CHARACTERISTIC_UUID_NOTIFY="FFF4", CHARACTERISTIC_UUID_WRITE="FFF3",
        CRYPT_KEY=bytearray(range(16)), BLEAK_CLIENT_TIMEOUT=10,
        BLEAK_CLEANUP_TIMEOUT=5,
        GATT_DATA_REALTIME="d1550700000000000000000000000000",
        GATT_DATA_VERSION="d1550100000000000000000000000000",
        GATT_NOTIFY_REALTIME_PREFIX="d15507",
        GATT_NOTIFY_VERSION_PREFIX="d15501",
    )
    sys.modules["bm6_testpkg"].__path__ = []
    sys.modules["bm6_testpkg.const"].__dict__.update(constants)
    sys.modules["bleak"].BleakClient = type("BleakClient", (), {})
    sys.modules["bleak.backends.characteristic"].BleakGATTCharacteristic = type("BleakGATTCharacteristic", (), {})
    sys.modules["bleak.backends.scanner"].AdvertisementData = type("AdvertisementData", (), {})
    sys.modules["bleak_retry_connector"].establish_connection = AsyncMock()
    sys.modules["Crypto.Cipher"].AES = AES
    sys.modules["habluetooth"].BaseHaScanner = type("BaseHaScanner", (), {})
    sys.modules["habluetooth"].BluetoothScannerDevice = type("BluetoothScannerDevice", (), {})
    sys.modules["homeassistant.core"].HomeAssistant = type("HomeAssistant", (), {})
    sys.modules["homeassistant.components.bluetooth"].async_scanner_devices_by_address = lambda *a, **k: []

    spec = importlib.util.spec_from_file_location("bm6_testpkg.bm6_connect", SOURCE)
    connector_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, connector_module)
    spec.loader.exec_module(connector_module)
    return connector_module


@pytest.fixture
def make_connector(bm6):
    def factory(scanner_count=1):
        connector = object.__new__(bm6.BM6Connector)
        connector._address = "AA:BB:CC:DD:EE:FF"
        connector.hass = object()
        connector._data = bm6.BM6Data(None, None)
        connector._scanners = [
            SimpleNamespace(
                scanner=SimpleNamespace(name=f"proxy-{i}"),
                ble_device=SimpleNamespace(address=connector._address),
                advertisement=SimpleNamespace(rssi=-40 - i),
            )
            for i in range(scanner_count)
        ]
        return connector
    return factory


@pytest.fixture
def frame():
    """32 hex characters, valid fixed-position BM6 reading (12.60 V, 24 C)."""
    def make(voltage=1260, prefix="d15507", percent=75, state=0):
        return bytearray.fromhex(
            prefix + "00" + "18" + f"{state:02x}" + f"{percent:02x}"
            + f"{voltage:04x}" + "0001" + "0002" + "000000"
        )
    return make


@pytest.fixture
def client():
    class FakeClient:
        is_connected = True
        def __init__(self):
            self.stop_notify = AsyncMock()
            self.disconnect = AsyncMock(side_effect=self._disconnect)
            self.start_notify = AsyncMock()
            self.write_gatt_char = AsyncMock()
            self.callback = None
        async def _disconnect(self):
            self.is_connected = False
    return FakeClient()
