import os
import subprocess


def compose_story_video(image_path: str, audio_path: str, output_path: str) -> str:
    """
    合成故事视频
    用途: 使用 FFmpeg 将静态图片与 TTS 音频合成为可播放的 MP4 视频
    """
    if not os.path.exists(image_path):
        raise RuntimeError(f"未找到待合成图片文件: {image_path}")
    if not os.path.exists(audio_path):
        raise RuntimeError(f"未找到待合成音频文件: {audio_path}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        image_path,
        "-i",
        audio_path,
        "-c:v",
        "libx264",
        "-tune",
        "stillimage",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        output_path,
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise RuntimeError("当前环境未安装 ffmpeg，可执行文件不可用。") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip() or error.stdout.strip() or "未知 FFmpeg 错误"
        raise RuntimeError(f"FFmpeg 合成失败: {message}") from error

    return output_path
