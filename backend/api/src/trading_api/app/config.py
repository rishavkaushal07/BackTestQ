from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/trading_sim"
    DEFAULT_STARTING_CASH_PAISE: int = 100_000_000  # ₹10,00,000
    DEFAULT_FEE_BPS: int = 1
    DEFAULT_SLIPPAGE_BPS: int = 2

settings = Settings()
