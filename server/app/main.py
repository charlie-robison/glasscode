"""GlassCode FastAPI server — voice-control Claude Code from Meta glasses."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .project_router import router as project_router
from .session_router import router as session_router
from .voice_router import router as voice_router

app = FastAPI(title="GlassCode", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project_router, prefix="/api")
app.include_router(session_router, prefix="/api")
app.include_router(voice_router)


@app.get("/")
async def root():
    return {"service": "glasscode", "status": "running"}
