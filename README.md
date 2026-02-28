# Mount Madness 2026

## Stack
- Backend: FastAPI
- Frontend: React (Vite)
- AI: Gemini API
- Runtime: Docker Compose

## Quick Start
1. Copy environment files:
   - `cp backend/.env.example backend/.env`
2. Add your Gemini key in `backend/.env`.
3. Start services:
   - `docker compose up --build`

## URLs
- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- FastAPI docs: http://localhost:8000/docs

## Notes
- Frontend calls backend at `VITE_API_BASE_URL`.
- Backend reads `GEMINI_API_KEY` and `GEMINI_MODEL` from environment.
