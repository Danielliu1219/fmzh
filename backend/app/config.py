"""全局配置：从 backend/.env 读取，未配置的项使用默认值"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

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
    MAX_UPLOAD_SIZE_MB: int = Field(20, ge=1, le=20)
    USER_STORAGE_LIMIT_MB: int = Field(256, ge=1)
    LLM_DAILY_LIMIT: int = Field(50, ge=1)
    BACKUP_ENABLED: bool = True
    BACKUP_INTERVAL_HOURS: float = Field(24, gt=0, le=24)
    BACKUP_DIR: str = ''
    BACKUP_KEY_FILE: str = ''

    # 大模型：LLM_MOCK=true 时走内置 Mock，不需要 API Key
    LLM_MOCK: bool = True
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # 思考模式保留；分析需要容纳思考与完整JSON，按实际生成量计费。
    LLM_ANALYSIS_MAX_TOKENS: int = Field(65536, ge=4000, le=131072)
    LLM_ANALYSIS_TIMEOUT_SECONDS: int = Field(420, ge=60, le=900)


settings = Settings()

# 上传目录的绝对路径
UPLOAD_DIR = BASE_DIR / settings.UPLOAD_DIR
