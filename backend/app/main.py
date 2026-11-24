from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Well Model Builder - Backend Orchestrator Stub",
    description="Каркас оркестратора для Роли 2 и Роли 3",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "backend",
        "message": "Orchestrator stub ready for Role 2 & Role 3"
    }
