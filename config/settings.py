from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"
    secret_key: str = "change_me_in_production"

    llm_provider: str = "anthropic"  # "anthropic" or "openai"
    anthropic_api_key: str = ""
    anthropic_workspace_id: str = ""
    openai_api_key: str = ""
    primary_macro_model: str = "claude-3-5-haiku-20241022"
    fast_sentiment_model: str = "claude-3-5-haiku-20241022"

    # LLM Observability & Cost Tracking (Helicone / LangSmith)
    helicone_api_key: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "quantedge"
    macro_cache_ttl_hours: float = 24.0

    database_url: str = "postgresql://localhost:5432/quantedge"
    redis_url: str = "redis://localhost:6379/0"

    zmq_host: str = "127.0.0.1"
    zmq_req_port: int = 5555
    zmq_sub_port: int = 5556
    exness_account_type: str = "Demo"

    massive_api_key: str = ""
    polygon_api_key: str = ""
    newsapi_key: str = ""

    @property
    def effective_massive_api_key(self) -> str:
        return self.massive_api_key or self.polygon_api_key

    risk_per_trade_pct: float = Field(default=1.0, ge=0.1, le=5.0)
    max_portfolio_heat_pct: float = Field(default=5.0, ge=1.0, le=25.0)
    max_daily_drawdown_pct: float = Field(default=3.0, ge=0.5, le=20.0)
    enable_live_trading: bool = False

    # Bridge: "file" for Exness MT4 (default), "tcp" for MT5 socket EA
    bridge_transport: str = "file"
    bridge_file_dir: str = ""

    supported_assets: list[str] = ["XAUUSD", "USOIL", "BTCUSD", "EURUSD"]
    # Exness MT4 Market Watch names (m-suffix). Canonical names still used in strategies.
    broker_symbol_map: dict[str, str] = {
        "EURUSD": "EURUSDm",
        "XAUUSD": "XAUUSDm",
        "BTCUSD": "BTCUSDm",
        "USOIL": "USOILm",
    }
    signal_threshold: float = 65.0
    signal_interval_sec: float = Field(default=5.0, ge=1.0, le=300.0)
    intraday_max_trades_per_day: int = Field(default=20, ge=1, le=100)

    # Reinforcement Learning (RL) trade feedback
    rl_enabled: bool = True
    rl_learning_rate: float = Field(default=0.1, ge=0.01, le=1.0)
    rl_discount_factor: float = Field(default=0.95, ge=0.5, le=0.99)
    rl_exploration_rate: float = Field(default=0.1, ge=0.0, le=0.5)
    rl_memory_file: str = "data/rl_trade_memory.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
