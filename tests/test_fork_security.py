"""Checks for the security hardening (run: .venv/bin/python -m pytest -q -p no:aiohttp tests)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "addon" / "app"))

import asyncio  # noqa: E402

import main  # noqa: E402
import storage  # noqa: E402
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402


async def _ok(request):
    return web.Response(text="ok")


def test_only_audio_is_reachable_outside_ingress():
    async def run():
        app = web.Application(middlewares=[main._restrict_to_ingress_middleware])
        for path in ("/", "/api/devices", "/images/x", "/audio/x.aac", "/app.js"):
            app.router.add_get(path, _ok)
        # Connects from 127.0.0.1, i.e. not from the ingress proxy.
        async with TestClient(TestServer(app)) as client:
            assert (await client.get("/audio/x.aac")).status == 200
            for path in ("/", "/api/devices", "/images/x", "/app.js"):
                assert (await client.get(path)).status == 403, path

    asyncio.run(run())


def test_managed_logins(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "data.json"))
    assert storage.get_managed_logins() == set()
    storage.set_login_managed("dev-a", True)
    # A saved device must not make an existing login ours.
    storage.save_device("AF01TEST", {"mqtt_user": "someone-else"})
    assert storage.get_managed_logins() == {"dev-a"}
    storage.set_login_managed("dev-a", False)
    assert storage.get_managed_logins() == set()
