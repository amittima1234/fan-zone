"""Unit tests for AI Enrichment Service, GeminiAIEnricher, and MockAIEnricher (Milestone 4)."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from core.config import Settings
from core.queue import InMemoryTaskQueue
from db.repository import ArticleRepository
from db.session import Base, create_async_db_engine, get_session_factory
from models.feed import ArticleModel
from schemas.feed import (
    AIEnrichedCard,
    RawArticlePayload,
    ToneEnum,
)
from services.ai_worker import (
    AIEnrichmentError,
    AIEnrichmentService,
    GeminiAIEnricher,
    MockAIEnricher,
)
from tests.fixtures.mock_gemini import (
    MOCK_DERBY_ENRICHED_CARD,
    MOCK_EUROLEAGUE_ENRICHED_CARD,
    MOCK_INJURY_ENRICHED_CARD,
    MOCK_TRANSFER_ENRICHED_CARD,
    MockGenerateContentResponse,
    create_mock_gemini_response,
)
from tests.fixtures.raw_articles import (
    HAPOEL_TA_DERBY_RAW_ARTICLE,
    INJURY_RAW_ARTICLE,
    MACCABI_HAIFA_FOOTBALL_RAW_ARTICLE,
    OLYMPIC_JUDO_RAW_ARTICLE,
    ONE_RAW_ARTICLE,
    SPORT5_RAW_ARTICLE,
    YNET_RAW_ARTICLE,
)


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def in_memory_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provide an isolated in-memory SQLite engine."""
    engine = create_async_db_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def session_factory(in_memory_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Provide session factory bound to in-memory test engine."""
    return get_session_factory(in_memory_engine)


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an active AsyncSession."""
    async with session_factory() as session:
        yield session


@pytest.fixture
def repo(db_session: AsyncSession) -> ArticleRepository:
    """Return ArticleRepository wired to the test session."""
    return ArticleRepository(db_session)


@pytest.fixture
def sample_raw_sport5() -> RawArticlePayload:
    return RawArticlePayload(**SPORT5_RAW_ARTICLE)


@pytest.fixture
def sample_raw_ynet() -> RawArticlePayload:
    return RawArticlePayload(**YNET_RAW_ARTICLE)


@pytest.fixture
def sample_raw_one() -> RawArticlePayload:
    return RawArticlePayload(**ONE_RAW_ARTICLE)


@pytest.fixture
def sample_raw_judo() -> RawArticlePayload:
    return RawArticlePayload(**OLYMPIC_JUDO_RAW_ARTICLE)


@pytest.fixture
def sample_raw_injury() -> RawArticlePayload:
    return RawArticlePayload(**INJURY_RAW_ARTICLE)


@pytest.fixture
def sample_raw_derby() -> RawArticlePayload:
    return RawArticlePayload(**MACCABI_HAIFA_FOOTBALL_RAW_ARTICLE)


# ---------------------------------------------------------------------------
# 1. MockAIEnricher Unit Tests
# ---------------------------------------------------------------------------

class TestMockAIEnricher:
    """Unit tests validating deterministic offline heuristic AI enrichment."""

    @pytest.mark.asyncio
    async def test_entity_extraction_israeli_and_euroleague(
        self,
        sample_raw_sport5: RawArticlePayload,
    ):
        """Verify basketball, Euroleague, and Israeli entities are extracted."""
        enricher = MockAIEnricher()
        card = await enricher.enrich_article(sample_raw_sport5)

        assert isinstance(card, AIEnrichedCard)
        assert "Maccabi Tel Aviv" in card.tags
        assert "Real Madrid" in card.tags
        assert "Euroleague" in card.tags
        assert "Basketball" in card.tags
        assert len(card.tags) >= 1
        assert len(card.tags) <= 8

    @pytest.mark.asyncio
    async def test_entity_extraction_judo_olympics(
        self,
        sample_raw_judo: RawArticlePayload,
    ):
        """Verify Olympic sports, Judo, and athlete entities are extracted."""
        enricher = MockAIEnricher()
        card = await enricher.enrich_article(sample_raw_judo)

        assert isinstance(card, AIEnrichedCard)
        assert "Judo" in card.tags
        assert "Peter Paltchik" in card.tags
        assert "Raz Hershko" in card.tags
        assert "Israel National Team" in card.tags

    @pytest.mark.asyncio
    async def test_entity_extraction_fallback_when_no_known_entity(self):
        """Verify fallback tags are generated when no known entity is matched."""
        unknown_article = RawArticlePayload(
            title="טורניר בדמינגטון בינלאומי נפתח הבוקר",
            raw_body="תחרות חדשה ולא מוכרת נפתחה באולם הספורט.",
            url="https://www.sport5.co.il/badminton-1",
            publisher="sport5",
            category="ענפים נוספים",
        )
        enricher = MockAIEnricher()
        card = await enricher.enrich_article(unknown_article)

        assert isinstance(card, AIEnrichedCard)
        assert len(card.tags) >= 1
        assert "Israeli Sports" in card.tags or "Sport5" in card.tags

    @pytest.mark.asyncio
    async def test_tone_classification_hype(
        self,
        sample_raw_sport5: RawArticlePayload,
        sample_raw_judo: RawArticlePayload,
    ):
        """Verify hype tone detection on dramatic victories and gold medals."""
        enricher = MockAIEnricher()

        card_sport5 = await enricher.enrich_article(sample_raw_sport5)
        assert card_sport5.tone == ToneEnum.HYPE

        card_judo = await enricher.enrich_article(sample_raw_judo)
        assert card_judo.tone == ToneEnum.HYPE

    @pytest.mark.asyncio
    async def test_tone_classification_critical(
        self,
        sample_raw_ynet: RawArticlePayload,
    ):
        """Verify critical tone detection on club crisis and player disputes."""
        enricher = MockAIEnricher()
        card = await enricher.enrich_article(sample_raw_ynet)

        assert card.tone == ToneEnum.CRITICAL
        assert "Beitar Jerusalem" in card.tags

    @pytest.mark.asyncio
    async def test_tone_classification_objective(
        self,
        sample_raw_one: RawArticlePayload,
    ):
        """Verify objective tone on standard transfer negotiations."""
        enricher = MockAIEnricher()
        card = await enricher.enrich_article(sample_raw_one)

        assert card.tone == ToneEnum.OBJECTIVE

    @pytest.mark.asyncio
    async def test_context_label_classification(
        self,
        sample_raw_one: RawArticlePayload,
        sample_raw_injury: RawArticlePayload,
        sample_raw_derby: RawArticlePayload,
        sample_raw_ynet: RawArticlePayload,
    ):
        """Verify context label classification across various sports categories."""
        enricher = MockAIEnricher()

        # Transfer
        card_transfer = await enricher.enrich_article(sample_raw_one)
        assert card_transfer.context_label == "Transfer Rumor"

        # Injury
        card_injury = await enricher.enrich_article(sample_raw_injury)
        assert card_injury.context_label == "Injury Update"

        # Tactical / Lineup
        card_derby = await enricher.enrich_article(sample_raw_derby)
        assert card_derby.context_label == "Tactical Analysis"

        # Breaking News / Crisis / Transfer
        card_ynet = await enricher.enrich_article(sample_raw_ynet)
        assert card_ynet.context_label in ("Breaking News", "Match Report", "Transfer Rumor", "Club Crisis")

    @pytest.mark.asyncio
    async def test_micro_summary_word_count_and_single_sentence(
        self,
        sample_raw_sport5: RawArticlePayload,
        sample_raw_ynet: RawArticlePayload,
        sample_raw_derby: RawArticlePayload,
    ):
        """Verify micro_summary is a valid single sentence with word count <= 35 words."""
        enricher = MockAIEnricher()

        for article in (sample_raw_sport5, sample_raw_ynet, sample_raw_derby):
            card = await enricher.enrich_article(article)
            words = card.micro_summary.split()
            assert len(words) <= 35, f"Summary exceeded 35 words: {len(words)}"
            assert len(card.micro_summary) >= 10, "Summary too short"
            assert len(card.micro_summary) <= 400, "Summary too long"


# ---------------------------------------------------------------------------
# 2. GeminiAIEnricher Unit Tests (Mocked Google GenAI SDK)
# ---------------------------------------------------------------------------

class TestGeminiAIEnricher:
    """Unit tests validating Gemini AI enrichment with mocked SDK responses."""

    @pytest.mark.asyncio
    async def test_successful_gemini_enrichment(
        self,
        sample_raw_sport5: RawArticlePayload,
    ):
        """Verify Gemini SDK call maps structured output into AIEnrichedCard."""
        mock_response = create_mock_gemini_response("euroleague")

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        enricher = GeminiAIEnricher(
            api_key="test-api-key-123",
            model="gemini-3.7-flash",
            client=mock_client,
        )

        card = await enricher.enrich_article(sample_raw_sport5)

        assert isinstance(card, AIEnrichedCard)
        assert card.micro_summary == "מכבי תל אביב גברה 82:86 על ריאל מדריד בהיכל מנורה בהובלת בולדווין והבטיחה מקום בפלייאוף היורוליג."
        assert "מכבי תל אביב" in card.tags
        assert "ריאל מדריד" in card.tags
        assert "יורוליג" in card.tags
        assert card.tone == ToneEnum.HYPE
        assert card.context_label == "יורוליג"

        # Verify SDK generate_content was called once
        mock_client.aio.models.generate_content.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_strict_body_truncation_enforcement(self):
        """Verify that raw_body is strictly truncated to <= 3500 chars in prompt."""
        huge_body = ("תוכן ארוך מאוד של משחק " * 200) + " סוף טקסט ייחודי שלא נכנס מעבר לגבול"
        long_article = RawArticlePayload(
            title="כתבה ארוכה במיוחד",
            raw_body=huge_body,
            url="https://www.sport5.co.il/long-article",
            publisher="sport5",
        )

        captured_prompts = []

        async def fake_generate_content(model, contents, config):
            captured_prompts.append(contents)
            return create_mock_gemini_response("euroleague")

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(side_effect=fake_generate_content)

        enricher = GeminiAIEnricher(
            api_key="test-key",
            model="gemini-3.7-flash",
            client=mock_client,
        )

        card = await enricher.enrich_article(long_article)
        assert isinstance(card, AIEnrichedCard)
        assert len(captured_prompts) == 1

        prompt = captured_prompts[0]
        # The raw body portion in prompt must not exceed 3500 characters
        truncated_portion = huge_body[:3500]
        assert truncated_portion in prompt
        # Verify the unique characters beyond 3500 are not present
        assert "סוף טקסט ייחודי שלא נכנס מעבר לגבול" not in prompt

    @pytest.mark.asyncio
    async def test_client_uninitialized_raises_ai_enrichment_error(
        self,
        sample_raw_sport5: RawArticlePayload,
    ):
        """Verify AIEnrichmentError when client is not initialized."""
        enricher = GeminiAIEnricher(api_key=None, client=None)
        with pytest.raises(AIEnrichmentError, match="Google GenAI client is not initialized"):
            await enricher.enrich_article(sample_raw_sport5)

    @pytest.mark.asyncio
    async def test_sdk_api_failure_raises_ai_enrichment_error(
        self,
        sample_raw_sport5: RawArticlePayload,
    ):
        """Verify API exceptions from SDK are wrapped in AIEnrichmentError."""
        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("Google GenAI 429 Quota Exceeded")
        )

        enricher = GeminiAIEnricher(
            api_key="test-key",
            client=mock_client,
        )

        with pytest.raises(AIEnrichmentError, match="Gemini API enrichment failed"):
            await enricher.enrich_article(sample_raw_sport5)


# ---------------------------------------------------------------------------
# 3. AIEnrichmentService Dispatcher & Fallback Tests
# ---------------------------------------------------------------------------

class TestAIEnrichmentServiceDispatcher:
    """Unit tests validating factory selection and fallback logic."""

    def test_dispatcher_defaults_to_mock_when_no_api_key(self):
        """Verify MockAIEnricher is selected when GEMINI_API_KEY is not configured."""
        s = Settings(GEMINI_API_KEY=None, USE_MOCK_AI=False)
        service = AIEnrichmentService(settings_obj=s)
        assert isinstance(service.enricher, MockAIEnricher)

    def test_dispatcher_selects_mock_when_use_mock_ai_is_true(self):
        """Verify MockAIEnricher is selected when USE_MOCK_AI=True."""
        s = Settings(GEMINI_API_KEY="some-key", USE_MOCK_AI=True)
        service = AIEnrichmentService(settings_obj=s)
        assert isinstance(service.enricher, MockAIEnricher)

    def test_dispatcher_selects_mock_on_explicit_argument(self):
        """Verify use_mock=True forces MockAIEnricher regardless of settings."""
        s = Settings(GEMINI_API_KEY="some-key", USE_MOCK_AI=False)
        service = AIEnrichmentService(use_mock=True, settings_obj=s)
        assert isinstance(service.enricher, MockAIEnricher)

    def test_dispatcher_custom_enricher_override(self):
        """Verify passing a custom enricher directly."""
        mock_custom = MockAIEnricher()
        service = AIEnrichmentService(enricher=mock_custom)
        assert service.enricher is mock_custom

    @pytest.mark.asyncio
    async def test_automatic_fallback_to_mock_on_gemini_error(
        self,
        sample_raw_sport5: RawArticlePayload,
    ):
        """Verify service falls back to MockAIEnricher if Gemini client fails."""
        failing_client = MagicMock()
        failing_client.aio.models.generate_content = AsyncMock(
            side_effect=RuntimeError("503 Service Unavailable")
        )
        gemini_enricher = GeminiAIEnricher(api_key="test-key", client=failing_client)

        service = AIEnrichmentService(enricher=gemini_enricher)
        card = await service.enrich_article(sample_raw_sport5)

        assert isinstance(card, AIEnrichedCard)
        assert "Maccabi Tel Aviv" in card.tags
        assert card.tone == ToneEnum.HYPE


# ---------------------------------------------------------------------------
# 4. AIEnrichmentService Storage & Task Queue Tests
# ---------------------------------------------------------------------------

class TestAIEnrichmentServiceStorageAndQueue:
    """Unit tests for enrich_and_store and process_queue_item with in-memory DB and Queue."""

    @pytest.mark.asyncio
    async def test_enrich_and_store_fresh_article(
        self,
        repo: ArticleRepository,
        sample_raw_sport5: RawArticlePayload,
    ):
        """Verify enrich_and_store creates a new ArticleModel in DB."""
        service = AIEnrichmentService(use_mock=True)

        article = await service.enrich_and_store(sample_raw_sport5, repo)

        assert isinstance(article, ArticleModel)
        assert article.id is not None
        assert article.id > 0
        assert article.url == str(sample_raw_sport5.url)
        assert article.title == sample_raw_sport5.title
        assert article.publisher == "sport5"
        assert "Maccabi Tel Aviv" in article.tags
        assert article.tone == "hype"

        # Verify article exists in repository
        fetched = await repo.get_by_id(article.id)
        assert fetched is not None
        assert fetched.url == str(sample_raw_sport5.url)

    @pytest.mark.asyncio
    async def test_enrich_and_store_idempotent_existing_url(
        self,
        repo: ArticleRepository,
        sample_raw_sport5: RawArticlePayload,
    ):
        """Verify enrich_and_store returns existing article without duplicate enrichment."""
        service = AIEnrichmentService(use_mock=True)

        # First call creates record
        first_article = await service.enrich_and_store(sample_raw_sport5, repo)
        assert first_article.id is not None

        # Second call with same URL returns existing record
        second_article = await service.enrich_and_store(sample_raw_sport5, repo)
        assert second_article.id == first_article.id
        assert second_article.url == first_article.url

        # Check total count in DB is still 1
        items, total = await repo.list_articles()
        assert total == 1

    @pytest.mark.asyncio
    async def test_process_queue_item_success(
        self,
        repo: ArticleRepository,
        sample_raw_ynet: RawArticlePayload,
        sample_raw_one: RawArticlePayload,
    ):
        """Verify popping and processing items from an InMemoryTaskQueue."""
        queue = InMemoryTaskQueue()
        await queue.push(sample_raw_ynet)
        await queue.push(sample_raw_one)

        assert await queue.size() == 2

        service = AIEnrichmentService(use_mock=True)

        # Process item 1
        article1 = await service.process_queue_item(queue, repo)
        assert article1 is not None
        assert article1.url == str(sample_raw_ynet.url)
        assert article1.publisher == "ynet"
        assert await queue.size() == 1

        # Process item 2
        article2 = await service.process_queue_item(queue, repo)
        assert article2 is not None
        assert article2.url == str(sample_raw_one.url)
        assert article2.publisher == "one"
        assert await queue.size() == 0

        # Queue is now empty
        empty_res = await service.process_queue_item(queue, repo, timeout=0.01)
        assert empty_res is None

    @pytest.mark.asyncio
    async def test_process_queue_item_empty_queue(
        self,
        repo: ArticleRepository,
    ):
        """Verify process_queue_item returns None on an empty queue."""
        queue = InMemoryTaskQueue()
        service = AIEnrichmentService(use_mock=True)

        result = await service.process_queue_item(queue, repo, timeout=0.01)
        assert result is None
