# SHL Conversational Assessment Recommender

[![CI](https://github.com/mukktinaadh/SHL-AI-assessment/actions/workflows/ci.yml/badge.svg)](https://github.com/mukktinaadh/SHL-AI-assessment/actions/workflows/ci.yml)

A stateless conversational AI agent that guides recruiters from a vague hiring intent to a grounded shortlist of SHL Individual Test Assessments.

## Live API
- **Health Check:** `GET https://shl-assessment-recommender-g6wx.onrender.com/health`
- **Chat Endpoint:** `POST https://shl-assessment-recommender-g6wx.onrender.com/chat`

## Architecture
```text
User 
  → FastAPI 
    → Intent Classifier (CLARIFY, RECOMMEND, REFUSE)
      → ChromaDB RAG (Vector Search on Catalog)
        → Gemini 2.5 Flash / Groq Llama 3.1 8B 
          → Validated Response (Whitelist Filter)
            → User
```

## Tech Stack
| Component | Technology |
|---|---|
| **Backend** | FastAPI (Python 3.11) |
| **Primary LLM** | Google Gemini 2.5 Flash |
| **Fallback LLM** | Groq Llama 3.1 8B Instant |
| **Embeddings** | `sentence-transformers/all-MiniLM-L6-v2` |
| **Vector DB** | ChromaDB (In-process, Persisted) |
| **Hosting** | Render.com |

## Local Setup
1. Clone the repository and configure environment variables:
   ```bash
   git clone https://github.com/mukktinaadh/SHL-AI-assessment.git
   cd SHL-AI-assessment
   echo "GEMINI_API_KEY=your_gemini_key" > backend/.env
   echo "GROQ_API_KEY=your_groq_key" >> backend/.env
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Run the backend (this will automatically scrape the catalog and build the ChromaDB index on the first run, or you can run `python backend/scripts/build_index.py` manually):
   ```bash
   cd backend
   python -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```
4. Optional: Run the Next.js frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

## Running Tests
Run unit tests (mocked, no API keys required):
```bash
cd backend
pytest tests/test_api.py -v
```
Run the Recall@10 behavioral evaluation against the 10 provided traces:
```bash
cd backend
python tests/eval_recall.py --traces tests/test_traces/ --endpoint http://localhost:8000
```

## API Contract

**Request: `POST /chat`**
```json
{
  "messages": [
    {
      "role": "user",
      "content": "I am hiring a mid-level Java developer."
    }
  ]
}
```

**Response**
```json
{
  "reply": "For a mid-level Java developer, I recommend...",
  "recommendations": [
    {
      "name": "Java 8 (New)",
      "url": "https://www.shl.com/products/product-catalog/view/java-8-new/",
      "test_type": "K"
    }
  ],
  "end_of_conversation": false
}
```

## Key Design Decisions
- **Anti-Hallucination Guardrails:** The LLM's output is strictly validated against a fast, in-memory URL whitelist of the scraped catalog. If the LLM hallucinates an assessment or URL, it is either fuzzy-matched to the correct one or dropped entirely.
- **Stateless Design:** The backend stores zero session state. The frontend sends the entire conversation history on every request, allowing the backend to be horizontally scaled or deployed on serverless infrastructure.
- **Fallback Orchestration:** If the primary LLM (Gemini) hits rate limits or goes down, the system automatically and transparently falls back to Groq (Llama 3.1 8B).
- **Intent Classification:** Instead of brute-forcing RAG on every prompt, an initial classification step determines if the user is asking for clarification, refining, comparing, or attempting a prompt injection, routing them to the optimal pipeline.

## Repository Structure
```text
.
├── backend/
│   ├── data/              # Auto-generated (catalog.json, chroma_db/)
│   ├── scripts/           # build_index.py
│   ├── tests/             # Pytest suite & eval_recall.py
│   ├── agent.py           # Orchestration & Intent logic
│   ├── llm.py             # LLM Clients & Fallback
│   ├── main.py            # FastAPI Entrypoint
│   ├── retriever.py       # ChromaDB RAG
│   ├── schemas.py         # Pydantic API Models
│   ├── scraper.py         # SHL Catalog Scraper
│   ├── prompts.py         # System Prompts
│   ├── Dockerfile         # Render.com build specs
│   └── requirements.txt   
├── frontend/              # Next.js Chat Interface
├── docs/                  # Design Approach Document
├── render.yaml            # Render Deployment Spec
└── .github/workflows/     # CI Pipeline
```
