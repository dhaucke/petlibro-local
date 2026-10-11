"""Supervisor API calls for managing the MQTT broker add-on.

Works with the Mosquitto add-on (core_mosquitto) and the EMQX add-on (*_emqx),
whichever is installed. Mosquitto logins live in its add-on options and need a
broker restart; EMQX logins go into its built-in user database through the EMQX
REST API (API key from Settings) and apply without a restart.
"""

import logging
import os

import aiohttp

import storage
from ha_config import SUPERVISOR_TOKEN, _headers

_LOGGER = logging.getLogger(__name__)

SUPERVISOR_URL = "http://supervisor"
MOSQUITTO_SLUG = "core_mosquitto"
EMQX_PORT = 18083
_EMQX_USERS = "/authentication/password_based%3Abuilt_in_database/users"


async def broker_slug() -> str:
    """Slug of the broker add-on: the one set in Settings, else the only installed
    (or only running) Mosquitto/EMQX add-on. "" when that is ambiguous."""
    chosen = storage.get_settings().get("broker_addon", "").strip()
    if chosen:
        return chosen
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{SUPERVISOR_URL}/addons", headers=_action_headers(),
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                addons = (await resp.json()).get("data", {}).get("addons", [])
    except Exception:
        _LOGGER.exception("Could not list add-ons, assuming Mosquitto")
        return MOSQUITTO_SLUG
    brokers = [a for a in addons if a.get("slug") == MOSQUITTO_SLUG or a.get("slug", "").endswith("_emqx")]
    # With both installed, the running one is the broker in use
    running = [a for a in brokers if a.get("state") == "started"]
    candidates = running or brokers or [{"slug": MOSQUITTO_SLUG}]
    if len(candidates) > 1:
        _LOGGER.error("Several MQTT broker add-ons (%s), set the one in use under Settings → MQTT → Broker add-on",
                      ", ".join(a["slug"] for a in candidates))
        return ""
    # ponytail: asks the Supervisor on every broker operation (rare), no cache to go stale
    return candidates[0]["slug"]


def is_emqx(slug: str) -> bool:
    return slug.endswith("_emqx")


def _action_headers() -> dict:
    """Headers for Supervisor action POSTs (no body, so no Content-Type)."""
    return {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}


# The broker stop_mosquitto() stopped: start_mosquitto() restarts that one, since
# discovery can no longer tell it apart once nothing is running
_stopped_slug: str = ""


async def _addon_action(action: str, slug: str = "") -> bool:
    if not SUPERVISOR_TOKEN:
        _LOGGER.error("SUPERVISOR_TOKEN is not set — hassio_api may not be enabled")
        return False

    slug = slug or await broker_slug()
    if not slug:
        return False
    url = f"{SUPERVISOR_URL}/addons/{slug}/{action}"
    _LOGGER.info("Supervisor: POST %s", url)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers=_action_headers(),
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                if resp.status == 200:
                    _LOGGER.info("Mosquitto %s: OK (response: %s)", action, text[:120])
                    return True
                _LOGGER.error(
                    "Mosquitto %s failed: HTTP %d — %s",
                    action, resp.status, text[:300],
                )
                return False
    except Exception:
        _LOGGER.exception("Mosquitto %s request failed", action)
        return False


async def get_addon_info() -> dict:
    """Fetch Mosquitto add-on info for diagnostics. Logs the slug + state."""
    if not SUPERVISOR_TOKEN:
        _LOGGER.error("SUPERVISOR_TOKEN not set")
        return {}
    slug = await broker_slug()
    if not slug:
        return {}
    url = f"{SUPERVISOR_URL}/addons/{slug}/info"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=_action_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    state = data.get("data", {}).get("state", "?")
                    _LOGGER.info("Mosquitto info: state=%s", state)
                    return data
                text = await resp.text()
                _LOGGER.error("Mosquitto info failed: HTTP %d — %s", resp.status, text[:200])
                return {}
    except Exception:
        _LOGGER.exception("Mosquitto info request failed")
        return {}


async def stop_mosquitto() -> bool:
    global _stopped_slug
    slug = await broker_slug()
    if slug and await _addon_action("stop", slug):
        _stopped_slug = slug
        return True
    return False


async def start_mosquitto() -> bool:
    global _stopped_slug
    slug, _stopped_slug = _stopped_slug, ""
    return await _addon_action("start", slug)


async def remove_mosquitto_login(username: str) -> str:
    """Remove a login entry from Mosquitto's options.

    Returns:
        "removed"   — entry found and removed
        "not_found" — entry was not present, no change
        "error"     — Supervisor API call failed
        "removed_live" — EMQX: removed, no broker restart needed
    """
    slug = await broker_slug()
    if not slug:
        return "error"
    if is_emqx(slug):
        return await _emqx_remove(slug, username)
    if not SUPERVISOR_TOKEN:
        _LOGGER.error("SUPERVISOR_TOKEN is not set")
        return "error"

    info_url = f"{SUPERVISOR_URL}/addons/{MOSQUITTO_SLUG}/info"
    options_url = f"{SUPERVISOR_URL}/addons/{MOSQUITTO_SLUG}/options"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                info_url,
                headers=_action_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    _LOGGER.error("Could not read Mosquitto info: HTTP %d — %s", resp.status, text[:200])
                    return "error"
                info = await resp.json()

        current_opts = info.get("data", {}).get("options", {})
        logins = list(current_opts.get("logins", []))
        if username not in storage.get_managed_logins():
            _LOGGER.warning("Login %s... was not created by Petlibro Local, leaving it in place", username[:4])
            return "not_managed"
        new_logins = [e for e in logins if e.get("username") != username]
        if len(new_logins) == len(logins):
            _LOGGER.info("Login for %s... not found in Mosquitto (nothing to remove)", username[:4])
            return "not_found"

        new_options = {**current_opts, "logins": new_logins}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                options_url,
                json={"options": new_options},
                headers={**_action_headers(), "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info("Removed Mosquitto login for %s...", username[:4])
                    storage.set_login_managed(username, False)
                    return "removed"
                text = await resp.text()
                _LOGGER.error("Failed to save Mosquitto options: HTTP %d — %s", resp.status, text[:200])
                return "error"
    except Exception:
        _LOGGER.exception("remove_mosquitto_login failed")
        return "error"


async def add_mosquitto_login(username: str, password: str) -> str:
    """Add a login entry to Mosquitto's options and save.

    Returns:
        "added"  — credentials were new and saved successfully
        "exists" — credentials already present, no change made
        "conflict" — username belongs to a login we did not create, left unchanged
        "error"  — Supervisor API call failed
        "added_live" — EMQX: saved, no broker restart needed
        "manual" — EMQX without API key or built-in user database: create the login in EMQX yourself
    """
    slug = await broker_slug()
    if not slug:
        return "error"
    if is_emqx(slug):
        return await _emqx_add(slug, username, password)
    if not SUPERVISOR_TOKEN:
        _LOGGER.error("SUPERVISOR_TOKEN is not set")
        return "error"

    info_url = f"{SUPERVISOR_URL}/addons/{MOSQUITTO_SLUG}/info"
    options_url = f"{SUPERVISOR_URL}/addons/{MOSQUITTO_SLUG}/options"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                info_url,
                headers=_action_headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    _LOGGER.error("Could not read Mosquitto info: HTTP %d — %s", resp.status, text[:200])
                    return "error"
                info = await resp.json()

        current_opts = info.get("data", {}).get("options", {})
        logins = list(current_opts.get("logins", []))
        for entry in logins:
            if entry.get("username") == username:
                if entry.get("password") == password:
                    _LOGGER.info("Login for %s... already exists in Mosquitto (unchanged)", username[:4])
                    return "exists"
                # Same username, different password: only update logins we created,
                # never another user's or app's Mosquitto account.
                if username not in storage.get_managed_logins():
                    _LOGGER.error("Login %s... already exists in Mosquitto and was not created by "
                                  "Petlibro Local, refusing to change its password", username[:4])
                    return "conflict"
                entry["password"] = password
                _LOGGER.info("Login for %s... exists in Mosquitto — updating password", username[:4])
                new_options = {**current_opts, "logins": logins}
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        options_url,
                        json={"options": new_options},
                        headers={**_action_headers(), "Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status == 200:
                            return "added"
                        text = await resp.text()
                        _LOGGER.error("Failed to update Mosquitto password for %s...: HTTP %d — %s", username[:4], resp.status, text[:200])
                        return "error"

        logins.append({"username": username, "password": password})
        new_options = {**current_opts, "logins": logins}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                options_url,
                json={"options": new_options},
                headers={**_action_headers(), "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    _LOGGER.info("Added Mosquitto login for %s...", username[:4])
                    storage.set_login_managed(username, True)
                    return "added"
                text = await resp.text()
                _LOGGER.error("Failed to save Mosquitto options: HTTP %d — %s", resp.status, text[:200])
                return "error"
    except Exception:
        _LOGGER.exception("add_mosquitto_login failed")
        return "error"


# ── EMQX ───────────────────────────────────────────────────────────────────

def _owned(slug: str, username: str) -> str:
    """Ownership key for an EMQX login: per broker add-on, apart from Mosquitto logins."""
    return f"{slug}:{username}"


async def _emqx(slug: str, method: str, path: str, body: dict | None = None) -> tuple[int, str] | None:
    """Call the EMQX REST API of the broker add-on; None when no API key is set."""
    settings = storage.get_settings()
    key, secret = settings.get("emqx_api_key", ""), settings.get("emqx_api_secret", "")
    if not key or not secret:
        return None
    # Add-on containers reach each other by slug, with "-" instead of "_"
    url = f"http://{slug.replace('_', '-')}:{EMQX_PORT}/api/v5{path}"
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, json=body, auth=aiohttp.BasicAuth(key, secret),
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return resp.status, await resp.text()


async def _emqx_add(slug: str, username: str, password: str) -> str:
    from urllib.parse import quote
    try:
        result = await _emqx(slug, "POST", _EMQX_USERS, {"user_id": username, "password": password})
        if result is None:
            _LOGGER.warning("EMQX: no API key in Settings, create the login %s... in EMQX yourself", username[:4])
            return "manual"
        status, text = result
        if status in (200, 201):
            storage.set_login_managed(_owned(slug, username), True)
            _LOGGER.info("EMQX: added login %s...", username[:4])
            return "added_live"
        if status == 409:
            if _owned(slug, username) not in storage.get_managed_logins():
                # EMQX cannot show us the stored password, so a login someone else made is
                # left alone, and the user has to check it matches the device's password
                _LOGGER.warning("EMQX: login %s... already exists and was not created here, left unchanged; "
                                "check its password matches the device", username[:4])
                return "manual"
            status, text = await _emqx(slug, "PUT", f"{_EMQX_USERS}/{quote(username, safe='')}", {"password": password})
            if status == 200:
                return "added_live"
        if status == 404:
            _LOGGER.warning("EMQX: no built-in database authenticator, create the login %s... yourself "
                            "(or EMQX accepts every login)", username[:4])
            return "manual"
        _LOGGER.error("EMQX: saving login %s... failed: HTTP %d — %s", username[:4], status, text[:200])
        return "error"
    except Exception:
        _LOGGER.exception("EMQX: saving login failed")
        return "error"


async def _emqx_remove(slug: str, username: str) -> str:
    from urllib.parse import quote
    if _owned(slug, username) not in storage.get_managed_logins():
        _LOGGER.warning("Login %s... was not created by Petlibro Local, leaving it in place", username[:4])
        return "not_managed"
    try:
        result = await _emqx(slug, "DELETE", f"{_EMQX_USERS}/{quote(username, safe='')}")
        if result is None:
            return "error"
        status, text = result
        if status in (200, 204, 404):
            storage.set_login_managed(_owned(slug, username), False)
            return "removed_live" if status != 404 else "not_found"
        _LOGGER.error("EMQX: removing login %s... failed: HTTP %d — %s", username[:4], status, text[:200])
        return "error"
    except Exception:
        _LOGGER.exception("EMQX: removing login failed")
        return "error"
