import logging
import time

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    SCHEDULER_INTERVAL_HOURS: int = 4
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(env_file="deploy/.env", env_file_encoding="utf-8")


settings = Settings()


class _Formatter(logging.Formatter):
    converter = time.gmtime
    default_msec_format = "%s.%03d UTC"


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=settings.LOG_LEVEL, handlers=[handler])
