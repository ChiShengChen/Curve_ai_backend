from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = Field("sqlite:///curve.db", env="DATABASE_URL")
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    schedule_frequency: int = Field(60 * 60 * 8, env="SCHEDULE_FREQUENCY")
    api_title: str = Field("Curve APY API", env="API_TITLE")
    access_token_expire_minutes: int = Field(15, env="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_minutes: int = Field(60 * 24 * 7, env="REFRESH_TOKEN_EXPIRE_MINUTES")
    jwt_secret: str = Field("secret", env="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")


settings = Settings()
