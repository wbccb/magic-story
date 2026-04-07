import copy
import json
import os
import time
import uuid
from typing import Any, Dict, Iterable, Tuple

import httpx


CONFIG_DIR = "./data/settings"
CONFIG_PATH = os.path.join(CONFIG_DIR, "comfy_config.json")
WORKFLOW_TEMPLATE_PATH = os.path.join(CONFIG_DIR, "comfy_workflow_api.json")

DEFAULT_COMFY_CONFIG = {
    "provider": "local",
    "label": "本地 ComfyUI",
    "base_url": "",
    "api_key": "",
    "workflow_api": "/api/prompt",
    "workflow_id": "",
    "local_endpoint": "http://127.0.0.1:8188",
    "client_id": "magic-story-poc",
    "positive_prompt": "children's picture book illustration, clay art, soft lighting, colorful scene, {narration}",
    "negative_prompt": "blurry, low quality, distorted, extra limbs, text, watermark",
}


def workflow_template_exists() -> bool:
    """
    检查工作流模板是否存在
    用途: 判断当前是否已经上传了可供真实图片重绘使用的 ComfyUI API 工作流
    """
    return os.path.exists(WORKFLOW_TEMPLATE_PATH)


def load_workflow_template() -> Dict[str, Any]:
    """
    读取工作流模板
    用途: 加载用户上传的 ComfyUI API 格式 workflow JSON 模板
    """
    if not workflow_template_exists():
        raise ValueError("尚未上传 ComfyUI workflow 模板，请先在页面配置区上传 API 格式 JSON。")
    with open(WORKFLOW_TEMPLATE_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def save_workflow_template(content: bytes) -> Dict[str, Any]:
    """
    保存工作流模板
    用途: 将前端上传的 ComfyUI API workflow JSON 持久化到本地
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    payload = json.loads(content.decode("utf-8"))
    with open(WORKFLOW_TEMPLATE_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    return get_workflow_template_status()


def get_workflow_template_status() -> Dict[str, Any]:
    """
    获取工作流模板状态
    用途: 给前端展示当前是否已经上传 workflow 模板以及模板路径
    """
    return {
        "template_ready": workflow_template_exists(),
        "template_path": WORKFLOW_TEMPLATE_PATH if workflow_template_exists() else None,
        "placeholders": [
            "__INPUT_IMAGE__",
            "__POSITIVE_PROMPT__",
            "__NEGATIVE_PROMPT__",
            "__OUTPUT_PREFIX__",
        ],
    }


def load_comfy_config() -> Dict[str, Any]:
    """
    读取图像服务配置
    用途: 返回 Comfy Cloud 或本地 ComfyUI 的当前配置，供前端页面展示
    """
    if not os.path.exists(CONFIG_PATH):
        config = DEFAULT_COMFY_CONFIG.copy()
    else:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            stored = json.load(file)
        config = DEFAULT_COMFY_CONFIG.copy()
        config.update(stored)

    config.update(get_workflow_template_status())
    return config


def save_comfy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    保存图像服务配置
    用途: 将前端提交的图像生成接入信息持久化到本地文件
    """
    os.makedirs(CONFIG_DIR, exist_ok=True)
    merged = DEFAULT_COMFY_CONFIG.copy()
    merged.update(config)
    for transient_key in ["template_ready", "template_path", "placeholders"]:
        merged.pop(transient_key, None)

    with open(CONFIG_PATH, "w", encoding="utf-8") as file:
        json.dump(merged, file, ensure_ascii=False, indent=2)

    return load_comfy_config()


def validate_comfy_config(config: Dict[str, Any]) -> None:
    """
    校验图像服务配置
    用途: 在保存或测试连接前确保前端填写了必要字段
    """
    provider = config.get("provider", "local")
    if provider == "cloud":
        if not config.get("base_url"):
            raise ValueError("Comfy Cloud 需要填写 Base URL")
        if not config.get("workflow_api"):
            raise ValueError("Comfy Cloud 需要填写提交接口路径")
    elif provider == "local":
        if not config.get("local_endpoint"):
            raise ValueError("本地 ComfyUI 需要填写服务地址")
    else:
        raise ValueError("暂不支持的图像服务类型")


def _get_base_and_path(config: Dict[str, Any], endpoint_key: str, local_fallback: str, cloud_fallback: str) -> Tuple[str, str]:
    """
    获取 API 基地址与路径
    用途: 根据 provider 自动推断本地或云端兼容接口的访问路径
    """
    provider = config.get("provider", "local")
    if provider == "cloud":
        base_url = config["base_url"].rstrip("/")
        path = config.get(endpoint_key) or cloud_fallback
        return base_url, path
    base_url = config["local_endpoint"].rstrip("/")
    return base_url, local_fallback


def _build_headers(config: Dict[str, Any]) -> Dict[str, str]:
    """
    构造请求头
    用途: 为 Comfy Cloud 场景附加鉴权信息，同时兼容本地 ComfyUI 空鉴权
    """
    headers: Dict[str, str] = {}
    if config.get("provider") == "cloud" and config.get("api_key"):
        headers["Authorization"] = f"Bearer {config['api_key']}"
    return headers


def _replace_placeholders(value: Any, replacements: Dict[str, str]) -> Any:
    """
    递归替换占位符
    用途: 将 workflow JSON 中的输入图、提示词和输出前缀占位符替换为运行时真实值
    """
    if isinstance(value, dict):
        return {key: _replace_placeholders(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_placeholders(item, replacements) for item in value]
    if isinstance(value, str):
        rendered = value
        for placeholder, actual in replacements.items():
            rendered = rendered.replace(placeholder, actual)
        return rendered
    return value


def _iter_output_images(outputs: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """
    遍历输出图片
    用途: 从 ComfyUI history 结构里提取所有产出的图片条目
    """
    for node_output in outputs.values():
        for image in node_output.get("images", []):
            yield image


def _upload_source_image(client: httpx.Client, config: Dict[str, Any], image_path: str, story_id: str) -> str:
    """
    上传源图片到 ComfyUI
    用途: 将用户原始涂鸦图片上传到工作流可访问的输入区
    """
    base_url, upload_path = _get_base_and_path(config, "upload_api", "/upload/image", "/api/upload/image")
    remote_name = f"{story_id}_{uuid.uuid4().hex}.png"
    with open(image_path, "rb") as file:
        files = {"image": (remote_name, file, "image/png")}
        response = client.post(f"{base_url}{upload_path}", files=files, data={"overwrite": "true"})
    response.raise_for_status()
    payload = response.json()
    return payload.get("name") or remote_name


def _submit_prompt(client: httpx.Client, config: Dict[str, Any], workflow: Dict[str, Any]) -> str:
    """
    提交工作流
    用途: 向 ComfyUI 提交处理后的 workflow JSON，拿到 prompt_id 供后续轮询
    """
    base_url, prompt_path = _get_base_and_path(config, "workflow_api", "/prompt", "/api/prompt")
    response = client.post(
        f"{base_url}{prompt_path}",
        json={"prompt": workflow, "client_id": config.get("client_id", "magic-story-poc")},
    )
    response.raise_for_status()
    payload = response.json()
    prompt_id = payload.get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI 未返回 prompt_id，无法继续轮询结果。")
    return prompt_id


def _poll_history(client: httpx.Client, config: Dict[str, Any], prompt_id: str) -> Dict[str, Any]:
    """
    轮询工作流结果
    用途: 等待 ComfyUI 任务完成，并取回 history 中的输出结构
    """
    base_url, history_root = _get_base_and_path(config, "history_api", "/history", "/api/history")
    for _ in range(90):
        response = client.get(f"{base_url}{history_root}/{prompt_id}")
        response.raise_for_status()
        payload = response.json()
        if prompt_id in payload:
            return payload[prompt_id]
        time.sleep(2)
    raise RuntimeError("等待 ComfyUI 输出超时，请检查工作流是否正常执行。")


def _download_output_image(client: httpx.Client, config: Dict[str, Any], image_info: Dict[str, Any], output_path: str) -> str:
    """
    下载输出图片
    用途: 将 ComfyUI 生成的结果图保存到本地，供后续 FFmpeg 合成使用
    """
    base_url, view_path = _get_base_and_path(config, "view_api", "/view", "/api/view")
    params = {
        "filename": image_info["filename"],
        "subfolder": image_info.get("subfolder", ""),
        "type": image_info.get("type", "output"),
    }
    response = client.get(f"{base_url}{view_path}", params=params)
    response.raise_for_status()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as file:
        file.write(response.content)
    return output_path


def build_runtime_workflow(config: Dict[str, Any], source_image_name: str, narration: str, output_prefix: str) -> Dict[str, Any]:
    """
    构造运行时工作流
    用途: 将用户上传的模板 workflow 与当前故事的输入图和提示词拼装成可执行 JSON
    """
    template = load_workflow_template()
    positive_prompt = (config.get("positive_prompt") or DEFAULT_COMFY_CONFIG["positive_prompt"]).format(narration=narration)
    negative_prompt = (config.get("negative_prompt") or DEFAULT_COMFY_CONFIG["negative_prompt"]).format(narration=narration)
    replacements = {
        "__INPUT_IMAGE__": source_image_name,
        "__POSITIVE_PROMPT__": positive_prompt,
        "__NEGATIVE_PROMPT__": negative_prompt,
        "__OUTPUT_PREFIX__": output_prefix,
    }
    return _replace_placeholders(copy.deepcopy(template), replacements)


def run_image_redraw(story_id: str, image_path: str, narration: str, output_path: str) -> str | None:
    """
    执行图片重绘
    用途: 在配置完整且 workflow 模板存在时调用真实 ComfyUI，生成重绘图并返回本地路径
    """
    config = load_comfy_config()
    validate_comfy_config(config)
    if not workflow_template_exists():
        return None

    headers = _build_headers(config)
    with httpx.Client(headers=headers, timeout=120.0) as client:
        source_image_name = _upload_source_image(client, config, image_path, story_id)
        workflow = build_runtime_workflow(
            config=config,
            source_image_name=source_image_name,
            narration=narration,
            output_prefix=f"magic_story_{story_id}",
        )
        prompt_id = _submit_prompt(client, config, workflow)
        history = _poll_history(client, config, prompt_id)
        outputs = history.get("outputs", {})
        first_image = next(_iter_output_images(outputs), None)
        if not first_image:
            raise RuntimeError("ComfyUI 未产出图片，请检查 workflow 的输出节点。")
        return _download_output_image(client, config, first_image, output_path)


def test_comfy_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    测试图像服务连接
    用途: 帮助前端确认当前配置是否至少满足基础连通性或参数完整性
    """
    validate_comfy_config(config)
    provider = config.get("provider", "local")
    headers = _build_headers(config)
    with httpx.Client(headers=headers, timeout=5.0) as client:
        if provider == "cloud":
            base_url = config["base_url"].rstrip("/")
            response = client.get(base_url)
            response.raise_for_status()
            return {
                "ok": True,
                "message": "Comfy Cloud 连接成功，请继续上传 workflow 模板后再执行真实重绘。",
            }

        endpoint = config["local_endpoint"].rstrip("/")
        response = client.get(f"{endpoint}/system_stats")
        response.raise_for_status()
        return {
            "ok": True,
            "message": "本地 ComfyUI 连接成功。",
            "details": response.json(),
        }
