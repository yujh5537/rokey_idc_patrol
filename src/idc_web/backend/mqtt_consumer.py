from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math

import paho.mqtt.client as mqtt

from backend.config import settings
from backend.database import SessionLocal
from backend.models import Robot


logger = logging.getLogger(__name__)


TELEMETRY_SUBSCRIPTIONS = (
    ("idc/+/battery", 1),
    ("idc/+/mission/state", 1),
    ("idc/+/pose", 0),
)


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


class MqttTelemetryConsumer:
    """PC4 MQTT -> PostgreSQL telemetry consumer.

    This module intentionally has no ROS 2 dependency. It consumes only the
    FROZEN MQTT Interface v1 payloads produced by PC3 idc_bridge.
    """

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
            "MQTT telemetry consumer started: %s:%s",
            settings.mqtt_host,
            settings.mqtt_port,
        )

    def stop(self) -> None:
        self.client.loop_stop()
        try:
            self.client.disconnect()
        except Exception:
            logger.exception("MQTT telemetry consumer disconnect failed")

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

        for topic, qos in TELEMETRY_SUBSCRIPTIONS:
            result, _ = client.subscribe(topic, qos=qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                logger.error("MQTT subscribe failed: topic=%s rc=%s", topic, result)
            else:
                logger.info("MQTT subscribed: %s qos=%s", topic, qos)

    def _on_message(self, client, userdata, message: mqtt.MQTTMessage) -> None:
        try:
            robot_id, telemetry_type = _robot_from_topic(message.topic)
            payload = json.loads(message.payload.decode("utf-8"))

            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            if payload.get("schema_version") != "1.0":
                raise ValueError("unsupported schema_version")
            if payload.get("robot_id") != robot_id:
                raise ValueError("topic robot_id does not match payload robot_id")

            received_at = _parse_utc(payload.get("received_at"))
            key = (robot_id, telemetry_type)
            previous = self._last_received_at.get(key)

            # QoS 1 redelivery / battery 1 Hz replay can repeat the same source
            # sample. Avoid unnecessary DB writes and stale out-of-order updates.
            if previous is not None and received_at <= previous:
                return

            self._store(robot_id, telemetry_type, payload, received_at)
            self._last_received_at[key] = received_at

        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            logger.warning(
                "Rejected MQTT telemetry: topic=%s payload=%r",
                message.topic,
                message.payload[:512],
                exc_info=True,
            )
        except Exception:
            logger.exception("MQTT telemetry processing failed: %s", message.topic)

    def _store(
        self,
        robot_id: str,
        telemetry_type: str,
        payload: dict,
        received_at: datetime,
    ) -> None:
        with SessionLocal() as db:
            robot = db.get(Robot, robot_id)
            if robot is None:
                robot = Robot(
                    id=robot_id,
                    name=robot_id,
                )
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

            # last_seen is the bridge source receive time, not the PC4 consume time.
            # Never move it backwards when different telemetry topics interleave.
            if robot.last_seen is None or received_at > robot.last_seen:
                robot.last_seen = received_at

            db.commit()
