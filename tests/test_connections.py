"""Connection lifecycle tests with mocked Bleak clients."""
import asyncio
from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_valid_response(bm6, make_connector, client, frame, monkeypatch):
    connector = make_connector()
    async def notify(_uuid, callback):
        await callback(None, frame())
    client.start_notify.side_effect = notify
    establish = AsyncMock(return_value=client)
    monkeypatch.setattr(bm6, "establish_connection", establish)
    result = await connector.get_data()
    assert result.RealTime.Voltage == pytest.approx(12.60)
    client.disconnect.assert_awaited_once()
    client.stop_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_response(bm6, make_connector, client, monkeypatch):
    connector = make_connector()
    monkeypatch.setattr(bm6, "establish_connection", AsyncMock(return_value=client))
    async def fast_sleep(_):
        # Simulate time passing quickly without producing any reading.
        return None
    monkeypatch.setattr(bm6.asyncio, "sleep", fast_sleep)
    with pytest.raises(bm6.BM6DeviceError, match="No valid real-time response"):
        await connector.get_data()
    client.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_scanner_fallback(bm6, make_connector, client, frame, monkeypatch):
    connector = make_connector(scanner_count=2)
    async def establish(_cls, device, _name, **kwargs):
        if device is connector._scanners[0].ble_device:
            raise ConnectionError("first proxy unavailable")
        return client
    async def notify(_uuid, callback):
        await callback(None, frame())
    client.start_notify.side_effect = notify
    monkeypatch.setattr(bm6, "establish_connection", establish)
    result = await connector.get_data()
    assert result.RealTime.Voltage == pytest.approx(12.60)
    assert result.Advertisement.Scanner == "proxy-1"


@pytest.mark.asyncio
async def test_connection_timeout_argument(bm6, make_connector, client, frame, monkeypatch):
    connector = make_connector()
    async def notify(_uuid, callback):
        await callback(None, frame())
    client.start_notify.side_effect = notify
    establish = AsyncMock(return_value=client)
    monkeypatch.setattr(bm6, "establish_connection", establish)
    await connector.get_data()
    assert establish.await_args.kwargs["timeout"] == bm6.BLEAK_CLIENT_TIMEOUT
    assert establish.await_args.kwargs["max_attempts"] == 3


@pytest.mark.asyncio
async def test_cleanup_failure_still_disconnects(make_connector, client):
    connector = make_connector()
    client.stop_notify.side_effect = RuntimeError("proxy failure")
    await connector._cleanup(client)
    client.disconnect.assert_awaited_once()
