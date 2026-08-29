# Fan Zone — Israeli Sports News Aggregation Platform

An ad-free, personalized sports news aggregation platform for Israeli sports portals (Sport5, Ynet, ONE, Walla, Israel Hayom, Sport1, Haaretz). The backend automatically ingests live RSS and web feeds, extracts clean content, enriches and summarizes articles using Google Gemini Structured Outputs, and provides high-performance filtered feed APIs for client applications.

---

## 📁 Repository Structure (Monorepo)

```
fan-zone/
├── backend/                       # Python FastAPI Backend Service
│   ├── api/                       # API layer (dependencies, v1 routers & endpoints)
│   │   ├── deps.py                # FastAPI dependencies (DB session, AI service, Repos)
│   │   └── v1/
│   │       ├── api.py             # Main v1 API router aggregation
│   │       └── endpoints/
│   │           ├── feed.py        # /api/v1/feed & /api/v1/feed/personal
│   │           ├── health.py      # /api/v1/health & dependency checks
│   │           └── ingestion.py   # /api/v1/ingest/trigger on-demand scraping
│   ├── core/                      # Core configuration & queue abstractions
│   │   ├── config.py              # Pydantic Settings & environment loader
│   │   └── queue.py               # InMemory & Redis async task queue
│   ├── db/                        # Database layer
│   │   ├── session.py             # Async SQLAlchemy engine & session factory
│   │   └── repository.py          # Article CRUD, filters & pagination
│   ├── models/                    # SQLAlchemy ORM models
│   │   └── feed.py                # ArticleModel definition
│   ├── schemas/                   # Pydantic validation schemas & contracts
│   │   └── feed.py                # RawArticlePayload, AIEnrichedCard, UserPreferences
│   ├── services/                  # Business logic & background workers
│   │   ├── ai_worker.py           # Gemini Structured Outputs & MockAI fallback
│   │   ├── scheduler.py           # Async periodic scraper scheduler
│   │   └── scrapers/              # Portal scrapers (Sport5, Ynet, ONE, Registry)
│   ├── tests/                     # Automated test suite (279 tests)
│   │   ├── unit/                  # Unit tests (schemas, config, scrapers, queue, AI)
│   │   ├── integration/           # Integration tests (DB CRUD, API, pipeline)
│   │   ├── security/              # Security audits (secret leakage, HTML sanitization)
│   │   └── fixtures/              # Mock fixtures and sample article payloads
│   ├── main.py                    # FastAPI application entrypoint & lifespan
│   ├── pytest.ini                 # Pytest configuration
│   ├── requirements.txt           # Python dependencies
│   ├── .env                       # Local environment variables
│   ├── .env.example               # Example environment template
│   └── fan_zone.db                # SQLite database (auto-generated)
│
├── client/                        # Frontend Client Application Workspace
│   └── README.md                  # Frontend setup guide & API integration notes
│
├── .agents/                       # Multi-agent specifications & audit reports
├── .gitignore                     # Monorepo git ignore rules
└── README.md                      # Developer documentation (this file)
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python 3.11+**
- **pip** and **virtualenv**
- (Optional) **Redis** for distributed task queues
- (Optional) **PostgreSQL** for production database (defaults to SQLite)

---

### Backend Setup

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to set your `GEMINI_API_KEY` (if testing with live AI). If no API key is provided or `USE_MOCK_AI=true`, the system automatically runs with the deterministic `MockAIEnricher`.

5. **Run the FastAPI server:**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

6. **Access Interactive Documentation:**
   - Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
   - ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
   - Health Check: [http://localhost:8000/health](http://localhost:8000/health)

---

### Running Automated Tests

The backend includes a comprehensive test suite (279 automated tests) covering unit tests, DB integration, async scraping, adversarial edge cases, security audits, and end-to-end pipelines.

From the `backend/` directory:
```bash
# Run all tests
pytest -q tests/

# Run with verbose output
pytest -v tests/

# Run specific test categories
pytest tests/unit/
pytest tests/integration/
pytest tests/security/
```

From the root directory (using virtualenv):
```bash
backend/.venv/Scripts/python.exe -m pytest -q backend/tests/
```

---

## ⚙️ Environment Configuration (`backend/.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_NAME` | `FanZone Israeli Sports Ingestion Backend` | Application title in docs & logs |
| `APP_ENV` | `development` | Environment (`development`, `production`, `test`) |
| `PORT` | `8000` | HTTP port for server binding |
| `DATABASE_URL` | `sqlite+aiosqlite:///./fan_zone.db` | Async SQLAlchemy URL (`sqlite+aiosqlite` or `postgresql+asyncpg`) |
| `GEMINI_API_KEY` | `""` | Google Gemini API Key |
| `GEMINI_MODEL` | `gemini-3.7-flash` | Gemini model name for structured outputs |
| `USE_MOCK_AI` | `false` | Set `true` to force deterministic offline AI mock mode |
| `ENABLE_SCHEDULER` | `true` | Enable periodic background scraper scheduler |
| `POLL_INTERVAL_SECONDS`| `300` | Frequency (seconds) for scheduled portal scraping |
| `SCRAPER_TIMEOUT_SECONDS` | `15` | HTTP request timeout for web scrapers |
| `REDIS_URL` | `""` | (Optional) Redis URL (`redis://localhost:6379/0`) for distributed queue |

---

## 📡 API Endpoints

### 1. Feed Retrieval
- **`GET /api/v1/feed`** (also aliased at `/api/feed`):
  - **Query Parameters**:
    - `tags`: Filter by team/sport/league (e.g. `?tags=מכבי תל אביב&tags=יורוליג` or `?tags=כדורסל,ג'ודו`)
    - `publisher`: Filter by portal (`sport5`, `ynet`, `one`, `walla`, etc.)
    - `date_from` / `date_to`: ISO 8601 timestamps
    - `tone`: `objective`, `hype`, or `critical`
    - `search`: Full-text substring search across headlines, summaries, and bodies
    - `page` (default `1`) and `page_size` (default `20`, max `100`)
- **`POST /api/v1/feed/personal`**:
  - Accepts JSON body with `UserPreferences` (`followed_tags`, `excluded_sources`, `preferred_tones`).
- **`GET /api/v1/feed/{article_id}`**:
  - Retrieve single enriched article card by ID.

### 2. Ingestion & Scrapers
- **`POST /api/v1/ingest/trigger`**:
  - Manually trigger on-demand scraping and AI enrichment.
  - Query parameters: `publisher` (e.g. `sport5`, `ynet`, `one`, or `all`) and `limit` (max articles to scrape per portal).

### 3. System & Health
- **`GET /health`** or **`GET /api/v1/health`**:
  - Returns service status, database connectivity, active AI mode (`live_gemini` or `mock`), and background scheduler state.

---

## 🧠 Architecture Highlights

1. **Strict Sanitization & Truncation**:
   - All article bodies undergo complete HTML stripping and entity unescaping before reaching AI workers.
   - Text inputs are strictly truncated to under 3,500 characters to prevent prompt injection and token overflow.
2. **Deterministic Fallbacks**:
   - In offline, testing, or API failure scenarios, the `MockAIEnricher` / `FallbackAIEnrichmentService` uses an Israeli sports entity lexicon and regex heuristics to generate compliant structured outputs.
3. **Cross-Dialect Database Layer**:
   - Seamlessly operates on local SQLite (`aiosqlite` with `StaticPool` for in-memory tests) and PostgreSQL (`asyncpg`) in production environments.
4. **Idempotency & Deduplication**:
   - Articles are deduplicated by canonical source URL at three distinct stages: scraper fetch, queue push, and repository persistence.
