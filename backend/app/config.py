import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Сервисы расчетного ядра
    ipr_service_url: str = os.getenv("IPR_SERVICE_URL", "http://localhost:8003")
    vlp_service_url: str = os.getenv("VLP_SERVICE_URL", "http://localhost:8002")
    nodal_service_url: str = os.getenv("NODAL_SERVICE_URL", "http://localhost:8004")

    # Конфигурация ИИ (Роль 3)
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-flash"
    llm_api_key: str = ""
    llm_timeout_sec: int = 30
    ai_max_steps: int = 6

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_api_key.strip())


settings = Settings()
