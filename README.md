# Fan-Zone ⚽🏀 — Israeli Sports News Backend & AI Story Hub

Backend service that continuously monitors Israeli sports news sources, clusters related articles into unified stories, generates original non-clickbait Hebrew summaries with AI (Gemini), automatically tags sports entities, and provides a personalized fan feed API with copyright compliance.

---

## 🌟 Features

- **Multi-Source Ingestion**: Monitors 7 major Israeli sports news sites:
  - **Sport5** (sport5.co.il)
  - **ONE** (one.co.il)
  - **Walla! Sports** (sports.walla.co.il)
  - **Ynet Sport** (ynet.co.il/sport)
  - **Sport1** (sport1.maariv.co.il)
  - **Israel Hayom** (israelhayom.co.il/sport)
  - **Haaretz Sport** (haaretz.co.il/sport)
- **Per-Source Deduplication**: Canonical URL normalization and SHA-256 content hashing scoped per source so identical stories on different sites remain distinct inputs for clustering.
- **Copyright Safe**: Raw third-party article bodies and images remain internal for processing only. End users receive original AI-synthesized summaries with outbound source links.
- **Story Clustering**: Automatically detects and groups articles from different outlets reporting on the same real-world event/match into a single Story.
- **Google Gemini AI Synthesis**:
  - Non-clickbait headline & 1-2 sentence subheadline rewriting.
  - Multi-source fact synthesis into an objective Hebrew summary.
  - 5-Dimensional entity classification: sport, 	eams, players, competition, 	ags.
  - Structured outbound source citations with clickable links for further reading.
  - Built-in retry handling with exponential backoff and rule-based / offline mock fallbacks.
- **Personalized Fan Feed API**:
  - Filter stories by custom fan preferences (multiple sports, favorite teams, leagues, keywords).
  - Search and discover available tags and categories.
- **Background Scheduler**: Configurable async poller for periodic background ingestion.

---

## 📁 Repository Structure

`
fan-zone/
├── fan_zone/                     # Main application package
│   ├── ai/                       # Gemini AI client, prompts, structured output & mock fallbacks
│   ├── api/                      # FastAPI application & v1 REST routers
│   │   └── v1/                   # Endpoints: feed, stories, articles, sources, tags, ingest, system
│   ├── db/                       # Database engine and async session factories
│   ├── models/                   # SQLAlchemy 2.0 ORM models (Story, Article, Source, Tag, Media)
│   ├── repositories/             # Async database repositories for queries & filters
│   ├── scheduler/                # Background async poller & scheduler
│   ├── schemas/                  # Pydantic schemas for request/response validation
│   ├── scrapers/                 # 7 Israeli sports scrapers & base scraper
│   ├── services/                 # Ingestion & Story clustering/synthesis services
│   ├── config.py                 # Pydantic settings management
│   └── main.py                   # FastAPI entrypoint
├── docs/                         # Specifications & technical documentation
│   ├── PROJECT_SPEC.md           # Full system architecture & feature specification
│   └── REQUIREMENTS.md           # Product requirements & user stories
├── tests/                        # Comprehensive test suite (343 tests)
│   ├── unit/                     # Unit tests (models, repositories, AI, scrapers, deduplication)
│   ├── integration/              # Integration tests (API endpoints, ingestion service, scheduler)
│   └── e2e/                      # End-to-end tiers 1-5 test suites
├── .env.example                  # Environment variables template
├── requirements.txt              # Python dependencies
└── verify_e2e.py                 # E2E pipeline verification script
`

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- (Optional) PostgreSQL database (SQLite is supported out of the box for local development)
- Google Gemini API Key

### 2. Installation
Clone the repository and install dependencies:

`ash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
`

### 3. Configuration
Copy .env.example to .env and fill in your settings:

`ash
cp .env.example .env
`

Key environment variables:
`nv
GEMINI_API_KEY=your_google_gemini_api_key
DATABASE_URL=sqlite+aiosqlite:///./fan_zone.db
LOG_LEVEL=INFO
POLL_INTERVAL_SECONDS=300
`

---

## 🏃 Running the Application

### Start the FastAPI Server
`ash
uvicorn fan_zone.main:app --reload --port 8000
`

Once running:
- **Interactive Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Health Check**: [http://localhost:8000/api/v1/system/health](http://localhost:8000/api/v1/system/health)

---

## 📡 REST API Overview

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/v1/feed | **Personalized Fan Feed** — filter by sports, 	eams, competitions, 	ags, q |
| GET | /api/v1/stories/{id} | Get synthesized story with Hebrew summary, tags, and source citations |
| GET | /api/v1/stories | List all synthesized stories with pagination |
| GET | /api/v1/tags | Discover available sports, teams, leagues, and tags for frontend pickers |
| GET | /api/v1/sources | List all 7 monitored Israeli sports sources |
| POST | /api/v1/ingest/trigger | Trigger manual scraping & processing for a specific source or URL |
| GET | /api/v1/system/health | System health check and ingestion statistics |

---

## 🧪 Testing & Verification

### Run the Full Test Suite
`ash
pytest -v
`

### Run the E2E CLI Demo Script
`ash
python verify_e2e.py
`
Demonstrates all 7 operational phases:
1. Source initialization
2. Multi-source scraping
3. Per-source deduplication
4. Story clustering across outlets
5. Gemini AI synthesis, non-clickbait title generation & entity classification
6. Database storage & relationship persistence
7. Personalized fan feed API querying & filtering
