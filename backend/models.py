from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Video(Base):
    __tablename__ = "videos"

    id = Column(String, primary_key=True, index=True)  # YouTube Video ID
    channel_id = Column(String, index=True, nullable=False)
    channel_title = Column(String, nullable=False)
    title = Column(String, index=True, nullable=False)
    description = Column(Text, default="")
    published_at = Column(DateTime, nullable=False)
    thumbnail_url = Column(String, default="")
    category = Column(String, index=True, default="General")
    raw_transcript = Column(Text, nullable=True)
    has_transcript = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class VideoAnalysis(Base):
    __tablename__ = "video_analyses"

    video_id = Column(String, ForeignKey("videos.id"), primary_key=True)
    executive_summary = Column(Text, nullable=False)
    key_takeaways = Column(JSON, default=list)        # list[str]
    topics_covered = Column(JSON, default=list)       # list[str]
    entities = Column(JSON, default=dict)             # {"people": [], "organizations": [], "locations": []}
    fact_check_notes = Column(JSON, default=list)     # list[dict]
    upsc_relevance = Column(JSON, default=dict)       # {"prelims_pointers": [], "mains_pointers": [], "syllabus_mapping": ""}
    deep_dossier_markdown = Column(Text, nullable=False)
    processed_at = Column(DateTime, default=datetime.utcnow)
