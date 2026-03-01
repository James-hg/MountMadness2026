from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .budget import router as budget_router
from .config import settings
from .database import close_db_pool, init_db_pool
from .transactions import router as transactions_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(transactions_router)
app.include_router(budget_router)


class PromptRequest(BaseModel):
    prompt: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/generate")
async def generate_text(payload: PromptRequest) -> dict[str, str]:
    if not settings.gemini_api_key:
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not set")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    params = {"key": settings.gemini_api_key}
    body = {
        "contents": [
            {
                "parts": [
                    {"text": payload.prompt}
                ]
            }
        ]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, params=params, json=body)

    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    data = response.json()
    text = ""

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        text = ""

    return {"text": text}
