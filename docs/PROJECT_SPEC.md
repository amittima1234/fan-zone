# Project: Fan Zone — Israeli Sports News Ingestion & AI Tagging Backend

## Architecture
Fan Zone is an automated Israeli sports news monitoring, ingestion, AI headline rewriting, entity classification, and persistence backend service.

### System Data Flow
1. **Source Discovery & Ingestion**: Periodic background scheduler or manual trigger invokes source-specific scrapers/parsers (Sport5, ONE, Walla! Sports, Ynet Sport, Sport1, Israel Hayom, Haaretz).
2. **Parsing & Deduplication**: Extracts article metadata (title, subtitle, author, published date, paragraphs, main/gallery images with captions) and performs dual deduplication checks via `canonical_url` normalization and SHA-256 `content_hash`.
3. **AI Headline Rewriting & Entity Tagging**: Unprocessed articles are passed to the Gemini AI Engine (`google-genai` with `gemini-2.5-flash` / `gemini-1.5-flash`), which generates objective, non-clickbait Hebrew headlines, concise subheadlines, and extracts structured sports entity tags (`sport`, `teams`, `players`, `competition`, `tags`).
4. **Persistence Layer**: SQLAlchemy 2.0 ORM saves articles, media, and entity tags with dual-database support (SQLite for local/test, PostgreSQL for production) and repository query methods.
5. **API & Presentation**: FastAPI REST API exposes paginated search and filter endpoints by sport, team, competition, tag, source, and date range, alongside ingestion triggers and health/stats endpoints.

```
 [RSS Feeds / Web Pages]
 (Sport5, ONE, Walla, Ynet, Sport1, Israel Hayom, Haaretz)
            │
            ▼
 ┌────────────────────────────────────────┐
 │ 1. Ingestion & Scrapers Module         │
 │    - BaseSourceParser & Source Parsers │
 │    - URL normalizer & Content Hash     │
 └──────────────────┬─────────────────────┘
                    │ Raw ExtractedArticle
                    ▼
 ┌────────────────────────────────────────┐
 │ 2. Gemini AI Processing & Tagging      │
 │    - google-genai structured output    │
 │    - Non-clickbait Hebrew rewriter     │
 │    - Sport, Team, Player, League tags  │
 │    - Tenacity retry + Offline Mock     │
 └──────────────────┬─────────────────────┘
                    │ Enriched ArticleAnalysisResult
                    ▼
 ┌────────────────────────────────────────┐
 │ 3. Persistence & Repository Layer      │
 │    - SQLAlchemy 2.0 Models             │
 │    - Article, Media, Tag, Source       │
 │    - SQLite & PostgreSQL compatibility │
 └──────────────────┬─────────────────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│ 4. Background    │  │ 5. FastAPI REST  │
│    Scheduler     │  │    API Service   │
│ (AsyncIO Poller) │  │  (/api/v1/...)   │
└──────────────────┘  └──────────────────┘
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| 1 | Multi-Source Scrapers (7 Sources) | Scrapers for Sport5, ONE, Walla! Sports, Ynet Sport, Sport1, Israel Hayom, Haaretz | M2 | ORIGINAL_REQUEST §R1 |
| 2 | Article Metadata Extraction | Extracts title, subtitle, author, publish date, clean text paragraphs, image URLs/captions | M2 | ORIGINAL_REQUEST §R1 |
| 3 | Per-Source Deduplication Engine | Canonical URL normalization and SHA-256 content hashing scoped per source to avoid duplicate re-ingestion while allowing distinct sources to cover the same story | M2 | ORIGINAL_REQUEST §R1 |
| 4 | Gemini AI Non-Clickbait Headline | Generates objective, sensationalism-free Hebrew headlines using Gemini (`google-genai`) | M3 | ORIGINAL_REQUEST §R2 |
| 5 | Gemini AI Subheadline Summary | Generates concise 1-2 sentence Hebrew summarizing subheadlines | M3 | ORIGINAL_REQUEST §R2 |
| 6 | Sports Entity Extraction & Tagging | Classifies `sport`, `teams`, `players`, `competition`, and generic `tags` | M3 | ORIGINAL_REQUEST §R2 |
| 7 | AI Error Resilience & Mock Mode | Exponential backoff for 429/503, fallback rule-based analyzer, offline deterministic mock | M3 | ORIGINAL_REQUEST §R2 |
| 8 | SQLAlchemy 2.0 Models | Article, Source, Tag, ArticleTag, ArticleMedia with relations and indexes | M1 | ORIGINAL_REQUEST §R3 |
| 9 | Dual Database Support | SQLite (local development/tests) and PostgreSQL (`DATABASE_URL`) parity | M1 | ORIGINAL_REQUEST §R3 |
| 10 | Repository Query Methods | Rich querying/filtering by sport, team, competition, tag, source, date, and keyword | M1 | ORIGINAL_REQUEST §R3 |
| 11 | Periodic Background Scheduler | In-process AsyncIO poller with mutual exclusion lock and configurable interval | M4 | ORIGINAL_REQUEST §R4 |
| 12 | FastAPI REST Endpoints | GET /articles, GET /articles/{id}, POST /ingest/trigger, GET /sources, GET /tags, health/stats | M4 | ORIGINAL_REQUEST §R4 |
| 13 | Comprehensive Automated Test Suite | Tiers 1-4 test coverage across all requirements with mock & live modes | M5 | ORIGINAL_REQUEST §Verification |
| 14 | End-to-End Verification Demo Script | Demonstrates fetching, processing, tagging, storing, and querying sample articles | M5 | ORIGINAL_REQUEST §Verification |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | Core Config, Models & Repositories | Pydantic Settings, SQLAlchemy 2.0 DB Engine, ORM Models (Article, Source, Tag, Media), Repository Layer with filtering & upsert | none | DONE |
| M2 | Ingestion Engine & 7 Multi-Source Parsers | BaseSourceParser, 7 concrete parsers (Sport5, ONE, Walla, Ynet, Sport1, Israel Hayom, Haaretz), canonical URL normalizer, content hasher, IngestionService | M1 | DONE |
| M3 | Gemini AI Tagging & Non-Clickbait Engine | `google-genai` client integration, structured Pydantic schemas, Hebrew prompt templates, tenacity retry, rule-based fallback, MockAIProcessor | M1 | DONE |
| M4 | Background Scheduler & FastAPI REST API | In-process asyncio scheduler, FastAPI app, `/api/v1` routes (articles, sources, tags, ingest, health, stats), CORS, lifecycle hooks | M1, M2, M3 | DONE |
| M5 | E2E Testing, Acceptance Verification & Hardening | 5-Tier E2E test suite pass (100%), Tier 5 adversarial tests, E2E CLI verification script, final audit | M1, M2, M3, M4 | DONE |

## Interface Contracts

### M1 ↔ Downstream Modules (`fan_zone.db` & `fan_zone.repositories`)
```python
class ArticleRepository:
    async def get_by_id(self, db: AsyncSession, article_id: int) -> Optional[Article]: ...
    async def get_by_canonical_url(self, db: AsyncSession, canonical_url: str) -> Optional[Article]: ...
    async def get_by_content_hash(self, db: AsyncSession, content_hash: str) -> Optional[Article]: ...
    async def list_articles(
        self,
        db: AsyncSession,
        source_id: Optional[int] = None,
        sport: Optional[str] = None,
        team: Optional[str] = None,
        competition: Optional[str] = None,
        tag: Optional[str] = None,
        search_query: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> Tuple[List[Article], int]: ...
    async def upsert_article(self, db: AsyncSession, article_data: ArticleCreate, media_data: List[MediaCreate], tag_names: List[Tuple[str, str]]) -> Article: ...
```

### M2 ↔ Ingestion Service (`fan_zone.scrapers`)
```python
class ExtractedArticle(BaseModel):
    source_name: str
    original_url: str
    canonical_url: str
    content_hash: str
    original_title: str
    original_subtitle: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    paragraphs: List[str]
    images: List[ExtractedImage] = []
    category_hint: Optional[str] = None

class BaseSourceParser(ABC):
    source_name: str
    async def discover_articles(self, client: httpx.AsyncClient) -> List[str]: ...
    async def parse_article(self, client: httpx.AsyncClient, url: str) -> Optional[ExtractedArticle]: ...
```

### M3 ↔ AI Tagging Engine (`fan_zone.ai`)
```python
class ArticleAnalysisResult(BaseModel):
    headline: str
    subheadline: str
    sport: str
    teams: List[str] = []
    players: List[str] = []
    competition: Optional[str] = None
    tags: List[str] = []

class BaseAIProcessor(ABC):
    async def analyze_article(self, title: str, subtitle: Optional[str], body: str) -> ArticleAnalysisResult: ...
```

### M4 ↔ REST API & Scheduler (`fan_zone.api` & `fan_zone.scheduler`)
```python
# REST API:
# GET /api/v1/articles?sport=...&team=...&competition=...&tag=...&source=...&q=...&page=1&size=20
# GET /api/v1/articles/{id}
# POST /api/v1/ingest/trigger (body: {"source_name": Optional[str], "url": Optional[str]})
# GET /api/v1/sources
# GET /api/v1/tags
# GET /api/v1/health
# GET /api/v1/stats

class IngestionScheduler:
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def run_now(self, source_name: Optional[str] = None) -> IngestionRunStats: ...
```

## Code Layout
```
fan_zone/
├── __init__.py
├── main.py                         # FastAPI application entry point
├── config.py                       # Pydantic Settings configuration
├── db/
│   ├── __init__.py
│   ├── session.py                  # Engine, sessionmaker, async/sync DB session dependency
│   └── base.py                     # DeclarativeBase metadata
├── models/
│   ├── __init__.py
│   ├── source.py                   # Source ORM model
│   ├── article.py                  # Article & ArticleMedia ORM models
│   └── tag.py                      # Tag & ArticleTag ORM models
├── schemas/
│   ├── __init__.py
│   ├── article.py                  # Article Pydantic schemas (read, create, filter)
│   ├── media.py                    # Media schemas
│   ├── tag.py                      # Tag schemas
│   ├── source.py                   # Source schemas
│   └── ingest.py                   # Ingest trigger and stats schemas
├── repositories/
│   ├── __init__.py
│   ├── base.py
│   ├── article_repo.py             # Article data access & queries
│   ├── source_repo.py              # Source management queries
│   └── tag_repo.py                 # Tag lookup & association queries
├── scrapers/
│   ├── __init__.py
│   ├── base.py                     # BaseSourceParser & normalization/hashing helpers
│   ├── sport5.py                   # Sport5 parser
│   ├── one.py                      # ONE parser
│   ├── walla.py                    # Walla! Sports parser
│   ├── ynet.py                     # Ynet Sport parser
│   ├── sport1.py                   # Sport1 parser
│   ├── israel_hayom.py             # Israel Hayom parser
│   ├── haaretz.py                  # Haaretz parser
│   └── registry.py                 # Scraper registry
├── ai/
│   ├── __init__.py
│   ├── base.py                     # BaseAIProcessor interface
│   ├── gemini_client.py            # Gemini 2.5/1.5 Flash client (google-genai)
│   ├── prompts.py                  # Hebrew non-clickbait system prompt & few-shot examples
│   ├── fallback.py                 # Rule-based fallback extractor
│   └── mock.py                     # Deterministic MockAIProcessor for tests
├── services/
│   ├── __init__.py
│   ├── ingestion_service.py        # Orchestrates scraping, deduplication, AI tagging, DB save
│   └── article_service.py          # Business logic for article queries & formatting
├── scheduler/
│   ├── __init__.py
│   └── poller.py                   # AsyncIO periodic background polling worker with mutex
└── api/
    ├── __init__.py
    └── v1/
        ├── __init__.py
        ├── router.py               # Main v1 API router
        ├── articles.py             # Article search and detail endpoints
        ├── sources.py              # Source listing endpoints
        ├── tags.py                 # Tag exploration endpoints
        ├── ingest.py               # Ingestion trigger & history endpoints
        └── system.py               # Health and stats endpoints

tests/
├── conftest.py                     # Fixtures: async DB session, mock HTTP responses, mock AI
├── unit/
│   ├── test_models.py
│   ├── test_repositories.py
│   ├── test_scrapers.py
│   ├── test_deduplication.py
│   ├── test_ai_prompts_mock.py
│   └── test_api_schemas.py
├── integration/
│   ├── test_ingestion_service.py
│   ├── test_scheduler.py
│   └── test_api_endpoints.py
└── e2e/
    ├── test_tier1_features.py      # Tier 1: Feature Coverage (>=5 per feature)
    ├── test_tier2_boundaries.py    # Tier 2: Boundary & Corner Cases
    ├── test_tier3_combinations.py  # Tier 3: Cross-Feature Interactions
    ├── test_tier4_scenarios.py     # Tier 4: Real-World Ingestion & Querying Workloads
    └── test_tier5_adversarial.py   # Tier 5: Adversarial Hardening
verify_e2e.py                       # CLI demo script for end-to-end verification
```
