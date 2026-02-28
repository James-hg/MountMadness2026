from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

from .config import settings

app = FastAPI(title=settings.app_name)


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
