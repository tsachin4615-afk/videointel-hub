from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models import Base

repo_root = Path(__file__).resolve().parent.parent

resolved_data_dir = Path(settings.DATA_DIR).expanduser()
if not resolved_data_dir.is_absolute():
    resolved_data_dir = (repo_root / resolved_data_dir).resolve()
resolved_data_dir.mkdir(parents=True, exist_ok=True)

resolved_db_url = settings.DATABASE_URL
if resolved_db_url.startswith("sqlite+aiosqlite:///"):
    sqlite_path = resolved_db_url.replace("sqlite+aiosqlite:///", "", 1)
    sqlite_path_obj = Path(sqlite_path).expanduser()
    if not sqlite_path_obj.is_absolute():
        sqlite_path_obj = (repo_root / sqlite_path_obj).resolve()
    resolved_db_url = f"sqlite+aiosqlite:///{sqlite_path_obj.as_posix()}"

engine = create_async_engine(
    resolved_db_url,
    echo=False,
    connect_args={"check_same_thread": False} if resolved_db_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
