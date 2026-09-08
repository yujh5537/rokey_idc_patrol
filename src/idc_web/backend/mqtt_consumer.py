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


# PC4 FastAPI 서버가 Mosquitto에서 구독할 MQTT topic 목록이다.
# + 는 MQTT wildcard라서 robot5, robot11 등 어떤 robot_id도 받을 수 있다.
# 예: idc/robot5/battery, idc/robot11/battery 모두 idc/+/battery에 매칭된다.
# 두 번째 값은 QoS이다. battery/state는 QoS 1, pose는 실시간성을 위해 QoS 0을 사용한다.
TELEMETRY_SUBSCRIPTIONS = (
    ("idc/+/battery", 1),
    ("idc/+/mission/state", 1),
    ("idc/+/pose", 0),
)


def _parse_utc(value: object) -> datetime:
    # MQTT JSON의 received_at 문자열을 Python datetime으로 바꾼다.
    # 시간 정보가 없거나 timezone이 없으면 잘못된 메시지로 판단한다.
    if not isinstance(value, str) or not value:
        raise ValueError("received_at is required")

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)

    if parsed.tzinfo is None:
        raise ValueError("received_at must include timezone")

    return parsed.astimezone(timezone.utc)


def _finite_float(value: object, *, allow_none: bool = False) -> float | None:
    # DB에 NaN/Infinity 같은 비정상 숫자가 들어가지 않도록 검사한다.
    if value is None and allow_none:
        return None

    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite number")
    return parsed


def _robot_from_topic(topic: str) -> tuple[str, str]:
    # MQTT topic 문자열을 분해해서
    # 1) 어떤 로봇인지(robot_id)
    # 2) 어떤 종류의 telemetry인지
    # 를 알아낸다.
    # 예: idc/robot5/pose -> ("robot5", "pose")
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
        # 같은 telemetry가 재전송되거나 과거 데이터가 늦게 도착했을 때
        # DB를 이전 값으로 덮어쓰지 않기 위해 마지막 수신 시각을 기억한다.
        self._last_received_at: dict[tuple[str, str], datetime] = {}

        # paho-mqtt Client를 만든다.
        # 이 Client가 PC4의 Mosquitto broker에 연결되어 telemetry를 구독한다.
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="idc-pc4-telemetry-consumer",
        )
        # 연결 성공 시 실행할 함수와 메시지 수신 시 실행할 함수를 등록한다.
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        # broker 연결이 끊기면 1~30초 간격으로 재연결을 시도한다.
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    def start(self) -> None:
        # FastAPI 시작 시 MQTT broker에 비동기로 연결한다.
        self.client.connect_async(
            settings.mqtt_host,
            settings.mqtt_port,
            keepalive=60,
        )
        # MQTT 네트워크 처리를 별도 thread에서 계속 돌린다.
        self.client.loop_start()
        logger.info(
            "MQTT telemetry consumer started: %s:%s",
            settings.mqtt_host,
            settings.mqtt_port,
        )

    def stop(self) -> None:
        # FastAPI 종료 시 MQTT background loop와 broker 연결도 같이 정리한다.
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
        # broker 연결에 실패하면 subscribe를 시도하지 않는다.
        if getattr(reason_code, "is_failure", False):
            logger.error("MQTT connection failed: %s", reason_code)
            return

        # 연결이 성공하면 위에서 정의한 3종 telemetry topic을 구독한다.
        for topic, qos in TELEMETRY_SUBSCRIPTIONS:
            result, _ = client.subscribe(topic, qos=qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                logger.error("MQTT subscribe failed: topic=%s rc=%s", topic, result)
            else:
                logger.info("MQTT subscribed: %s qos=%s", topic, qos)

    def _on_message(self, client, userdata, message: mqtt.MQTTMessage) -> None:
        # Mosquitto에서 메시지가 하나 들어올 때마다 실행되는 callback이다.
        try:
            # topic에서 robot_id와 telemetry 종류를 알아낸다.
            robot_id, telemetry_type = _robot_from_topic(message.topic)
            # MQTT payload는 bytes이므로 UTF-8 문자열 -> JSON dict로 변환한다.
            payload = json.loads(message.payload.decode("utf-8"))

            # 계약에 맞지 않는 메시지는 DB에 넣지 않고 거부한다.
            if not isinstance(payload, dict):
                raise ValueError("payload must be a JSON object")
            if payload.get("schema_version") != "1.0":
                raise ValueError("unsupported schema_version")
            if payload.get("robot_id") != robot_id:
                raise ValueError("topic robot_id does not match payload robot_id")

            # 메시지가 PC3 bridge에 들어온 실제 시각을 읽는다.
            received_at = _parse_utc(payload.get("received_at"))
            key = (robot_id, telemetry_type)
            previous = self._last_received_at.get(key)

            # QoS 1 redelivery / battery 1 Hz replay can repeat the same source
            # sample. Avoid unnecessary DB writes and stale out-of-order updates.
            if previous is not None and received_at <= previous:
                return

            # 검증이 끝난 데이터만 PostgreSQL에 저장한다.
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
        # 한 번의 MQTT 메시지를 DB에 반영하는 함수다.
        with SessionLocal() as db:
            # robots 테이블에서 해당 robot_id를 찾는다.
            robot = db.get(Robot, robot_id)
            # 처음 보는 로봇이면 자동으로 새 row를 만든다.
            # 그래서 robot5/robot11을 코드에 각각 따로 하드코딩할 필요가 없다.
            if robot is None:
                robot = Robot(
                    id=robot_id,
                    name=robot_id,
                )
                db.add(robot)

            if telemetry_type == "battery":
                # BatteryState의 percentage는 0.0~1.0 값으로 저장한다.
                percentage = _finite_float(
                    payload.get("percentage"),
                    allow_none=True,
                )
                if percentage is not None and not 0.0 <= percentage <= 1.0:
                    raise ValueError("battery percentage must be within 0..1")
                robot.battery = percentage

            elif telemetry_type == "mission_state":
                # 로봇의 현재 mission state(PATROL, IDLE 등)를 저장한다.
                state = payload.get("state")
                if not isinstance(state, str) or not state:
                    raise ValueError("mission state is required")
                robot.state = state

            elif telemetry_type == "pose":
                # 지도 위 위치를 표시하기 위해 x, y, yaw를 저장한다.
                robot.x = _finite_float(payload.get("x"))
                robot.y = _finite_float(payload.get("y"))
                robot.yaw = _finite_float(payload.get("yaw"))

            else:
                raise ValueError(f"unsupported telemetry type: {telemetry_type}")

            # last_seen is the bridge source receive time, not the PC4 consume time.
            # Never move it backwards when different telemetry topics interleave.
            if robot.last_seen is None or received_at > robot.last_seen:
                robot.last_seen = received_at

            # 여기까지 문제가 없으면 실제 DB에 변경사항을 저장한다.
            db.commit()
