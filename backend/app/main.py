from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .auth import router as auth_router
from .budget import router as budget_router
from .categories import router as categories_router
from .config import settings
from .dashboard import router as dashboard_router
from .database import close_db_pool, init_db_pool
from .fixed_categories import router as fixed_categories_router
from .recurring import router as recurring_router
from .reports import router as reports_router
from .transactions import router as transactions_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db_pool()
    yield
    await close_db_pool()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(auth_router)
app.include_router(transactions_router)
app.include_router(budget_router)
app.include_router(categories_router)
app.include_router(reports_router)
app.include_router(dashboard_router)
app.include_router(fixed_categories_router)
app.include_router(recurring_router)


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
