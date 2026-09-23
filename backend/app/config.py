"""全局配置：从 backend/.env 读取，未配置的项使用默认值"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（所有相对路径以此为基准，避免启动目录不同导致找不到文件）
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 数据库
    DATABASE_URL: str = "sqlite:///./fmzh.db"

    # JWT
    SECRET_KEY: str = "dev-secret-key-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 天

    # 文件上传
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 20

    # 大模型：LLM_MOCK=true 时走内置 Mock，不需要 API Key
    LLM_MOCK: bool = True
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"


settings = Settings()

# 上传目录的绝对路径
UPLOAD_DIR = BASE_DIR / settings.UPLOAD_DIR
