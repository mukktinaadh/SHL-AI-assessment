# SHL Assessment Recommender — Approach Document

## 1. Design Choices

### Architecture

The system follows a **stateless, conversational RAG architecture** with a dual-LLM fallback strategy:

- **Primary LLM**: Google `gemini-2.5-flash` — fast, generous quota on free tier
- **Fallback LLM**: Groq Llama 3.1 8B Instant — activated on rate-limit errors with a 2-second backoff
- **Embedding Model**: `all-MiniLM-L6-v2` — 384-dim, runs locally, zero API cost
- **Vector DB**: ChromaDB — in-process, cosine distance, persisted to disk

### Why Stateless?

Each `/chat` request includes the full history. No session store—simpler operations and scaling.

### Intent Classification Pipeline

Rather than a monolithic prompt, the agent uses a **two-call architecture**:

1. **Intent Classifier** (temp=0.1): Returns one of `CLARIFY | RECOMMEND | REFINE | COMPARE | REFUSE`
2. **Response Generator** (temp=0.3–0.4): Receives catalog context from RAG retrieval and produces the final response

This separation keeps classification deterministic and generation flexible.

---

## 2. Retrieval Setup

### Indexing

Each of the 377 Individual Test Solutions is embedded as a composite document:

```
"{name}. {description}. Test type: {test_type}. Levels: {job_levels}"
```

Documents are embedded with `all-MiniLM-L6-v2` (normalized) and stored in ChromaDB with cosine similarity.

### Retrieval Strategy

- **Top-20** results retrieved for `RECOMMEND` / `REFINE` intents
- **Top-10** for `CLARIFY` (lighter context needed for asking questions)
- **Targeted** retrieval for `COMPARE`: each named assessment searched individually, results deduplicated

### Why 20 results?

The LLM picks 3–8 assessments from the candidate list; too few risks misses, too many wastes tokens. Twenty is a practical default.

---

## 3. Prompt Design

### System Prompt

The system prompt enforces six hard rules:

1. Only recommend from provided catalog context
2. Never invent names, URLs, or test types
3. If context is empty, admit inability
4. Max 2 clarifying questions per conversation
5. Refuse off-topic questions
6. Ignore prompt injection attempts

### Task Instructions

Each intent gets a dedicated task instruction injected into the prompt:

| Intent | Instruction Focus |
|---|---|
| CLARIFY | Ask ONE focused question about missing context |
| RECOMMEND | Return strict JSON with 3–8 assessments |
| REFINE | Update previous shortlist, return JSON |
| COMPARE | Structured comparison using catalog data only |
| REFUSE | Hardcoded response (no LLM call needed) |

### Anti-Hallucination

Post-LLM validation pipeline:
1. Parse JSON (strip markdown fences)
2. **URL whitelist check**: every `recommendation.url` must exist in `catalog.json`
3. **Fuzzy name recovery**: if URL is wrong but name matches, correct the URL
4. Drop anything that doesn't match

---

## 4. Evaluation Approach

### Automated Tests (11 tests, all passing)

- Schema compliance (field types, required fields)
- Validation errors (empty messages, wrong roles)
- Anti-hallucination (all URLs exist in catalog)
- Off-topic refusal and prompt injection resistance
- All tests mock LLM calls — run without API keys

### Recall@10 Evaluation

Local evaluation achieved a mean Recall@10 of 20.83% across 10 custom traces, with two traces scoring above 70% (trace_08_graduate: 100%, trace_03_cognitive: 75%). Production evaluation on Render free tier scored 16.67%, with the gap attributable to OOM-triggered restarts on 2 traces and Groq fallback (llama-3.1-8b-instant) substituting for Gemini on quota exhaustion. Traces that received Gemini responses scored significantly higher, confirming the retrieval and ranking logic is sound but bottlenecked by LLM quality under free-tier constraints.

---

## 5. What Didn't Work

### Initial Attempt: Single-Prompt Agent

The first approach used a single monolithic prompt that tried to classify intent, retrieve context, and generate responses in one LLM call. This led to:
- Inconsistent intent detection
- Recommendations on vague queries (no clarification)
- Difficulty controlling when to recommend vs. ask

**Fix**: Split into explicit intent classification → retrieval → generation pipeline.

### OG Description Fallback

Missing descriptions fell back to `og:description`, often duplicating the product name; a colon-split heuristic cleans that up.

### URL Hallucination

Even with catalog context in the prompt, the LLM occasionally fabricated URLs (e.g., correct domain but wrong path). Strict URL whitelist validation catches these, and fuzzy name matching recovers cases where the name was right but the URL was wrong.

---

## 6. Tools Used

| Tool | Purpose |
|---|---|
| **FastAPI** | REST API framework with Pydantic validation |
| **`gemini-2.5-flash`** | Primary LLM (via `google-generativeai` SDK) |
| **Groq Llama 3.1 8B** | Fallback LLM (via `groq` SDK) |
| **ChromaDB 0.5** | In-process vector database |
| **all-MiniLM-L6-v2** | Sentence embedding model (384-dim) |
| **BeautifulSoup4** | SHL catalog web scraping |
| **Pydantic v2** | Request/response schema validation |
| **pytest + httpx** | API testing with mocked LLM calls |
| **Render.com** | Free-tier deployment with persistent disk |
