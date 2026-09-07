from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_FILE)


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "").strip()

        self.mqtt_host = os.getenv(
            "MQTT_HOST",
            "127.0.0.1",
        ).strip()

        self.mqtt_port = int(
            os.getenv(
                "MQTT_PORT",
                "1883",
            )
        )

        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is not configured in .env"
            )


settings = Settings()
