"""Notification tests against the real BM6 connector source."""
import pytest


@pytest.mark.asyncio
async def test_valid_encrypted_notification(bm6, make_connector, frame):
    connector = make_connector()
    # Cipher is stubbed as identity; this exercises the decrypted-frame path.
    await connector._notify_callback(None, frame())
    assert connector._data.RealTime.Voltage == pytest.approx(12.60)
    assert connector._data.RealTime.Temperature == 24
    assert connector._data.RealTime.Percent == 75


@pytest.mark.asyncio
async def test_zero_voltage_does_not_replace_valid_reading(make_connector, frame):
    connector = make_connector()
    await connector._notify_callback(None, frame())
    previous = connector._data.RealTime
    await connector._notify_callback(None, frame(voltage=0))
    assert connector._data.RealTime is previous


@pytest.mark.asyncio
async def test_empty_notification_ignored(make_connector):
    connector = make_connector()
    await connector._notify_callback(None, bytearray())
    assert connector._data.RealTime is None


@pytest.mark.asyncio
async def test_incomplete_encrypted_packet_ignored(make_connector):
    connector = make_connector()
    await connector._notify_callback(None, bytearray(b"abc"))
    assert connector._data.RealTime is None


@pytest.mark.asyncio
async def test_truncated_real_time_message_ignored(make_connector):
    connector = make_connector()
    # A valid-size encrypted packet can decrypt to an incomplete message.
    from unittest.mock import patch
    with patch.object(connector, "_decrypt", return_value=bytes.fromhex("d15507")):
        await connector._notify_callback(None, bytearray(16))
    assert connector._data.RealTime is None


@pytest.mark.asyncio
async def test_malformed_real_time_fields_ignored(make_connector, frame):
    connector = make_connector()
    # A malformed field cannot be expressed in real decrypted bytes because
    # .hex() always yields hex digits. Simulate a parser rejecting the frame.
    from unittest.mock import patch
    module = __import__(connector.__class__.__module__, fromlist=["BM6RealTimeData"])
    with patch.object(module, "BM6RealTimeData", side_effect=ValueError("bad field")):
        await connector._notify_callback(None, frame())
    assert connector._data.RealTime is None


@pytest.mark.asyncio
async def test_unknown_notification_type_logged(make_connector, caplog):
    connector = make_connector()
    with caplog.at_level("DEBUG"):
        await connector._notify_callback(None, bytearray.fromhex("aabbcc" + "00" * 13))
    assert connector._data.RealTime is None
    assert "unknown notification type" in caplog.text
