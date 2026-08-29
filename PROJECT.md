# Project: Fan Zone Israeli Sports News Backend

## Architecture
Fan Zone is an event-driven, asynchronous sports news aggregation backend built in Python using FastAPI, SQLAlchemy 2.0 (asyncio with aiosqlite and asyncpg), Google GenAI SDK (`gemini-3.7-flash`), BeautifulSoup4/Trafilatura, and Pydantic v2.

```
[Israeli Sports Portals (Sport5 / Ynet / ONE)]
                     │
                     ▼ (Async HTTP / RSS Extraction & HTML Sanitization)
           [Scraper Pipeline] ──> Enforces strict text truncation (<= 3500 chars)
                     │
                     ▼ Enqueue RawArticlePayload
             [Queue Layer] (InMemoryTaskQueue default / RedisTaskQueue)
                     │
                     ▼ Dequeue RawArticlePayload
         [AI Enrichment Service] (Google GenAI SDK Structured Outputs / MockAIEnricher fallback)
                     │
                     ▼ Validated AIEnrichedCard
         [Database Repository] (SQLAlchemy 2.0 Async ORM with SQLite/Postgres support)
                     │
                     ▼
         [FastAPI Delivery Layer] (Paginated & Multi-criteria Filtered Endpoints)
```

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | `ToneEnum` | Fixed-choice journalistic tone classification (`"objective"`, `"hype"`, `"critical"`) | M1 | R1, survey_spec_miner_1 |
| 2 | `PublisherEnum` | Standardized Israeli publisher identifiers (`"sport5"`, `"ynet"`, `"one"`, `"walla"`, etc.) | M1 | R1, survey_spec_miner_1 |
| 3 | `RawArticlePayload` | Ingested raw article data model with HTML sanitization and URL validation | M1 | R1, survey_spec_miner_1 |
| 4 | `AIEnrichedCard` | Gemini structured output model with single-sentence micro-summary (<=40 words), non-empty tags, tone, context label | M1 | R1, survey_spec_miner_1 |
| 5 | `UserPreferences` | User profile filter model (followed tags, excluded sources, preferred tones, language) | M1 | R1, survey_spec_miner_1 |
| 6 | `FeedItemResponse` | Serialized client response model for single enriched article cards | M1 | R1, survey_spec_miner_1 |
| 7 | `PaginatedFeedResponse` | Standardized pagination wrapper (items, total, page, page_size, total_pages, has_next, has_prev) | M1 | R1, survey_spec_miner_1 |
| 8 | `Settings` Configuration | Pydantic-settings config loading `.env` variables with safe defaults and SQLite/Postgres helpers | M1 | R4, survey_spec_miner_1 |
| 9 | `BaseScraper` Contract | Abstract base scraper interface for async RSS & HTML extraction | M2 | R2, survey_spec_miner_2 |
| 10 | `Sport5Scraper` | Async scraper for Sport5 portal with RSS discovery, Trafilatura/BeautifulSoup extraction | M2 | R2, survey_spec_miner_2 |
| 11 | `YnetScraper` | Async scraper for Ynet Sports portal | M2 | R2, survey_spec_miner_2 |
| 12 | `ONEScraper` | Async scraper for ONE Sports portal | M2 | R2, survey_spec_miner_2 |
| 13 | Content Sanitizer | Strips raw HTML tags (`<script>`, `<div>`, `<iframe>`) and normalizes Hebrew/RTL text | M2 | R2, R5, survey_spec_miner_2 |
| 14 | Strict Text Truncation | Slices article body text strictly to `raw_text[:3500]` characters before AI processing | M2 | R2, survey_spec_miner_2 |
| 15 | Task Queue Decoupling | `InMemoryTaskQueue` (asyncio.Queue) & `RedisTaskQueue` with URL deduplication | M2 | R2, survey_spec_miner_2 |
| 16 | `ArticleModel` ORM | SQLAlchemy 2.0 async model supporting SQLite (`aiosqlite`) and PostgreSQL (`asyncpg`) | M3 | R3, survey_spec_miner_2 |
| 17 | DB Session & Engine | Dual-dialect async engine manager with `StaticPool` support for test environments | M3 | R3, survey_spec_miner_2 |
| 18 | `ArticleRepository` CRUD | Async repository supporting article persistence, URL deduplication, and filtered queries | M3 | R3, survey_spec_miner_2 |
| 19 | `GeminiAIEnricher` | `google-genai` SDK structured output integration with `gemini-2.5-flash` | M4 | R3, survey_spec_miner_2 |
| 20 | `MockAIEnricher` | Deterministic offline AI enrichment engine with Israeli sports entity/tone extraction | M4 | R3, survey_spec_miner_2 |
| 21 | AI Service Dispatcher | Factory selecting live Gemini or deterministic mock enricher based on `USE_MOCK_AI` | M4 | R3, survey_spec_miner_2 |
| 22 | `GET /api/v1/feed` | Filtered & paginated article feed (by tags, publisher, date range, tone, search text) | M5 | R4, survey_spec_miner_1 |
| 23 | `POST /api/v1/feed/personal` | Feed query endpoint matching `UserPreferences` payload | M5 | R4, survey_spec_miner_1 |
| 24 | `GET /api/v1/feed/{id}` | Single enriched article lookup with 404 handling | M5 | R4, survey_spec_miner_1 |
| 25 | `GET /health` | Health and readiness check endpoint with async DB ping and AI mode detection | M5 | R4, survey_spec_miner_1 |
| 26 | `POST /api/v1/ingestion/trigger` | Manual scraping/ingestion trigger endpoint | M5 | R4, survey_spec_miner_1 |
| 27 | FastAPI App & Lifespan | Main application with CORS, route aggregation, and background scheduler initialization | M5 | R4, survey_spec_miner_1 |
| 28 | Test Infrastructure & Fixtures | `pytest.ini`, `tests/conftest.py`, static HTML/RSS/Gemini fixtures | M_TEST | R5, survey_explorer_3 |
| 29 | Tier 1-4 Test Suites | Comprehensive unit and integration test suites covering all R1-R4 features | M_TEST | R5, survey_explorer_3 |
| 30 | Security & Sanitization Tests | Static AST/regex secrets audit (0 hardcoded keys) and HTML leakage tests | M_TEST | R5, survey_explorer_3 |
| 31 | Final E2E Verification & Hardening | 100% test pass against full integrated backend and adversarial stress hardening | M6 | R5, Project Pattern |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Pydantic Contracts & Settings | `app/schemas/feed.py`, `app/core/config.py` | none | DONE |
| M2 | Web Scraping & Ingestion Pipeline | `app/services/scrapers/`, `app/core/queue.py`, sanitization & truncation | M1 | DONE |
| M3 | Database Layer & Async ORM | `app/db/`, `app/models/feed.py`, `app/db/repository.py` | M1 | DONE |
| M4 | AI Enrichment Service & Worker | `app/services/ai_worker.py` (Gemini SDK & MockAIEnricher) | M1, M3 | DONE |
| M5 | FastAPI Application & Routers | `app/api/`, `app/main.py`, lifespan & scheduler integration | M1, M2, M3, M4 | DONE |
| M_TEST | E2E Testing Track | `pytest.ini`, `tests/conftest.py`, `tests/fixtures/`, `tests/unit/`, `tests/integration/`, `tests/security/` -> `TEST_READY.md` | M1 | DONE |
| M6 | Final Verification & Hardening | Phase 1: 100% E2E test pass; Phase 2: Adversarial coverage hardening; Phase 3: Forensic audit | M5, M_TEST | DONE |


---

## Interface Contracts

### 1. `app.schemas.feed` ↔ All Services
- `RawArticlePayload(title, raw_body, url, publisher, published_at, category, author, image_url)`
- `AIEnrichedCard(micro_summary, tags, tone, context_label)`
- `UserPreferences(followed_tags, excluded_sources, preferred_tones, language)`
- `ToneEnum` values: `"objective"`, `"hype"`, `"critical"`
- `FeedItemResponse(id, title, url, publisher, published_at, micro_summary, tags, tone, context_label, category, author, created_at)`
- `PaginatedFeedResponse(items, total, page, page_size, total_pages, has_next, has_prev)`

### 2. `app.core.config.Settings`
- `DATABASE_URL`: default `"sqlite+aiosqlite:///./fan_zone.db"`
- `GEMINI_API_KEY`: `Optional[str] = None`
- `GEMINI_MODEL`: default `"gemini-2.5-flash"`
- `USE_MOCK_AI`: `bool = False`
- `ENABLE_SCHEDULER`: `bool = True`
- `POLL_INTERVAL_SECONDS`: `int = 300`

### 3. `app.services.scrapers` ↔ `app.core.queue`
- Scrapers return `List[RawArticlePayload]` with `len(raw_body) <= 3500` and HTML stripped.
- `BaseQueue.push(item: RawArticlePayload) -> bool` (returns False on duplicate URL).
- `BaseQueue.pop(timeout: Optional[float]) -> Optional[RawArticlePayload]`.

### 4. `app.services.ai_worker` ↔ `app.db.repository`
- `AIEnrichmentService.enrich_article(article: RawArticlePayload) -> AIEnrichedCard`
- `ArticleRepository.create_enriched_article(raw: RawArticlePayload, enriched: AIEnrichedCard) -> ArticleModel`
- `ArticleRepository.list_articles(tags, publishers, date_from, date_to, tone, search, page, page_size) -> Tuple[List[ArticleModel], int]`

---

## Code Layout

```
fan-zone/
├── .env.example
├── requirements.txt
├── pytest.ini
├── app/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app instance, CORS, routes inclusion, lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py               # get_db, get_settings, common query params
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── api.py            # APIRouter aggregator
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           ├── feed.py       # /api/v1/feed, /api/v1/feed/{id}, /api/v1/feed/personal
│   │           ├── health.py     # /health, /api/v1/health
│   │           └── ingestion.py  # /api/v1/ingestion/trigger
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py             # Settings (pydantic-settings)
│   │   └── queue.py              # InMemoryTaskQueue, RedisTaskQueue, BaseQueue
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py            # create_async_engine, async_sessionmaker, get_db, Base
│   │   └── repository.py         # ArticleRepository (async CRUD & query filters)
│   ├── models/
│   │   ├── __init__.py
│   │   └── feed.py               # ArticleModel (SQLAlchemy 2.0 ORM)
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── feed.py               # RawArticlePayload, AIEnrichedCard, UserPreferences, responses
│   └── services/
│       ├── __init__.py
│       ├── ai_worker.py          # GeminiAIEnricher, MockAIEnricher, AIEnrichmentService
│       ├── scheduler.py          # Periodic background scraping service
│       └── scrapers/
│           ├── __init__.py
│           ├── base.py           # BaseScraper abstract class & sanitization utils
│           ├── sport5.py         # Sport5Scraper
│           ├── ynet.py           # YnetScraper
│           ├── one.py            # ONEScraper
│           └── registry.py       # Scraper registry & dispatcher
└── tests/
    ├── __init__.py
    ├── conftest.py               # Test settings, in-memory async SQLite engine, async_client
    ├── fixtures/
    │   ├── __init__.py
    │   ├── raw_articles.py       # Mock RawArticlePayload objects
    │   ├── sample_rss.py         # Mock XML RSS feeds
    │   ├── sample_html.py        # Mock HTML articles
    │   └── mock_gemini.py        # Mock Gemini SDK responses
    ├── unit/
    │   ├── __init__.py
    │   ├── test_schemas.py
    │   ├── test_scrapers.py
    │   ├── test_queue.py
    │   ├── test_ai_worker.py
    │   ├── test_models.py
    │   └── test_config.py
    ├── integration/
    │   ├── __init__.py
    │   ├── test_db_crud.py
    │   ├── test_api_feed.py
    │   ├── test_api_health_ingest.py
    │   └── test_end_to_end_pipeline.py
    └── security/
        ├── __init__.py
        ├── test_no_hardcoded_secrets.py
        └── test_html_leakage.py
```
