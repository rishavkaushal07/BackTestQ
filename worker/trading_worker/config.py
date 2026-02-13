from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://backtestq:backtestq@localhost:5432/trading_sim"
    POLL_INTERVAL_SECS: float = 1.0
    WORKER_NAME: str = "worker-1"

settings = Settings()
