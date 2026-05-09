# SHL Conversational Assessment Recommender

A stateless conversational AI agent that guides hiring managers and recruiters from a vague hiring intent to a precise, grounded shortlist of SHL Individual Test Assessments through multi-turn dialogue.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.11) |
| LLM (Primary) | Google Gemini 1.5 Flash |
| LLM (Fallback) | Groq Llama 3.1 8B |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Vector DB | ChromaDB (in-process, persisted) |
| Catalog | JSON flat file (`catalog.json`) |
| Hosting | Render.com free tier |
| Frontend (optional) | Next.js on Vercel |

## Setup

```bash
# Clone and install
git clone <repo>
cd shl-recommender/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Build Catalog (one-time)

```bash
python scraper.py
python scripts/build_index.py
```

## Run Locally

```bash
uvicorn main:app --reload --port 8000
```

## Environment Variables

Copy the example env file and fill in your keys:

```bash
cp backend/.env.example backend/.env
```

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GROQ_API_KEY` | Groq API key (fallback LLM) |
| `PORT` | Server port (default: 8000) |
| `CATALOG_PATH` | Path to catalog.json |
| `CHROMA_PATH` | Path to ChromaDB persistence directory |

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Readiness probe — returns `{"status": "ok"}` |
| `POST` | `/chat` | Conversational assessment recommender |

## Deployment (Render.com)

1. Create Render.com account
2. New Web Service → connect GitHub repo
3. Build command: `pip install -r requirements.txt && python scraper.py && python scripts/build_index.py`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables in Render dashboard
6. Set disk: 1GB persistent (for ChromaDB)
7. Instance type: Free (512MB RAM)
