from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    应用配置
    用途: 从 .env 和环境变量中统一读取后端服务、模型和媒体路径配置
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///./data/magic_story.db"
    upload_dir: str = "./data/uploads"
    output_dir: str = "./data/outputs"

    llm_provider: str = "mock"
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = "local-not-required"
    llm_model: str = "qwen3:latest"
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 60.0

    asr_provider: str = "faster_whisper"
    asr_model_size: str = "small"
    asr_device: str = "auto"
    asr_compute_type: str = "auto"

    edge_tts_voice: str = "zh-CN-XiaoxiaoNeural"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """
    获取应用配置单例
    用途: 避免在一次进程生命周期内重复解析 .env 文件
    """
    return AppSettings()
