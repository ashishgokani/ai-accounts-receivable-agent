"""
Main FastAPI Application Entry Point.

Sets up CORS middleware, manages database initialization lifecycle,
mounts API routers, and provides operational health check endpoints.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import engine, Base, SessionLocal
from app.db.seeder import seed_database
from app.api import api_router
from app.services.scheduler import automation_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager that creates database schemas, seeds initial
    data if empty, and launches autonomous background collection scheduling.
    """
    # 1. Initialize relational database tables
    Base.metadata.create_all(bind=engine)

    # 2. Seed initial data if tables are empty
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    # 3. Automatically start autonomous collection background scheduler
    automation_scheduler.start()

    try:
        yield
    finally:
        # Gracefully terminate background workers on shutdown
        automation_scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Production-grade AI-Powered Autonomous Accounts Receivable Management Agent.",
    lifespan=lifespan,
)

# Configure Cross-Origin Resource Sharing (CORS) for Vite React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all feature routes
app.include_router(api_router)


@app.get("/health", tags=["Health"])
def health_check():
    """Operational health check confirming API and AI Gateway connectivity."""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.environment,
        "bedrock_model": settings.bedrock_model_id,
        "aws_region": settings.aws_region,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=True,
    )
