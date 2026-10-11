"""Checks for Home Assistant entities (run: .venv/bin/python -m pytest -q -p no:aiohttp tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "addon" / "app"))

import asyncio  # noqa: E402

import ha_mqtt  # noqa: E402
import storage  # noqa: E402


class _Client:
    def __init__(self):
        self.sent = {}

    async def publish(self, topic, payload, retain=False):
        self.sent[topic] = payload


def test_feeders_report_food_low(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    for device_type in ("granary", "one_rfid"):
        cfg = {"device_type": device_type, "name": "Feeder"}
        keys = [key for _, key, _ in ha_mqtt._entity_configs("AF01TEST", cfg, {})]
        assert "food_low" in keys, device_type
        for surplus, expected in ((False, "ON"), (True, "OFF")):
            client = _Client()
            asyncio.run(ha_mqtt.publish_state(client, "AF01TEST", cfg, {"surplusGrain": surplus}))
            assert client.sent[ha_mqtt.state_topic("AF01TEST", "food_low")] == expected
