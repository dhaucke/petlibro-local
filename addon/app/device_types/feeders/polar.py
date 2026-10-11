"""Polar Wet Food Feeder (PLAF109): three plates under a cooled lid.

Built from a real mqtt_proxy.py capture against the Petlibro cloud
(2026-10-11, fw 2.0.38, hw 5.2.0, serial prefix AF05):
- Feed now: WET_GRAIN_FEEDING_PLAN_SERVICE with one plan, planId 666666666,
  feedNowState true, executionTime/executionDay in local time, plate and
  feedingDuration 240 (unit not confirmed, the app sent 240).
- Stop: WET_FOOD_FEED_STOP_SERVICE with that planId.
- Plate: SET_PLATE_POS_SERVICE with platePosition 1-3.
- Light: ATTR_SET_SERVICE with lightSwitch. Sound: same with soundSwitch.
- Plans (second capture): WET_GRAIN_FEEDING_PLAN_SERVICE from the cloud with one
  dated run per entry: planId, executionDay, executionTime, plate,
  feedingDuration. What timezone executionTime is in is not clear from the
  capture (one run 19:53, the next two 21:53), so no Next Meal is built.
- Progress: WET_GRAIN_OUTPUT_EVENT with execStep GRAIN_THAW, GRAIN_START,
  OPEN_DOOR, CLOSE_DOOR, GRAIN_END (finished true); the cloud acks each step.
- HEARTBEAT carries temperature (degrees C).
Plans are edited in the Petlibro app (through the Cloud relay). Not built: ringerMode (NORMAL/SMART seen, meaning
unknown), volume, cleaning reset (not in either capture).
"""

DEVICE_TYPES = ["polar"]

MQTT_MODELS = {
    "polar": "PLAF109",
}

ALERT_MESSAGES = {}

DEFAULT_NOTIFICATIONS = {}

# planId the Petlibro app uses for feed-now; the stop command names it too
FEED_NOW_PLAN_ID = 666666666
FEED_NOW_DURATION = 240


def compute_alerts(state: dict, cfg: dict, online: bool) -> set:
    return set()


def track_intake(old_state: dict, new_state: dict, min_grams: float = 5) -> float | None:
    return None
