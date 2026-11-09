
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def current_time():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    youtube_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )
    title: Mapped[str] = mapped_column(String(1000))
    channel: Mapped[str] = mapped_column(String(300), default="")
    link: Mapped[str] = mapped_column(String(1000))
    thumbnail: Mapped[str] = mapped_column(String(1000), default="")

    published: Mapped[str] = mapped_column(String(100), default="")
    description: Mapped[str] = mapped_column(Text, default="")

    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_available: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=current_time
    )

    topics: Mapped[list["Topic"]] = relationship(
        back_populates="video",
        cascade="all, delete-orphan"
    )


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    title: Mapped[str] = mapped_column(String(500), index=True)
    category: Mapped[str] = mapped_column(String(150), default="General")
    summary: Mapped[str] = mapped_column(Text, default="")

    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    keywords: Mapped[list] = mapped_column(JSON, default=list)

    video_id: Mapped[int] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"),
        index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=current_time
    )

    video: Mapped["Video"] = relationship(back_populates="topics")

    articles: Mapped[list["Article"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan"
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    headline: Mapped[str] = mapped_column(String(1000))
    overview: Mapped[str] = mapped_column(Text, default="")

    # Stores structured article sections as JSON.
    content: Mapped[dict] = mapped_column(JSON, default=dict)

    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"),
        index=True
    )

    status: Mapped[str] = mapped_column(
        String(50), default="draft"
    )

    upsc_relevance: Mapped[bool] = mapped_column(
        Boolean, default=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=current_time
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=current_time,
        onupdate=current_time
    )

    topic: Mapped["Topic"] = relationship(back_populates="articles")

    research_sources: Mapped[list["ResearchSource"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan"
    )


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    article_id: Mapped[int] = mapped_column(
        ForeignKey("articles.id", ondelete="CASCADE"),
        index=True
    )

    title: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(2000))
    publisher: Mapped[str] = mapped_column(String(300), default="")
    source_type: Mapped[str] = mapped_column(String(100), default="web")

    notes: Mapped[str] = mapped_column(Text, default="")
    supports_claim: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=current_time
    )

    article: Mapped["Article"] = relationship(
        back_populates="research_sources"
    )
