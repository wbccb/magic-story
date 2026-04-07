from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import json
import shutil
import os
import uuid

from app.models import SessionLocal, Story, RenderCost
from app.settings import get_settings
from app.tasks import process_story_task
from app.services.comfyui import (
    get_workflow_template_status,
    load_comfy_config,
    save_comfy_config,
    save_workflow_template,
    test_comfy_connection,
    validate_comfy_config,
)

app = FastAPI(title="MagicStory POC API")
settings = get_settings()

# 配置CORS，允许前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = settings.upload_dir
OUTPUT_DIR = settings.output_dir
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
app.mount("/media", StaticFiles(directory="./data"), name="media")


class ComfyConfigPayload(BaseModel):
    """
    图像服务配置载体
    用途: 接收前端提交的 Comfy Cloud 或本地 ComfyUI 配置
    """
    provider: str
    label: str = "本地 ComfyUI"
    base_url: str = ""
    api_key: str = ""
    workflow_api: str = "/api/prompt"
    workflow_id: str = ""
    local_endpoint: str = "http://127.0.0.1:8188"
    client_id: str = "magic-story-poc"
    positive_prompt: str = "children's picture book illustration, clay art, soft lighting, colorful scene, {narration}"
    negative_prompt: str = "blurry, low quality, distorted, extra limbs, text, watermark"


class RuntimeConfigResponse(BaseModel):
    """
    运行时配置响应
    用途: 让前端或调试工具查看当前启用的 ASR 与 LLM 配置概况
    """
    llm_provider: str
    llm_base_url: str
    llm_model: str
    asr_provider: str
    asr_model_size: str
    edge_tts_voice: str

@app.get("/health")
def health_check():
    """
    健康检查接口
    用途: 验证服务是否正常运行
    """
    return {"status": "ok"}


@app.get("/api/settings/runtime", response_model=RuntimeConfigResponse)
def get_runtime_settings():
    """
    获取运行时模型配置
    用途: 暴露后端当前生效的 .env 关键配置，便于联调本地 LLM 和 ASR
    """
    current = get_settings()
    return RuntimeConfigResponse(
        llm_provider=current.llm_provider,
        llm_base_url=current.llm_base_url,
        llm_model=current.llm_model,
        asr_provider=current.asr_provider,
        asr_model_size=current.asr_model_size,
        edge_tts_voice=current.edge_tts_voice,
    )

@app.post("/api/upload")
async def upload_files(image: UploadFile = File(...), audio: UploadFile = File(...)):
    """
    上传涂鸦与录音接口
    用途: 接收前端传来的图片和音频文件，并初始化数据库记录
    """
    story_id = str(uuid.uuid4())
    
    # 保存图片
    image_ext = image.filename.split('.')[-1] if '.' in image.filename else 'png'
    image_path = os.path.join(UPLOAD_DIR, f"{story_id}.{image_ext}")
    with open(image_path, "wb") as f:
        shutil.copyfileobj(image.file, f)
        
    # 保存音频
    audio_ext = audio.filename.split('.')[-1] if '.' in audio.filename else 'webm'
    audio_path = os.path.join(UPLOAD_DIR, f"{story_id}.{audio_ext}")
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio.file, f)

    # 写入数据库
    db = SessionLocal()
    try:
        new_story = Story(
            id=story_id,
            status="uploaded",
            original_image_path=image_path,
            original_audio_path=audio_path
        )
        db.add(new_story)
        db.commit()
    finally:
        db.close()

    return {"story_id": story_id}

@app.post("/api/render/{story_id}")
async def trigger_render(story_id: str):
    """
    触发渲染接口
    用途: 接收到请求后，启动后台Celery任务处理AI管线
    """
    db = SessionLocal()
    story = db.query(Story).filter(Story.id == story_id).first()
    db.close()
    
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
        
    # 异步触发Celery任务
    task = process_story_task.delay(story_id)
    return {"task_id": task.id, "message": "Rendering started"}

@app.get("/api/status/{story_id}")
def get_status(story_id: str):
    """
    查询进度接口
    用途: 前端轮询此接口获取渲染进度与状态
    """
    db = SessionLocal()
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
            
        return {
            "status": story.status,
            "progress_pct": story.progress_pct,
            "current_step": story.current_step,
            "step_message": get_step_message_zh(story.current_step),
            "error_message": story.error_message
        }
    finally:
        db.close()

@app.get("/api/settings/comfy")
def get_comfy_settings():
    """
    获取图像服务配置
    用途: 让前端页面回显当前选择的 Comfy Cloud 或本地 ComfyUI 设置
    """
    return load_comfy_config()


@app.get("/api/settings/comfy/workflow")
def get_comfy_workflow_status():
    """
    获取工作流模板状态
    用途: 让前端知道是否已经上传真实 ComfyUI 重绘所需的 workflow 模板
    """
    return get_workflow_template_status()


@app.post("/api/settings/comfy/workflow")
async def upload_comfy_workflow(file: UploadFile = File(...)):
    """
    上传工作流模板
    用途: 保存 ComfyUI API workflow JSON 模板，供图片重绘阶段动态注入占位符
    """
    if not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="请上传 ComfyUI 导出的 API 格式 JSON 文件。")
    content = await file.read()
    try:
        return save_workflow_template(content)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="上传的 workflow 不是合法 JSON。") from error


@app.put("/api/settings/comfy")
def update_comfy_settings(payload: ComfyConfigPayload):
    """
    保存图像服务配置
    用途: 将前端填写的配置写入本地，供后续图片生成服务复用
    """
    config = payload.model_dump()
    try:
        validate_comfy_config(config)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return save_comfy_config(config)


@app.post("/api/settings/comfy/test")
def verify_comfy_settings(payload: ComfyConfigPayload):
    """
    测试图像服务配置
    用途: 提前验证当前配置是否可用于接入 Comfy Cloud 或本地 ComfyUI
    """
    try:
        return test_comfy_connection(payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"连接测试失败: {error}") from error


@app.get("/api/result/{story_id}")
def get_result(story_id: str):
    """
    获取结果接口
    用途: 渲染完成后，返回最终视频URL和成本明细
    """
    db = SessionLocal()
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if not story:
            raise HTTPException(status_code=404, detail="Story not found")
            
        costs = db.query(RenderCost).filter(RenderCost.story_id == story_id).all()
        total_cost = sum(c.cost_usd for c in costs)
        tts_audio_path = os.path.join(OUTPUT_DIR, f"{story_id}_narration.mp3")
        tts_audio_url = None
        if os.path.exists(tts_audio_path):
            tts_audio_url = f"/media/outputs/{story_id}_narration.mp3"
        
        return {
            "final_video_url": story.final_video_path,
            "redrawn_image_url": story.redrawn_image_path,
            "narration": story.corrected_narration,
            "tts_audio_url": tts_audio_url,
            "cost_breakdown": [{"step": c.step_name, "cost": c.cost_usd} for c in costs],
            "total_cost": total_cost
        }
    finally:
        db.close()

def get_step_message_zh(step: str) -> str:
    """
    转换状态为中文提示
    用途: 映射内部步骤名为用户友好的中文文案
    """
    mapping = {
        "asr": "正在聆听你的故事...",
        "llm_route": "正在理解画面...",
        "comfyui": "正在施展魔法...",
        "video_gen": "正在拍摄动画片...",
        "tts": "正在请配音员准备...",
        "ffmpeg": "最后润色中...",
        "completed": "魔法完成！"
    }
    return mapping.get(step, "请稍候...")
