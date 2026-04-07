import asyncio
import os

import edge_tts

from app.settings import get_settings

async def _generate_speech_async(text: str, output_path: str, voice: str) -> None:
    """
    异步生成语音文件
    用途: 调用 edge-tts 将旁白文本保存为 MP3 文件
    """
    communicator = edge_tts.Communicate(text=text, voice=voice)
    await communicator.save(output_path)

def generate_speech_file(text: str, output_path: str, voice: str | None = None) -> str:
    """
    生成语音文件
    用途: 在 Celery 同步任务里安全调用 edge-tts，并返回输出文件路径
    """
    selected_voice = voice or get_settings().edge_tts_voice
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    asyncio.run(_generate_speech_async(text=text, output_path=output_path, voice=selected_voice))
    return output_path
