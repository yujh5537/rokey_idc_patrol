from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
from time import monotonic

import paho.mqtt.client as mqtt
from sqlalchemy import select

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Event, Rack, Robot, Zone


logger = logging.getLogger(__name__)


# PC4 subscribes to the frozen telemetry topics plus the merged REP-03
# SecurityEvent path used by INT-00.
MQTT_SUBSCRIPTIONS = (
    ("idc/+/battery", 1),
    ("idc/+/mission/state", 1),
    ("idc/+/pose", 0),
    ("idc/events/security", 1),
)

# Pose is published at 2 Hz. INT-00 freezes a 3-second freshness window:
# if no actual pose MQTT sample reaches this backend for 3 seconds, the Web UI
# must stop treating the DB's last stored coordinates as a live robot position.
POSE_FRESHNESS_SECONDS = 3.0
_pose_last_received_monotonic: dict[str, float] = {}


def pose_is_fresh(robot_id: str) -> bool:
    received = _pose_last_received_monotonic.get(robot_id)
    return received is not None and monotonic() - received <= POSE_FRESHNESS_SECONDS


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("received_at is required")

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("received_at must include timezone")
    return parsed.astimezone(timezone.utc)


def _finite_float(value: object, *, allow_none: bool = False) -> float | None:
    if value is None and allow_none:
        return None

    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite number")
    return parsed


def _robot_from_topic(topic: str) -> tuple[str, str]:
    parts = topic.split("/")

    if len(parts) == 3 and parts[0] == "idc" and parts[2] == "battery":
        return parts[1], "battery"

    if (
        len(parts) == 4
        and parts[0] == "idc"
        and parts[2] == "mission"
        and parts[3] == "state"
    ):
        return parts[1], "mission_state"

    if len(parts) == 3 and parts[0] == "idc" and parts[2] == "pose":
        return parts[1], "pose"

    raise ValueError(f"unsupported telemetry topic: {topic}")


def _event_source_time(payload: dict, received_at: datetime) -> datetime:
    stamp = payload.get("stamp")
    if not isinstance(stamp, dict):
        raise ValueError("event stamp must be an object")

    sec = stamp.get("sec")
    nanosec = stamp.get("nanosec")
    if not isinstance(sec, int) or sec < 0:
        raise ValueError("event stamp.sec must be a non-negative integer")
    if not isinstance(nanosec, int) or not 0 <= nanosec < 1_000_000_000:
        raise ValueError("event stamp.nanosec must be within 0..999999999")

    # Some synthetic ROS messages use the zero stamp. The bridge preserves
    # received_at across replay, so it is the deterministic fallback key.
    if sec == 0 and nanosec == 0:
        return received_at

    try:
        return datetime.fromtimestamp(
            sec + (nanosec / 1_000_000_000),
            tz=timezone.utc,
        )
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("event stamp is outside datetime range") from exc


def _validate_security_event(payload: dict) -> dict:
    if payload.get("type") != "E5":
        raise ValueError("current REP-03 SecurityEvent contract supports E5 only")

    robot_id = payload.get("robot_id")
    zone_id = payload.get("zone_id")
    rack_id = payload.get("rack_id")
    basis = payload.get("basis")
    frames = payload.get("frames")
    marker_checked = payload.get("marker_checked")
    position = payload.get("position")

    if not isinstance(robot_id, str) or not robot_id:
        raise ValueError("event robot_id is required")
    if not isinstance(zone_id, str) or not zone_id:
        raise ValueError("event zone_id is required")
    if not isinstance(rack_id, str) or not rack_id:
        raise ValueError("event rack_id is required")
    if basis not in {"yolo", "marker_missing"}:
        raise ValueError("event basis must be yolo or marker_missing")
    if not isinstance(frames, int) or frames < 0:
        raise ValueError("event frames must be a non-negative integer")
    if not isinstance(marker_checked, bool):
        raise ValueError("event marker_checked must be boolean")
    if not isinstance(position, dict):
        raise ValueError("event position must be an object")

    open_ratio = _finite_float(payload.get("open_ratio"), allow_none=True)
    if open_ratio is not None and not 0.0 <= open_ratio <= 1.0:
        raise ValueError("event open_ratio must be within 0..1")

    normalized = {
        "robot_id": robot_id,
        "zone_id": zone_id,
        "rack_id": rack_id,
        "basis": basis,
        "frames": frames,
        "marker_checked": marker_checked,
        "open_ratio": open_ratio,
        "x": _finite_float(position.get("x")),
        "y": _finite_float(position.get("y")),
        "z": _finite_float(position.get("z"), allow_none=True),
    }
    return normalized


class MqttTelemetryConsumer:
    """PC4 MQTT -> PostgreSQL consumer with SecurityEvent ingestion."""

    def __init__(self) -> None:
        self._last_received_at: dict[tuple[str, str], datetime] = {}

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="idc-pc4-telemetry-consumer",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def start(self) -> None:
        self.client.connect_async(
            settings.mqtt_host,
            settings.mqtt_port,
            keepalive=60,
        )
        self.client.loop_start()
        logger.info(
            "MQTT consumer started: %s:%s",
            settings.mqtt_host,
            settings.mqtt_port,
        )

    def stop(self) -> None:
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:
            logger.exception("MQTT consumer disconnect failed")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata,
        flags,
        reason_code,
        properties,
    ) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.error("MQTT connection failed: %s", reason_code)
            return

        for topic, qos in MQTT_SUBSCRIPTIONS:
            result, _ = client.subscribe(topic, qos=qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                logger.error("MQTT subscribe failed: topic=%s rc=%s", topic, result)
            else:
                logger.info("MQTT subscribed: %s qos=%s", topic, qos)

    def _on_message(self, client, userdata, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            if payload.get("schema_version") != "1.0":
                raise ValueError("unsupported schema_version")

            if message.topic == "idc/events/security":
                received_at = _parse_utc(payload.get("received_at"))
                self._store_security_event(payload, received_at)
                return

            robot_id, telemetry_type = _robot_from_topic(message.topic)
            if payload.get("robot_id") != robot_id:
                raise ValueError("topic robot_id does not match payload robot_id")

            received_at = _parse_utc(payload.get("received_at"))
            key = (robot_id, telemetry_type)
            previous = self._last_received_at.get(key)
            if previous is not None and received_at <= previous:
                return

            self._store_robot(robot_id, telemetry_type, payload, received_at)
            self._last_received_at[key] = received_at

        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            logger.warning(
                "Rejected MQTT message: topic=%s payload=%r",
                message.topic,
                message.payload[:512],
                exc_info=True,
            )
        except Exception:
            logger.exception("MQTT processing failed: %s", message.topic)

    def _store_robot(
        self,
        robot_id: str,
        telemetry_type: str,
        payload: dict,
        received_at: datetime,
    ) -> None:
        with SessionLocal() as db:
            robot = db.get(Robot, robot_id)
            if robot is None:
                robot = Robot(id=robot_id, name=robot_id)
                db.add(robot)

            if telemetry_type == "battery":
                percentage = _finite_float(
                    payload.get("percentage"),
                    allow_none=True,
                )
                if percentage is not None and not 0.0 <= percentage <= 1.0:
                    raise ValueError("battery percentage must be within 0..1")
                robot.battery = percentage

            elif telemetry_type == "mission_state":
                state = payload.get("state")
                if not isinstance(state, str) or not state:
                    raise ValueError("mission state is required")
                robot.state = state

            elif telemetry_type == "pose":
                robot.x = _finite_float(payload.get("x"))
                robot.y = _finite_float(payload.get("y"))
                robot.yaw = _finite_float(payload.get("yaw"))

            else:
                raise ValueError(f"unsupported telemetry type: {telemetry_type}")

            if robot.last_seen is None or received_at > robot.last_seen:
                robot.last_seen = received_at

            db.commit()

        # Freshness is deliberately process-local and is set only after an
        # actual pose MQTT sample has been validated and committed. A backend
        # restart therefore cannot resurrect an old DB coordinate as "live".
        if telemetry_type == "pose":
            _pose_last_received_monotonic[robot_id] = monotonic()

    def _store_security_event(self, payload: dict, received_at: datetime) -> None:
        event_data = _validate_security_event(payload)
        event_ts = _event_source_time(payload, received_at)

        with SessionLocal() as db:
            robot = db.get(Robot, event_data["robot_id"])
            if robot is None:
                robot = Robot(
                    id=event_data["robot_id"],
                    name=event_data["robot_id"],
                )
                db.add(robot)
                db.flush()

            if db.get(Zone, event_data["zone_id"]) is None:
                raise ValueError(
                    f"unknown zone_id {event_data['zone_id']}; MAP-02 seed is required"
                )
            if db.get(Rack, event_data["rack_id"]) is None:
                raise ValueError(
                    f"unknown rack_id {event_data['rack_id']}; MAP-02 seed is required"
                )

            # The bridge is at-least-once. Use the preserved ROS source stamp
            # (or preserved received_at for zero-stamp tests) as the DB dedup key.
            duplicate = db.scalar(
                select(Event.id).where(
                    Event.robot_id == event_data["robot_id"],
                    Event.type == "E5",
                    Event.rack_id == event_data["rack_id"],
                    Event.first_ts == event_ts,
                ).limit(1)
            )
            if duplicate is not None:
                return

            detail = {
                "basis": event_data["basis"],
                "open_ratio": event_data["open_ratio"],
                "frames": event_data["frames"],
                "marker_checked": event_data["marker_checked"],
                "stamp": payload.get("stamp"),
                "received_at": payload.get("received_at"),
            }

            # REP-03 SecurityEvent has no severity/status/evidence fields.
            # Keep those DB columns NULL rather than inventing application data.
            db.add(
                Event(
                    type="E5",
                    severity=None,
                    zone_id=event_data["zone_id"],
                    rack_id=event_data["rack_id"],
                    robot_id=event_data["robot_id"],
                    x=event_data["x"],
                    y=event_data["y"],
                    first_ts=event_ts,
                    last_ts=received_at,
                    status=None,
                    detail_json=json.dumps(
                        detail,
                        ensure_ascii=False,
                        allow_nan=False,
                        separators=(",", ":"),
                    ),
                )
            )
            db.commit()
