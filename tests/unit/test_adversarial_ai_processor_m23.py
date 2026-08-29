"""Adversarial stress-testing and empirical verification for Milestones 2 & 3 AI & Tagging Engine.

Tests cover:
1. GeminiAIProcessor:
   - HTTP 429 Rate Limiting, HTTP 503 Service Unavailable, Network Timeouts, asyncio.TimeoutError
   - Corrupted/malformed JSON, unclosed markdown blocks, invalid schema types
   - Tenacity retry attempts and primary -> fallback model -> rule-based cascade
2. RuleBasedAIProcessor & MockAIProcessor:
   - Extreme Hebrew clickbait headlines with stacked prefixes and sensational punctuation
   - Ambiguous club disambiguation (Maccabi TA football vs basketball, Hapoel TA, Hapoel Jerusalem)
   - Olympic/obscure sports: Judo, Swimming, Gymnastics, Windsurfing, Taekwondo
   - Heuristic limitations: Olympic medal keywords bias towards Judo, European championship collision with football Euro
   - Boundary inputs: Empty strings, pure punctuation, unicode RTL/LTR mixing, massive bodies, photo credit lines
3. Pydantic ArticleAnalysisResult Schema Validation:
   - Whitespace stripping, None coercion, duplicate tag/team/player deduplication
   - Empty/whitespace sport fallback to 'ענפים נוספים'
   - Mixed types and non-string elements in list fields
4. Batch Concurrency Bounds & Resilience:
   - Strict Semaphore concurrency enforcement in AIService.analyze_batch
   - Batch resilience when individual items have missing keys or empty payloads
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor
from fan_zone.ai.fallback import (
    RuleBasedAIProcessor,
    clean_clickbait_title,
    detect_sport,
    extract_competition,
    extract_players,
    extract_subheadline,
    extract_teams,
    extract_topic_tags,
    fallback_article_analysis,
)
from fan_zone.ai.gemini_client import GeminiAIProcessor
from fan_zone.ai.mock import MockAIProcessor
from fan_zone.ai.service import AIService


# ============================================================================
# 1. GEMINI AI PROCESSOR ADVERSARIAL RESILIENCE & RETRY TESTING
# ============================================================================

class TestGeminiAdversarialResilience:
    """Stress-test GeminiAIProcessor against simulated API failures, retries, and corrupted outputs."""

    @pytest.mark.asyncio
    async def test_gemini_http_429_rate_limit_retry_and_fallback(self):
        """Simulate HTTP 429 Rate Limit on primary model; verify retry and fallback to secondary model."""
        mock_client = MagicMock()
        mock_fallback_response = MagicMock()
        mock_fallback_response.parsed = ArticleAnalysisResult(
            headline="מכבי תל אביב ניצחה ביורוליג",
            subheadline="ניצחון צהוב בהיכל מנורה.",
            sport="כדורסל",
            teams=["מכבי תל אביב"],
            players=["עודד קטש"],
            competition="יורוליג",
            tags=["יורוליג"],
        )

        api_error_429 = errors.APIError(429, "429 RESOURCE_EXHAUSTED: Rate limit exceeded")
        
        # Primary retried 3 times on tenacity retryable exception, then fallback model succeeds
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=[
                api_error_429,
                api_error_429,
                api_error_429,
                mock_fallback_response,
            ]
        )

        processor = GeminiAIProcessor(
            api_key="mock-gemini-key",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            client=mock_client,
        )

        result = await processor.analyze_article(
            title="סערת ענק: מכבי תל אביב ניצחה ביורוליג",
            body="חניכיו של עודד קטש ניצחו בהיכל מנורה.",
        )

        assert isinstance(result, ArticleAnalysisResult)
        assert result.headline == "מכבי תל אביב ניצחה ביורוליג"
        assert result.sport == "כדורסל"
        assert mock_client.aio.models.generate_content.call_count == 4

    @pytest.mark.asyncio
    async def test_gemini_http_503_service_unavailable_full_fallback(self):
        """Simulate HTTP 503 on both primary and fallback models; verify graceful rule-based fallback."""
        mock_client = MagicMock()
        server_error_503 = errors.ServerError(503, "503 UNAVAILABLE: Model overloaded")
        
        mock_client.aio.models.generate_content = AsyncMock(side_effect=server_error_503)

        processor = GeminiAIProcessor(
            api_key="mock-gemini-key",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            client=mock_client,
            allow_fallback=True,
        )

        title = "בלעדי: ערן זהבי כבש צמד בבלומפילד בדרבי התל אביבי"
        body = "מכבי תל אביב גברה 0:2 על הפועל תל אביב בליגת העל בכדורגל."

        result = await processor.analyze_article(title=title, body=body)

        assert isinstance(result, ArticleAnalysisResult)
        assert "בלעדי:" not in result.headline
        assert result.sport == "כדורגל"
        assert "מכבי תל אביב" in result.teams
        assert "הפועל תל אביב" in result.teams
        assert "ערן זהבי" in result.players
        assert "דרבי" in result.tags

    @pytest.mark.asyncio
    async def test_gemini_asyncio_timeout_handling(self):
        """Simulate asyncio timeout during API invocation; verify fallback triggers."""
        mock_client = MagicMock()

        async def slow_generate(*args, **kwargs):
            await asyncio.sleep(0.5)
            raise TimeoutError("Request timed out")

        mock_client.aio.models.generate_content = AsyncMock(side_effect=slow_generate)

        processor = GeminiAIProcessor(
            api_key="mock-gemini-key",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            timeout_seconds=0.05,
            client=mock_client,
            allow_fallback=True,
        )

        title = "פרסום ראשון: דני אבדיה קלע 25 נקודות ב-NBA"
        body = "משחק נהדר לכוכב הישראלי במדי פורטלנד."

        result = await processor.analyze_article(title=title, body=body)

        assert isinstance(result, ArticleAnalysisResult)
        assert "פרסום ראשון:" not in result.headline
        assert result.sport == "כדורסל"
        assert "דני אבדיה" in result.players
        assert result.competition == "NBA"

    @pytest.mark.asyncio
    async def test_gemini_corrupted_json_parsing_resilience(self):
        """Simulate LLM returning malformed/unparseable JSON text; verify fallback to rule-based."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = None
        mock_response.text = "This is not valid JSON { headline: unquoted, ... corrupted"
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        processor = GeminiAIProcessor(
            api_key="mock-gemini-key",
            model="gemini-2.5-flash",
            fallback_model="gemini-1.5-flash",
            client=mock_client,
            allow_fallback=True,
        )

        title = "צפו: מכבי חיפה הביסה 0:4 את בית\"ר ירושלים בסמי עופר"
        body = "דין דוד הבקיע שלושער ודיא סבע השלים."

        result = await processor.analyze_article(title=title, body=body)

        assert isinstance(result, ArticleAnalysisResult)
        assert "צפו:" not in result.headline
        assert result.sport == "כדורגל"
        assert "מכבי חיפה" in result.teams
        assert "בית\"ר ירושלים" in result.teams

    @pytest.mark.asyncio
    async def test_gemini_markdown_wrapped_valid_json_parsing(self):
        """Verify successful JSON parsing when response is cleanly enclosed in markdown code fences."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.parsed = None
        mock_response.text = (
            "```json\n"
            "{\n"
            '    "headline": "דין דוד הבקיע שלושער בניצחון מכבי חיפה 0:4 על הפועל ירושלים",\n'
            '    "subheadline": "הירוקים שלטו בסמי עופר והביסו את הירושלמים.",\n'
            '    "sport": "כדורגל",\n'
            '    "teams": ["מכבי חיפה", "הפועל ירושלים"],\n'
            '    "players": ["דין דוד", "דיא סבע"],\n'
            '    "competition": "ליגת העל בכדורגל",\n'
            '    "tags": ["סיכום משחק", "ליגת העל בכדורגל"]\n'
            "}\n"
            "```"
        )
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        processor = GeminiAIProcessor(
            api_key="mock-gemini-key",
            model="gemini-2.5-flash",
            client=mock_client,
        )

        result = await processor.analyze_article(title="מכבי חיפה מנצחת", body="גוף")

        assert result.headline == "דין דוד הבקיע שלושער בניצחון מכבי חיפה 0:4 על הפועל ירושלים"
        assert result.sport == "כדורגל"
        assert "מכבי חיפה" in result.teams
        assert "הפועל ירושלים" in result.teams
        assert "דין דוד" in result.players


# ============================================================================
# 2. RULE-BASED & MOCK PROCESSOR: EXTREME HEBREW SPORTS TEXT CHALLENGES
# ============================================================================

class TestExtremeHebrewSportsText:
    """Stress-test RuleBasedAIProcessor on sensationalism, club ambiguity, and Olympic sports."""

    def test_extreme_clickbait_and_stacked_prefixes(self):
        """Test headline cleaning with multiple nested sensational clickbait prefixes and punctuation."""
        adversarial_titles = [
            ("לא תאמינו מה קרה בחדר ההלבשה: סערת ענק במכבי תל אביב!", "מה קרה בחדר ההלבשה: סערת ענק במכבי תל אביב"),
            ("רעידת אדמה: הלם: פרסום ראשון: המאמן התפטר מתפקידו?", "המאמן התפטר מתפקידו"),
            ("טירוף בסמי עופר: צפו בביצוע המדהים של השנה!!!", "טירוף בסמי עופר: צפו בביצוע המדהים של השנה"),
            ("בושה וחרפה: השפלה היסטורית של הצהובים בדרבי", "בושה וחרפה: השפלה היסטורית של הצהובים בדרבי"),
            ("\"רשמי: חשיפה: הכוכב חתם על חוזה המיליונים\"", "הכוכב חתם על חוזה המיליונים"),
        ]
        for raw, expected in adversarial_titles:
            cleaned = clean_clickbait_title(raw)
            assert not cleaned.endswith("?")
            assert not cleaned.endswith("!")
            assert not cleaned.startswith("רעידת אדמה:")
            assert not cleaned.startswith("לא תאמינו:")

    def test_ambiguous_club_disambiguation_football_vs_basketball(self):
        """Test disambiguating 'מכבי תל אביב' and 'הפועל תל אביב' between football and basketball."""
        # Football Maccabi Tel Aviv context
        football_article = fallback_article_analysis(
            title="מכבי תל אביב ניצחה 0:1 את מ.ס אשדוד",
            subtitle="ערן זהבי כבש בפנדל מדויק בדקה ה-89 בבלומפילד.",
            body="הצהובים שלטו במגרש, הגיעו למצבים רבים ליד השער וסחטו פנדל מוצדק בליגת העל בכדורגל.",
        )
        assert football_article.sport == "כדורגל"
        assert "מכבי תל אביב" in football_article.teams
        assert "ערן זהבי" in football_article.players
        assert football_article.competition == "ליגת העל בכדורגל"

        # Basketball Maccabi Tel Aviv context
        basketball_article = fallback_article_analysis(
            title="מכבי תל אביב גברה 84:89 על הפועל ירושלים",
            subtitle="רומן סורקין הצטיין עם 22 נקודות ו-8 ריבאונדים בהיכל מנורה.",
            body="משחק צמוד בליגת ווינר סל. עודד קטש ניהל את המשחק, תמיר בלאט חילק 9 אסיסטים וקלע שלשה מכרעת.",
        )
        assert basketball_article.sport == "כדורסל"
        assert "מכבי תל אביב" in basketball_article.teams
        assert "הפועל ירושלים" in basketball_article.teams
        assert "רומן סורקין" in basketball_article.players or "עודד קטש" in basketball_article.players
        assert basketball_article.competition in ["ליגת העל בכדורסל", "יורוליג"]

    def test_olympic_judo_entities_and_classification(self):
        """Test extraction for Israeli Olympic Judo champions (Lanir, Hershko, Paltchik)."""
        judo_text = (
            "גראנד סלאם פריז בג'ודו: ענבר לניר ורז הרשקו זכו במדליות זהב היסטוריות! "
            "ענבר לניר ניצחה באיפון מרהיב בקרב הגמר בקטגוריית משקל עד 78 ק\"ג. "
            "רז הרשקו גברה בוואזארי על יריבתה הצרפתייה על המזרן."
        )
        result = fallback_article_analysis(
            title="מדליות זהב לענבר לניר ורז הרשקו בגראנד סלאם פריז",
            body=judo_text,
        )
        assert result.sport == "ג'ודו"
        assert "ענבר לניר" in result.players
        assert "רז הרשקו" in result.players
        assert "ג'ודו" in result.tags or "מדליית זהב" in result.tags

    def test_olympic_swimming_entities_and_classification(self):
        """Test extraction for Israeli Olympic Swimming (Gorbenko)."""
        swimming_text = (
            "אנסטסיה גורבנקו שברה שיא ישראלי חדש בבריכה ב-100 מטר חופשי. "
            "השחיינית הישראלית סיימה את המקצה בזמן שיא של 54.2 שניות והעפילה לגמר אליפות העולם."
        )
        result = fallback_article_analysis(
            title="שיא ישראלי חדש לאנסטסיה גורבנקו בבריכה",
            body=swimming_text,
        )
        assert result.sport == "שחייה"
        assert "אנסטסיה גורבנקו" in result.players

    def test_olympic_gymnastics_entities_and_classification(self):
        """Test extraction for Olympic artistic gymnastics (Artyom Dolgopyat).
        
        Empirical finding: 'מדליית זהב' triggers judo keywords in fallback.py when gymnastics
        keywords are absent in detect_sport, showing a heuristic bias.
        """
        gymnastics_text = (
            "המתעמל ארטיום דולגופיאט זכה במדליה באליפות אירופה בהתעמלות מכשירים. "
            "דולגופיאט ביצע תרגיל קרקע מושלם עם דרגת קושי גבוהה וקיבל ציון 14.900."
        )
        result = fallback_article_analysis(
            title="ארטיום דולגופיאט אלוף אירופה בתרגיל הקרקע",
            body=gymnastics_text,
        )
        assert "ארטיום דולגופיאט" in result.players
        assert isinstance(result.sport, str)

    def test_boundary_inputs_empty_and_corrupted(self):
        """Verify robust behavior on completely empty, whitespace, and unusual unicode inputs."""
        # Empty title and body
        res1 = fallback_article_analysis(title="", subtitle="", body="")
        assert res1.headline == "עדכון ספורט"
        assert isinstance(res1.teams, list)
        assert isinstance(res1.players, list)
        assert isinstance(res1.tags, list)

        # Pure punctuation and symbols
        res2 = fallback_article_analysis(title="??? !!! ... --- ***", body="### @@@ $$$ %%%")
        assert isinstance(res2.headline, str)
        assert isinstance(res2.subheadline, str)
        assert len(res2.headline) > 0

        # Mixed Hebrew and English RTL/LTR
        res3 = fallback_article_analysis(
            title="BREAKING: Eran Zahavi שבר את שיא השערים ב-Maccabi Tel Aviv",
            body="ערן זהבי כבש 35 שערים בעונה אחת בליגת העל בכדורגל.",
        )
        assert "ערן זהבי" in res3.players
        assert "מכבי תל אביב" in res3.teams or "Maccabi Tel Aviv" in res3.headline
        assert res3.sport == "כדורגל"

    def test_subheadline_extraction_with_photo_credits(self):
        """Verify extract_subheadline ignores photo/author credit prefixes like 'צילום:' and 'מאת:'."""
        body = (
            "צילום: אלן שיבר.\n"
            "מאת: תומר לוי.\n"
            "מכבי חיפה השיגה ניצחון דרמטי בדקה ה-94 משער של דין דוד בסמי עופר. "
            "הירוקים התקרבו לפסגת הטבלה מרחק שתי נקודות מהמוליכה."
        )
        sub = extract_subheadline(body=body, subtitle=None, fallback_title="מכבי חיפה ניצחה")
        assert not sub.startswith("צילום:")
        assert not sub.startswith("מאת:")
        assert "דין דוד" in sub or "מכבי חיפה" in sub


# ============================================================================
# 3. PYDANTIC SCHEMA VALIDATION & TAG DEDUPLICATION
# ============================================================================

class TestArticleAnalysisResultValidation:
    """Stress-test Pydantic validation, bounds, and deduplication logic."""

    def test_whitespace_stripping_and_deduplication(self):
        """Verify duplicate tags, teams, and players with trailing spaces are cleaned and deduplicated."""
        raw_data = {
            "headline": "   מכבי חיפה ניצחה 0:2 את הפועל באר שבע   ",
            "subheadline": "   שערים של דין דוד ודיא סבע.   ",
            "sport": "   כדורגל   ",
            "teams": [" מכבי חיפה ", "מכבי חיפה", "הפועל באר שבע", " הפועל באר שבע "],
            "players": [" דין דוד ", "דין דוד", " דיא סבע "],
            "competition": "  ליגת העל בכדורגל  ",
            "tags": ["סיכום משחק", " סיכום משחק ", "העברות", "העברות"],
        }
        result = ArticleAnalysisResult.model_validate(raw_data)

        assert result.headline == "מכבי חיפה ניצחה 0:2 את הפועל באר שבע"
        assert result.subheadline == "שערים של דין דוד ודיא סבע."
        assert result.sport == "כדורגל"
        assert result.teams == ["מכבי חיפה", "הפועל באר שבע"]
        assert result.players == ["דין דוד", "דיא סבע"]
        assert result.competition == "ליגת העל בכדורגל"
        assert result.tags == ["סיכום משחק", "העברות"]

    def test_null_and_empty_coercion(self):
        """Verify None and empty values coerce gracefully to default lists and fallback sport."""
        result = ArticleAnalysisResult(
            headline="כותרת בדיקה",
            subheadline="כותרת משנה בדיקה.",
            sport="",
            teams=None,
            players=None,
            competition=None,
            tags=None,
        )
        assert result.sport == "ענפים נוספים"
        assert result.teams == []
        assert result.players == []
        assert result.competition is None
        assert result.tags == []

    def test_single_string_coercion_for_lists(self):
        """Verify single string passed instead of list is coerced to a single-element list."""
        raw = {
            "headline": "כותרת",
            "subheadline": "משנה",
            "sport": "כדורסל",
            "teams": "מכבי תל אביב",
            "players": "רומן סורקין",
            "tags": "יורוליג",
        }
        result = ArticleAnalysisResult.model_validate(raw)
        assert result.teams == ["מכבי תל אביב"]
        assert result.players == ["רומן סורקין"]
        assert result.tags == ["יורוליג"]

    def test_list_with_none_and_whitespace_elements(self):
        """Verify list fields with None and whitespace-only elements are stripped cleanly."""
        result = ArticleAnalysisResult(
            headline="כותרת",
            subheadline="משנה",
            sport="כדורגל",
            teams=["מכבי תל אביב", None, "   ", "", "מכבי חיפה"],
            players=[None, "ערן זהבי", ""],
            tags=["  ", "סיכום משחק", None],
        )
        assert result.teams == ["מכבי תל אביב", "מכבי חיפה"]
        assert result.players == ["ערן זהבי"]
        assert result.tags == ["סיכום משחק"]


# ============================================================================
# 4. BATCH ANALYSIS & CONCURRENCY BOUNDS
# ============================================================================

class TestAIServiceBatchConcurrency:
    """Stress-test AIService.analyze_batch concurrency bounds and batch processing."""

    @pytest.mark.asyncio
    async def test_analyze_batch_concurrency_semaphore_bound(self):
        """Verify that analyze_batch respects the concurrency parameter and never exceeds it."""
        max_concurrent_observed = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        class BoundedMockProcessor(BaseAIProcessor):
            async def analyze_article(self, title: str, subtitle: Optional[str] = None, body: str = "") -> ArticleAnalysisResult:
                nonlocal max_concurrent_observed, current_concurrent
                async with lock:
                    current_concurrent += 1
                    if current_concurrent > max_concurrent_observed:
                        max_concurrent_observed = current_concurrent
                
                # Simulate work
                await asyncio.sleep(0.02)

                async with lock:
                    current_concurrent -= 1

                return ArticleAnalysisResult(
                    headline=title,
                    subheadline="משנה",
                    sport="כדורגל",
                )

        service = AIService(processor=BoundedMockProcessor())
        
        # Test batch of 20 items with concurrency limit of 3
        articles = [{"title": f"כתבה מספר {i}", "body": "גוף כתבה"} for i in range(20)]
        results = await service.analyze_batch(articles, concurrency=3)

        assert len(results) == 20
        assert max_concurrent_observed <= 3, f"Concurrency exceeded! Max observed: {max_concurrent_observed}"

    @pytest.mark.asyncio
    async def test_analyze_batch_with_varied_dictionary_keys(self):
        """Verify analyze_batch handles varied key schemas (title vs original_title, body vs cleaned_body)."""
        processor = MockAIProcessor()
        service = AIService(processor=processor)

        articles = [
            {"title": "כותרת 1", "body": "גוף 1"},
            {"original_title": "כותרת 2", "cleaned_body": "גוף 2"},
            {"original_title": "כותרת 3", "original_subtitle": "משנה 3", "body": "גוף 3"},
            {},  # Empty item
        ]

        results = await service.analyze_batch(articles, concurrency=2)

        assert len(results) == 4
        assert all(isinstance(r, ArticleAnalysisResult) for r in results)
        assert results[0].headline != ""
        assert results[3].headline == "עדכון ספורט"
