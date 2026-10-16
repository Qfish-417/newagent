from pathlib import Path
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    openai_api_key: str = Field(default="", validation_alias=AliasChoices("DEEPSEEK_API_KEY", "OPENAI_API_KEY"))
    openai_base_url: str = Field(default="https://api.deepseek.com", validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "OPENAI_BASE_URL"))
    model: str = Field(default="deepseek-chat", validation_alias=AliasChoices("DEEPSEEK_MODEL", "MODEL"))
    data_dir: Path = Path("data")
    max_rounds: int = 12
    search_api_key: str = ""

settings = Settings()
