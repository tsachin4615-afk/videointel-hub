from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from database import init_db
from api import videos, articles, search, assistant

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Backend AI news intelligence API powering VideoIntel Hub."
)

# Enable CORS for frontend clients (GitHub Pages and localhost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    await init_db()

# Mount API routers
app.include_router(videos.router, prefix="/api")
app.include_router(articles.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION
    }
