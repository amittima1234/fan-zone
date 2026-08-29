# Original User Request

## Initial Request — 2026-08-29T00:38:29+03:00

Backend service that continuously monitors Israeli sports news sources (Sport5, ONE, Walla! Sports, Ynet Sport, Sport1, Israel Hayom, Haaretz), extracts new articles with full body text and media URLs, generates clear non-clickbait Hebrew headlines and subheadlines using Google Gemini, automatically classifies and tags entities (sport category, club/team, players/personalities, league/tournament), and persists the processed articles, tags, and media metadata into a structured database.

Working directory: `c:\Users\amitt\git-projects\fan-zone`
Integrity mode: development

## Requirements

### R1. Multi-Source Sports News Ingestion & Parser
- Implement feed monitoring and scrapers for major Israeli sports outlets: Sport5, ONE, Walla! Sports, Ynet Sport, Sport1, Israel Hayom, and Haaretz.
- Extract complete article metadata and content: canonical URL, original title, published date, author, full body text paragraphs, and image URLs with metadata/captions.
- Implement robust deduplication (by URL / content hash) so already-processed articles are not re-fetched or duplicated.

### R2. Non-Clickbait AI Headline, Subheadline & Tag Extraction
- Integrate with Google Gemini API (using `google-genai` SDK) to analyze the Hebrew article body.
- Produce structured JSON output containing:
  1. An objective, informative, non-clickbait main headline (`headline`).
  2. A concise 1-2 sentence summarizing subheadline (`subheadline`).
  3. Extracted sports entity tags:
     - `sport` (e.g., כדורגל, כדורסל, טניס, ג'ודו, ענפים נוספים)
     - `teams` / `clubs` (e.g., מכבי תל אביב, מכבי חיפה, ריאל מדריד)
     - `players` / `personalities` (e.g., שחקנים, מאמנים, שופטים)
     - `competition` / `league` (e.g., ליגת העל, יורוליג, ליגת האלופות, NBA)
     - `tags` (any additional relevant topic keywords)
- Include retry handling and rate-limit resilience for API calls.

### R3. Data Models & Persistence Layer
- Implement database models using SQLAlchemy (supporting SQLite for local development and PostgreSQL via `.env` configuration).
- Store source information, original article content, extracted paragraphs, image URLs/metadata, generated non-clickbait titles, and extracted entity tags with appropriate relations/indexes for fast querying and filtering.
- Provide data access / repository methods for querying articles by source, tag, team, sport, date, or ID.

### R4. Background Scheduler & API Service
- Provide periodic polling (configurable interval) to automatically check for and ingest new articles.
- Provide FastAPI REST endpoints to:
  - List and search processed articles with pagination and filtering by sport, team, competition, or source.
  - Trigger manual ingestion / test runs for a given URL or source.
  - View service health, ingestion status, and available tags.

## Acceptance Criteria

### Ingestion & Parsing
- [ ] Feed parser correctly extracts articles from the configured Israeli sports sources.
- [ ] Extracted articles contain valid text paragraphs, publish timestamps, and image URLs without HTML artifacts.
- [ ] Duplicate articles are detected and skipped without error.

### AI Processing & Tagging
- [ ] Gemini client generates structured Hebrew headlines and subheadlines that summarize the article accurately and remove sensationalist/clickbait framing.
- [ ] Gemini extracts accurate entity tags (`sport`, `teams`, `players`, `competition`, `tags`) based on the article content.
- [ ] Errors in AI generation (network timeout, rate limit) are logged and handled without crashing the ingestion worker.

### Storage & API
- [ ] Articles, their associated image URLs, generated titles, and tags are stored in the database with proper relationships.
- [ ] FastAPI endpoints return paginated article lists with filtering support (by tag, sport, team, league, source) including both original and AI-generated headlines and image URLs.

### Verification & Testing
- [ ] Automated test suite verifies feed extraction, AI title generation & tagging logic (with mock/live modes), deduplication, and database CRUD operations with tag filtering.
- [ ] An end-to-end verification script demonstrates fetching, processing, tagging, storing, and querying at least one sample article.

## Follow-up — 2026-08-28T22:19:41Z

User Clarification on Deduplication:
Articles must be deduplicated PER SOURCE (per website URL / site), NOT globally across different news sites.
For example, if both Sport5 and Walla publish articles covering the same match/event, both articles MUST be ingested, processed, and saved independently in the database as separate articles without deduplicating across sources. Deduplication only applies to prevent re-ingesting the exact same article from the same source.

## Follow-up — 2026-08-28T22:43:55Z

CRITICAL SPECIFICATION UPDATE & PRODUCT EVOLUTION FROM USER:

The user has defined a legal/copyright-safe product architecture:
1. **Copyright & Media Constraints**:
   - Do NOT embed or serve original third-party images or display verbatim original article text to end-users.
   - Articles fetched from sources are strictly raw inputs for analysis and synthesis.

2. **Core Feature Evolution — Story Clustering & AI Synthesis**:
   - **Multi-source ingestion**: Fetch latest articles from the 7 Israeli sports sites.
   - **Story Clustering (Story Hub)**: Detect and group articles from different sites that cover the same event/match/story into a single "Story".
   - **AI Synthesis (Gemini)**: Synthesize each cluster into an original, objective, non-clickbait article/brief in Hebrew that synthesizes the facts and concludes with explicit source citations & outbound URLs for further reading / sharing.
   - **Entity Tagging**: Classify and tag each synthesized story by sport discipline, club/team, player/personality, competition/league.
   - **Personalized Fan Feed API**: Provide endpoints for fans to query/filter their personalized feed based on their chosen preferences (e.g., specific sports, teams, leagues).

Please integrate this story clustering, AI synthesis with source citations, and fan personalization feed into the data models, AI pipeline, and API endpoints!
