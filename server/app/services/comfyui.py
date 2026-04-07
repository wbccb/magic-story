import json
import os
from typing import Any, Dict

import httpx


CONFIG_DIR = "./data/settings"
CONFIG_PATH = os.path.join(CONFIG_DIR, "comfy_config.json")

DEFAULT_COMFY_CONFIG = {
    "provider": "cloud",
    "label": "Comfy Cloud",
    "base_url": "",
    "api_key": "",
    "workflow_api": "/api/v1/workflows",
    "workflow_id": "",
    "local_endpoint": "http://127.0.0.1:8188",
    "client_id": "magic-story-poc",
}


def load_comfy_config() -> Dict[str, Any]:
    """
    读取图像服务配置
    用途: 返回 Comfy Cloud 或本地 ComfyUI 的当前配置，供前端页面展示
    """
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_COMFY_CONFIG.copy()

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        stored = json.load(file)

    config = DEFAULT_COMFY_CONFIG.copy()
    config.update(stored)
    return config


def save_comfy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    保存图像服务配置
    用途: 将前端提交的图像生成接入信息持久化到本地文件
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    merged = DEFAULT_COMFY_CONFIG.copy()
    merged.update(config)

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(merged, file, ensure_ascii=False, indent=2)

    return merged


def validate_comfy_config(config: Dict[str, Any]) -> None:
    """
    校验图像服务配置
    用途: 在保存或测试连接前确保前端填写了必要字段
    """
    provider = config.get("provider", "cloud")
    if provider == "cloud":
        if not config.get("base_url"):
            raise ValueError("Comfy Cloud 需要填写 Base URL")
        if not config.get("workflow_api"):
            raise ValueError("Comfy Cloud 需要填写 Workflow API 路径")
    elif provider == "local":
        if not config.get("local_endpoint"):
            raise ValueError("本地 ComfyUI 需要填写服务地址")
    else:
        raise ValueError("暂不支持的图像服务类型")


def test_comfy_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    测试图像服务连接
    用途: 帮助前端确认当前配置是否至少满足基础连通性或参数完整性
    """
    validate_comfy_config(config)
    provider = config.get("provider", "cloud")

    if provider == "cloud":
        return {
            "ok": True,
            "message": "Comfy Cloud 配置已保存，可在后续接入工作流调用时直接复用。"
        }

    endpoint = config["local_endpoint"].rstrip("/")
    response = httpx.get(f"{endpoint}/system_stats", timeout=5.0)
    response.raise_for_status()

    return {
        "ok": True,
        "message": "本地 ComfyUI 连接成功。",
        "details": response.json()
    }
