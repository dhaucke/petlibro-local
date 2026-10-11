"""Checks for broker handling (run: .venv/bin/python -m pytest -q -p no:aiohttp tests)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "addon" / "app"))

import asyncio  # noqa: E402

import mosquitto  # noqa: E402
import storage  # noqa: E402


def test_version_matches_config():
    config = (ROOT / "addon" / "config.yaml").read_text()
    main = (ROOT / "addon" / "app" / "main.py").read_text()
    assert re.search(r'version: "([^"]+)"', config).group(1) == re.search(r'VERSION = "([^"]+)"', main).group(1)


def test_emqx_login_handling(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    storage.save_settings({"broker_addon": "a0d7b954_emqx"})
    calls = []
    answers = {}

    async def fake_emqx(slug, method, path, body=None):
        calls.append((method, path))
        return answers.get(method)

    monkeypatch.setattr(mosquitto, "_emqx", fake_emqx)

    async def run():
        # No API key: nothing is changed, the user is told to create the login
        assert await mosquitto.add_mosquitto_login("dev-a", "pw") == "manual"
        answers.update({"POST": (201, ""), "DELETE": (204, "")})
        assert await mosquitto.add_mosquitto_login("dev-a", "pw") == "added_live"
        assert "a0d7b954_emqx:dev-a" in storage.get_managed_logins()
        # A login someone else created in EMQX is left alone
        answers["POST"] = (409, "")
        assert await mosquitto.add_mosquitto_login("other", "pw") == "manual"
        # A Mosquitto login we created does not make the same EMQX name ours
        storage.set_login_managed("old-mosq", True)
        assert await mosquitto.add_mosquitto_login("old-mosq", "pw") == "manual"
        assert not any(c[0] == "PUT" for c in calls)
        assert await mosquitto.remove_mosquitto_login("other") == "not_managed"
        assert await mosquitto.remove_mosquitto_login("dev-a") == "removed_live"
        assert "a0d7b954_emqx:dev-a" not in storage.get_managed_logins()

    asyncio.run(run())


def test_links_to_removed_product_photos_are_cleared(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    storage.save_device("AF01TEST", {"image_url": "/api/hassio_ingress/x/images/plaf103_w"})
    storage.save_device("WF01TEST", {"image_url": "/api/hassio_ingress/x/images/custom_WF01TEST"})
    assert storage.drop_bundled_device_images() == 1
    assert storage.get_devices()["AF01TEST"]["image_url"] == ""
    assert storage.get_devices()["WF01TEST"]["image_url"].endswith("custom_WF01TEST")
