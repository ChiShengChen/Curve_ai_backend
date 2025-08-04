from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = Field("sqlite:///curve.db", env="DATABASE_URL")
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    schedule_frequency: int = Field(60 * 60 * 8, env="SCHEDULE_FREQUENCY")
    api_title: str = Field("Curve APY API", env="API_TITLE")


settings = Settings()
