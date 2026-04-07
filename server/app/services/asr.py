from functools import lru_cache
from typing import Optional

from app.settings import get_settings

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover - 运行环境未安装依赖时给出清晰报错
    WhisperModel = None


def _resolve_device(device: str) -> str:
    """
    解析 ASR 设备配置
    用途: 将 auto 配置转换为 faster-whisper 可接受的实际设备名称
    """
    return "cpu" if device == "auto" else device


def _resolve_compute_type(compute_type: str, device: str) -> str:
    """
    解析 ASR 精度配置
    用途: 为 CPU 默认使用 int8，避免未显式配置时的兼容性问题
    """
    if compute_type != "auto":
        return compute_type
    return "int8" if device == "cpu" else "float16"


@lru_cache(maxsize=1)
def get_whisper_model() -> WhisperModel:
    """
    获取 Whisper 模型单例
    用途: 让 Celery Worker 复用同一个 faster-whisper 模型实例，降低重复加载开销
    """
    if WhisperModel is None:
        raise RuntimeError("当前环境未安装 faster-whisper，请先安装依赖。")

    settings = get_settings()
    device = _resolve_device(settings.asr_device)
    compute_type = _resolve_compute_type(settings.asr_compute_type, device)
    return WhisperModel(settings.asr_model_size, device=device, compute_type=compute_type)


def transcribe_audio(audio_path: str, language: str = "zh") -> str:
    """
    转写音频内容
    用途: 使用 faster-whisper 将用户录音转写为中文文本
    """
    settings = get_settings()
    if settings.asr_provider != "faster_whisper":
        raise RuntimeError(f"暂不支持的 ASR Provider: {settings.asr_provider}")

    model = get_whisper_model()
    segments, _ = model.transcribe(audio_path, language=language, vad_filter=True)
    text = "".join(segment.text.strip() for segment in segments).strip()
    if not text:
        raise RuntimeError("ASR 未识别出有效文本，请检查录音内容或模型配置。")
    return text
