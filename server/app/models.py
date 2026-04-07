# 数据库模型定义，使用 SQLAlchemy
from sqlalchemy import Column, String, Integer, Float, DateTime, create_engine, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime
import uuid

from app.settings import get_settings

# 使用 SQLite 数据库
DATABASE_URL = get_settings().database_url

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Story(Base):
    """
    故事记录模型
    用途: 存储每次 POC 演示生成的故事的元数据及状态
    """
    __tablename__ = "stories"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(String, default="draft") # draft, uploaded, rendering, completed, failed
    original_image_path = Column(String)
    original_audio_path = Column(String)
    transcribed_text = Column(String)
    corrected_narration = Column(String)
    complexity_score = Column(Integer)
    render_route = Column(String)
    redrawn_image_path = Column(String)
    video_clip_path = Column(String)
    final_video_path = Column(String)
    progress_pct = Column(Integer, default=0)
    current_step = Column(String)
    error_message = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class RenderCost(Base):
    """
    渲染成本记录模型
    用途: 记录各个环节的预估/实际花费
    """
    __tablename__ = "render_costs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    story_id = Column(String, ForeignKey("stories.id"))
    step_name = Column(String)
    cost_usd = Column(Float)
    duration_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# 初始化表结构
Base.metadata.create_all(bind=engine)
