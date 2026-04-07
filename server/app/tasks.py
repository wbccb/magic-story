# 异步任务定义 (Celery)
from celery import Celery
import os
import time
from app.models import SessionLocal, Story, RenderCost
from app.settings import get_settings
from app.services.asr import transcribe_audio
from app.services.llm import analyze_story_text
from app.services.tts import generate_speech_file
from app.services.video import compose_story_video

settings = get_settings()
REDIS_URL = settings.redis_url
OUTPUT_DIR = settings.output_dir
celery_app = Celery("tasks", broker=REDIS_URL)

def update_story_progress(story_id: str, step: str, progress: int, error: str = None):
    """
    更新故事处理进度
    用途: 同步任务执行状态到数据库，供前端轮询
    """
    db = SessionLocal()
    try:
        story = db.query(Story).filter(Story.id == story_id).first()
        if story:
            story.current_step = step
            story.progress_pct = progress
            if error:
                story.status = "failed"
                story.error_message = error
            elif progress == 100:
                story.status = "completed"
            else:
                story.status = "rendering"
            db.commit()
    finally:
        db.close()

def record_cost(story_id: str, step_name: str, cost: float, duration: int):
    """
    记录每个步骤的耗时和成本
    用途: 满足POC的成本追踪需求
    """
    db = SessionLocal()
    try:
        cost_record = RenderCost(story_id=story_id, step_name=step_name, cost_usd=cost, duration_ms=duration)
        db.add(cost_record)
        db.commit()
    finally:
        db.close()

@celery_app.task
def process_story_task(story_id: str):
    """
    完整的故事处理管线
    用途: 异步执行 ASR -> LLM -> ComfyUI -> Video Gen -> TTS -> FFmpeg
    """
    try:
        # Step 1: ASR
        start_time = time.time()
        update_story_progress(story_id, "asr", 10)
        db = SessionLocal()
        try:
            story = db.query(Story).filter(Story.id == story_id).first()
            if not story or not story.original_audio_path:
                raise RuntimeError("未找到待转写的音频文件。")
            transcribed_text = transcribe_audio(story.original_audio_path)
            story.transcribed_text = transcribed_text
            db.commit()
        finally:
            db.close()
        record_cost(story_id, "asr", 0.006, int((time.time() - start_time) * 1000))

        # Step 2: LLM Route
        start_time = time.time()
        update_story_progress(story_id, "llm_route", 20)
        db = SessionLocal()
        try:
            story = db.query(Story).filter(Story.id == story_id).first()
            if not story:
                raise RuntimeError("未找到故事记录。")
            if not story.transcribed_text:
                raise RuntimeError("ASR 未产出可用文本，无法继续执行 LLM 路由。")

            plan = analyze_story_text(story.transcribed_text)
            story.corrected_narration = plan["corrected_narration"]
            story.complexity_score = plan["complexity_score"]
            story.render_route = plan["render_route"]
            db.commit()
            route = story.render_route
        finally:
            db.close()
        record_cost(story_id, "llm_route", 0.003, int((time.time() - start_time) * 1000))

        # Step 3: ComfyUI (Image Redraw)
        start_time = time.time()
        update_story_progress(story_id, "comfyui", 40)
        time.sleep(5) # Mock ComfyUI delay
        record_cost(story_id, "comfyui", 0.03, int((time.time() - start_time) * 1000))

        # Step 4: Video Generation
        start_time = time.time()
        update_story_progress(story_id, "video_gen", 70)
        time.sleep(8 if route == "i2v_api" else 3)
        video_cost = 0.15 if route == "i2v_api" else 0.005
        record_cost(story_id, route, video_cost, int((time.time() - start_time) * 1000))

        # Step 5: TTS
        start_time = time.time()
        update_story_progress(story_id, "tts", 85)
        narration_text = "魔法修正后的旁白：这是一个美丽的故事"
        db = SessionLocal()
        try:
            story = db.query(Story).filter(Story.id == story_id).first()
            if story and story.corrected_narration:
                narration_text = story.corrected_narration
        finally:
            db.close()

        output_path = os.path.join(OUTPUT_DIR, f"{story_id}_narration.mp3")
        generate_speech_file(text=narration_text, output_path=output_path)
        record_cost(story_id, "tts", 0.0, int((time.time() - start_time) * 1000))

        # Step 6: FFmpeg Compose
        start_time = time.time()
        update_story_progress(story_id, "ffmpeg", 95)
        db = SessionLocal()
        try:
            story = db.query(Story).filter(Story.id == story_id).first()
            if not story:
                raise RuntimeError("未找到故事记录，无法执行 FFmpeg 合成。")
            if not story.original_image_path:
                raise RuntimeError("未找到原始图片，无法执行 FFmpeg 合成。")

            narration_audio_path = os.path.join(OUTPUT_DIR, f"{story_id}_narration.mp3")
            final_video_path = os.path.join(OUTPUT_DIR, f"{story_id}_story.mp4")
            compose_story_video(
                image_path=story.original_image_path,
                audio_path=narration_audio_path,
                output_path=final_video_path,
            )
            story.final_video_path = f"/media/outputs/{story_id}_story.mp4"
            db.commit()
        finally:
            db.close()
        record_cost(story_id, "ffmpeg", 0.0, int((time.time() - start_time) * 1000))

        # Done
        update_story_progress(story_id, "completed", 100)

    except Exception as e:
        update_story_progress(story_id, "failed", 0, error=str(e))
