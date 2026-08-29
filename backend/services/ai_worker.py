"""AI enrichment service and worker for Fan Zone sports articles.

Integrates with Google GenAI SDK (gemini-3.7-flash) using structured outputs
constrained to the AIEnrichedCard Pydantic schema, with deterministic offline
MockAIEnricher fallback and queue-to-repository processing.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

from core.config import Settings, get_settings
from core.queue import BaseQueue
from db.repository import ArticleRepository
from models.feed import ArticleModel
from schemas.feed import (
    AIEnrichedCard,
    RawArticlePayload,
    ToneEnum,
)

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore
    GENAI_AVAILABLE = False


class AIEnrichmentError(Exception):
    """Raised when AI enrichment fails or produces invalid output."""

    pass


_UNSET: Any = object()


def _is_transient_gemini_error(exc: Exception) -> bool:
    """Return True if an exception represents a transient/retriable Gemini error (e.g. 503, 429, overload, timeout)."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True

    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code in (429, 500, 502, 503, 504, 529):
        return True

    err_str = str(exc).lower()
    transient_indicators = (
        "503",
        "429",
        "500",
        "502",
        "504",
        "529",
        "overloaded",
        "overload",
        "resource_exhausted",
        "resource exhausted",
        "rate limit",
        "rate_limit",
        "quota",
        "unavailable",
        "temporarily unavailable",
        "service unavailable",
        "deadline exceeded",
        "timeout",
        "connection reset",
        "try again",
        "high demand",
    )
    return any(indicator in err_str for indicator in transient_indicators)


class GeminiAIEnricher:
    """Live Google GenAI enrichment engine using Gemini Structured Outputs with retry on 503/overload."""

    def __init__(
        self,
        api_key: Optional[str] = _UNSET,
        model: Optional[str] = None,
        client: Optional[Any] = None,
        max_retries: Optional[int] = None,
        initial_delay: Optional[float] = None,
        backoff_factor: float = 2.0,
    ) -> None:
        cfg = get_settings()
        if api_key is _UNSET:
            self.api_key = cfg.GEMINI_API_KEY
        else:
            self.api_key = api_key

        self.model_name = model or cfg.GEMINI_MODEL or "gemini-3.7-flash"
        self.max_retries = max_retries if max_retries is not None else getattr(cfg, "GEMINI_MAX_RETRIES", 3)
        self.initial_delay = initial_delay if initial_delay is not None else getattr(cfg, "GEMINI_RETRY_DELAY_SECONDS", 2.0)
        self.backoff_factor = backoff_factor

        if client is not None:
            self.client = client
        elif GENAI_AVAILABLE and self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    async def enrich_article(self, article: RawArticlePayload) -> AIEnrichedCard:
        """Enrich a sports article using Google GenAI SDK with structured output constraints and 503 retries."""
        if self.client is None:
            raise AIEnrichmentError("Google GenAI client is not initialized or API key is missing")

        # Strictly enforce text truncation rule (<= 3500 characters)
        truncated_body = article.raw_body[:3500] if article.raw_body else ""
        publisher_name = (article.publisher or "Sports Portal").upper()

        prompt = f"""You are an expert Israeli sports journalist and analyst.
Analyze the following sports article from {publisher_name} and generate a structured enrichment card.

Article Title: {article.title}
Article Body:
{truncated_body}

Requirements:
1. micro_summary: A single-sentence, highly informative summary (max 30-40 words) capturing the key event, result, or news. Paraphrase factually without copying verbatim.
2. tags: List of specific entities mentioned: teams (e.g. 'Maccabi Tel Aviv', 'Hapoel Jerusalem', 'Real Madrid'), leagues/tournaments (e.g. 'Israeli Premier League', 'Euroleague', 'NBA'), athletes, or sports ('Football', 'Basketball'). Must contain at least 1 tag.
3. tone: Exactly one of: 'objective' (factual news/scores), 'hype' (excitement/derbies/buzzer-beaters), or 'critical' (tactical breakdown/manager pressure/controversies).
4. context_label: Short journalistic category: e.g. 'Match Report', 'Transfer Rumor', 'Injury Update', 'Tactical Analysis', 'Breaking News', 'Interview'.
"""

        # Build GenerateContentConfig using google.genai types if available
        config: Any
        if types is not None and hasattr(types, "GenerateContentConfig"):
            afc = types.AutomaticFunctionCallingConfig(disable=True) if hasattr(types, "AutomaticFunctionCallingConfig") else None
            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AIEnrichedCard,
                temperature=0.2,
                automatic_function_calling=afc,
            )
        else:
            config = {
                "response_mime_type": "application/json",
                "response_schema": AIEnrichedCard,
                "temperature": 0.2,
                "automatic_function_calling": {"disable": True},
            }

        attempt = 0
        current_delay = self.initial_delay

        while True:
            attempt += 1
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )

                # 1. Check if response has parsed attribute already containing the model or dict
                if hasattr(response, "parsed") and response.parsed is not None:
                    if isinstance(response.parsed, AIEnrichedCard):
                        return response.parsed
                    if isinstance(response.parsed, dict):
                        return AIEnrichedCard.model_validate(response.parsed)

                # 2. Check if response has text attribute containing JSON
                if hasattr(response, "text") and response.text:
                    return AIEnrichedCard.model_validate_json(response.text)

                # 3. If response is a dict directly
                if isinstance(response, dict):
                    return AIEnrichedCard.model_validate(response)

                raise AIEnrichmentError(f"Unexpected response structure from Gemini API: {response}")

            except Exception as e:
                if isinstance(e, AIEnrichmentError) and not _is_transient_gemini_error(e):
                    raise

                # If the error is 503 / overload / transient and we have remaining retries
                if attempt <= self.max_retries and _is_transient_gemini_error(e):
                    logger.warning(
                        "Gemini API 503/overload error for '%s' (attempt %d/%d): %s. Waiting %.1fs before retrying...",
                        article.title[:40],
                        attempt,
                        self.max_retries,
                        e,
                        current_delay,
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= self.backoff_factor
                    continue

                logger.error(
                    "Gemini AI enrichment failed for '%s' after %d attempt(s): %s",
                    article.title,
                    attempt,
                    e,
                )
                raise AIEnrichmentError(f"Gemini API enrichment failed: {e}") from e


class MockAIEnricher:
    """Deterministic offline AI enrichment engine for testing and local development.

    Extracts sports entities, journalistic tones, and context labels using
    comprehensive heuristic rules and an Israeli/international sports lexicon.
    """

    KNOWN_ENTITIES: Dict[str, str] = {
        # Israeli Football Teams
        "מכבי תל אביב": "Maccabi Tel Aviv",
        "מכבי ת\"א": "Maccabi Tel Aviv",
        "מכבי ת״א": "Maccabi Tel Aviv",
        "הפועל תל אביב": "Hapoel Tel Aviv",
        "הפועל ת\"א": "Hapoel Tel Aviv",
        "הפועל ת״א": "Hapoel Tel Aviv",
        "מכבי חיפה": "Maccabi Haifa",
        "בית\"ר ירושלים": "Beitar Jerusalem",
        "ביתר ירושלים": "Beitar Jerusalem",
        "בית״ר ירושלים": "Beitar Jerusalem",
        "הפועל באר שבע": "Hapoel Beer Sheva",
        "הפועל ב\"ש": "Hapoel Beer Sheva",
        "הפועל ב״ש": "Hapoel Beer Sheva",
        "הפועל ירושלים": "Hapoel Jerusalem",
        "מכבי נתניה": "Maccabi Netanya",
        "הפועל חיפה": "Hapoel Haifa",
        "עירוני קרית שמונה": "Ironi Kiryat Shmona",
        "קרית שמונה": "Ironi Kiryat Shmona" ,
        "קריית שמונה": "Ironi Kiryat Shmona",
        "מ.ס אשדוד": "FC Ashdod",
        "מ.ס. אשדוד": "FC Ashdod",
        "אשדוד": "FC Ashdod",
        "בני סכנין": "Bnei Sakhnin",
        "מכבי פתח תקווה": "Maccabi Petah Tikva",
        "מכבי פ\"ת": "Maccabi Petah Tikva",
        "הפועל פתח תקווה": "Hapoel Petah Tikva",
        "הפועל פ\"ת": "Hapoel Petah Tikva",
        "הפועל חדרה": "Hapoel Hadera",
        "מכבי בני ריינה": "Maccabi Bnei Reineh",
        "בני ריינה": "Maccabi Bnei Reineh",
        "עירוני טבריה": "Ironi Tiberias",
        "הפועל טבריה": "Ironi Tiberias",
        "הפועל קטמון": "Hapoel Katamon",

        # Israeli Basketball Teams
        "הפועל חולון": "Hapoel Holon",
        "חולון": "Hapoel Holon",
        "בני הרצליה": "Bnei Herzliya",
        "עירוני נס ציונה": "Ironi Ness Ziona",
        "נס ציונה": "Ironi Ness Ziona",
        "הפועל גליל עליון": "Hapoel Galil Elyon",
        "מכבי עירוני רמת גן": "Maccabi Ironi Ramat Gan",
        "עירוני רמת גן": "Maccabi Ironi Ramat Gan",
        "הפועל עפולה": "Hapoel Afula",
        "מכבי ראשון לציון": "Maccabi Rishon LeZion",

        # International Football & Basketball Clubs
        "ריאל מדריד": "Real Madrid",
        "ברצלונה": "Barcelona",
        "ליברפול": "Liverpool",
        "מנצ'סטר סיטי": "Manchester City",
        "מנצ'סטר יונייטד": "Manchester United",
        "ארסנל": "Arsenal",
        "באיירן מינכן": "Bayern Munich",
        "באיירן": "Bayern Munich",
        "פאריס סן ז'רמן": "PSG",
        "פריז סן ז'רמן": "PSG",
        "פ.ס.ז'": "PSG",
        "יובנטוס": "Juventus",
        "אינטר": "Inter Milan",
        "מילאן": "AC Milan",
        "צ'לסי": "Chelsea",
        "טוטנהאם": "Tottenham Hotspur",
        "אתלטיקו מדריד": "Atletico Madrid",
        "בורוסיה דורטמונד": "Borussia Dortmund",
        "דורטמונד": "Borussia Dortmund",
        "וושינגטון וויזארדס": "Washington Wizards",
        "וושינגטון": "Washington Wizards",
        "פורטלנד טרייל בלייזרס": "Portland Trail Blazers",
        "פורטלנד": "Portland Trail Blazers",
        "לוס אנג'לס לייקרס": "LA Lakers",
        "לייקרס": "LA Lakers",
        "בוסטון סלטיקס": "Boston Celtics",
        "גולדן סטייט": "Golden State Warriors",

        # Leagues & Tournaments
        "יורוליג": "Euroleague",
        "יורוקאפ": "EuroCup",
        "ליגת האלופות": "Champions League",
        "הליגה האירופית": "Europa League",
        "קונפרנס ליג": "Conference League",
        "ליגת העל": "Israeli Premier League",
        "ליגה לאומית": "Liga Leumit",
        "פרמייר ליג": "Premier League",
        "פרמיירליג": "Premier League",
        "לה ליגה": "La Liga",
        "סרייה א": "Serie A",
        "בונדסליגה": "Bundesliga",
        "אן.בי.אי": "NBA",
        "NBA": "NBA",
        "ליגת האומות": "Nations League",
        "מונדיאל": "World Cup",
        "יורו": "Euro",
        "גביע המדינה": "State Cup",
        "גביע הטוטו": "Toto Cup",

        # Sports Categories
        "כדורגל": "Football",
        "כדורסל": "Basketball",
        "ג'ודו": "Judo",
        "טניס": "Tennis",
        "שחייה": "Swimming",
        "אתלטיקה": "Athletics",
        "פורמולה 1": "Formula 1",
        "F1": "Formula 1",
        "כדוריד": "Handball",
        "כדורעף": "Volleyball",
        "ספורט אולימפי": "Olympic Sports",

        # Key Athletes & Personalities
        "דני אבדיה": "Deni Avdija",
        "מנור סולומון": "Manor Solomon",
        "אוסקר גלוך": "Oscar Gloukh",
        "ערן זהבי": "Eran Zahavi",
        "עומר אצילי": "Omer Atzili",
        "ברק בכר": "Barak Bakhar",
        "עודד קטש": "Oded Kattash",
        "ווייד בולדווין": "Wade Baldwin",
        "לורנזו בראון": "Lorenzo Brown",
        "פיטר פלצ'יק": "Peter Paltchik",
        "רז הרשקו": "Raz Hershko",
        "ענבר לניר": "Inbar Lanir",
        "שגיא מוקי": "Sagi Muki",
        "נבחרת ישראל": "Israel National Team",

        # English Names
        "maccabi tel aviv": "Maccabi Tel Aviv",
        "hapoel tel aviv": "Hapoel Tel Aviv",
        "maccabi haifa": "Maccabi Haifa",
        "beitar jerusalem": "Beitar Jerusalem",
        "hapoel beer sheva": "Hapoel Beer Sheva",
        "real madrid": "Real Madrid",
        "barcelona": "Barcelona",
        "liverpool": "Liverpool",
        "manchester city": "Manchester City",
        "euroleague": "Euroleague",
        "champions league": "Champions League",
        "premier league": "Premier League",
        "football": "Football",
        "basketball": "Basketball",
        "judo": "Judo",
        "tennis": "Tennis",
    }

    # Tone Lexicons
    HYPE_KEYWORDS: List[str] = [
        "דרמה",
        "ענק",
        "ענקי",
        "ענקית",
        "סנסציה",
        "מהפך",
        "טירוף",
        "ניצחון גדול",
        "ניצחון ענק",
        "ניצחון דרמטי",
        "היסטורי",
        "היסטורית",
        "חגיגה",
        "מדהים",
        "מרהיב",
        "שבר שיא",
        "אלופה",
        "תואר",
        "מדליית זהב",
        "זהב",
        "גולאסו",
        "הירואי",
        "הצגה",
        "לוהט",
        "תצוגת ענק",
        "buzzer-beater",
        "thriller",
        "sensational",
        "epic",
        "dramatic",
        "spectacular",
        "triumph",
        "miracle",
        "champion",
    ]

    CRITICAL_KEYWORDS: List[str] = [
        "משבר",
        "כישלון",
        "זעם",
        "זועמים",
        "הפסד כואב",
        "מפלה",
        "אכזבה",
        "פיטורים",
        "פוטר",
        "סערה",
        "תבוסה",
        "מבוכה",
        "הדחה",
        "מחאה",
        "השעיה",
        "ביקורת",
        "בלאגן",
        "קריסה",
        "זעזוע",
        "מכה",
        "עזיבה מיידית",
        "תביעה",
        "criticism",
        "crisis",
        "disaster",
        "failure",
        "fury",
        "outrage",
        "sacked",
        "fired",
        "defeat",
        "collapse",
        "disappointment",
    ]

    # Context Label Lexicons
    TRANSFER_KEYWORDS: List[str] = [
        "חתם",
        "מועמד",
        "סיכם",
        "מו\"מ",
        "מו״מ",
        "משא ומתן",
        "מעבר",
        "שחרור",
        "טרייד",
        "העברה",
        "העברות",
        "רכש",
        "הושאל",
        "החתים",
        "החתימה",
        "החתמתו",
        "מבוקש",
        "הצעה",
        "האריך חוזה",
        "חלון ההעברות",
        "הצטרף",
        "transfer",
        "rumor",
        "signing",
        "signs",
        "contract",
        "trade",
        "deal",
        "negotiations",
    ]

    INJURY_KEYWORDS: List[str] = [
        "פציעה",
        "פצוע",
        "נפצע",
        "ייעדר",
        "תיעדר",
        "קרע",
        "ניתוח",
        "החלים",
        "mri",
        "בדיקת mri",
        "קרסול",
        "ברך",
        "שבר",
        "כשירות",
        "רצועות",
        "פציעות",
        "injury",
        "injured",
        "out",
        "surgery",
        "recovery",
        "torn",
    ]

    TACTICAL_KEYWORDS: List[str] = [
        "ניתוח",
        "טקטי",
        "טקטיקה",
        "הרכב",
        "מערך",
        "פרשנות",
        "מדדים",
        "סטטיסטיקה",
        "מתלבט בהרכב",
        "מתלבט במערך",
        "חילוף",
        "analysis",
        "tactical",
        "tactics",
        "lineup",
        "formation",
        "breakdown",
    ]

    BREAKING_KEYWORDS: List[str] = [
        "מבזק",
        "ראשוני",
        "פרסום ראשון",
        "זעזוע",
        "התפטר",
        "הודעה רשמית",
        "רשמי",
        "הודיעו רשמית",
        "עזיבה מיידית",
        "breaking",
        "official",
        "alert",
    ]

    MATCH_KEYWORDS: List[str] = [
        "משחק",
        "מחזור",
        "סיכום",
        "הסתיים",
        "ניצחה",
        "גברה",
        "הפסידה",
        "תוצאה",
        "שערים",
        "נקודות",
        "גמר",
        "חצי גמר",
        "דרבי",
        "סמי עופר",
        "היכל מנורה",
        "טדי",
        "טוטו טרנר",
        "מחצית",
        "משחק עונה",
        "match",
        "game",
        "score",
        "recap",
        "derby",
    ]

    async def enrich_article(self, article: RawArticlePayload) -> AIEnrichedCard:
        """Deterministically enrich article payload into a validated AIEnrichedCard."""
        # Clean headline and truncate body to 3500 chars
        truncated_body = article.raw_body[:3500] if article.raw_body else ""
        combined_text = f"{article.title} {truncated_body}".lower()

        # 1. Entity and Tag Extraction
        matched_tags: List[str] = []
        for kw, tag_name in self.KNOWN_ENTITIES.items():
            # Allow optional Hebrew prefixes (ב, ה, ל, מ, כ, ש, ו) but disallow trailing letters
            pattern = rf"(?:^|[^\wא-ת]|[בהלמכשו]{{1,2}}){re.escape(kw.lower())}(?![\wא-ת])"
            if re.search(pattern, combined_text):
                if tag_name not in matched_tags:
                    matched_tags.append(tag_name)

        # Fallback tags if no known entity matched
        if not matched_tags:
            if article.category and article.category.strip():
                matched_tags.append(article.category.strip())
            matched_tags.append("Israeli Sports")
            if article.publisher:
                matched_tags.append(article.publisher.capitalize())

        # Ensure unique tags, limit to top 8
        final_tags = list(dict.fromkeys(matched_tags))[:8]

        # 2. Tone Classification
        hype_score = sum(1 for kw in self.HYPE_KEYWORDS if kw in combined_text)
        critical_score = sum(1 for kw in self.CRITICAL_KEYWORDS if kw in combined_text)

        if critical_score > hype_score and critical_score > 0:
            tone = ToneEnum.CRITICAL
        elif hype_score > 0:
            tone = ToneEnum.HYPE
        else:
            tone = ToneEnum.OBJECTIVE

        # 3. Context Label Classification
        if any(kw in combined_text for kw in self.INJURY_KEYWORDS):
            context_label = "Injury Update"
        elif any(kw in combined_text for kw in self.TRANSFER_KEYWORDS):
            context_label = "Transfer Rumor"
        elif any(kw in combined_text for kw in self.TACTICAL_KEYWORDS):
            context_label = "Tactical Analysis"
        elif any(kw in combined_text for kw in self.BREAKING_KEYWORDS):
            context_label = "Breaking News"
        elif any(kw in combined_text for kw in self.MATCH_KEYWORDS):
            context_label = "Match Report"
        else:
            context_label = "Match Report"

        # 4. Micro-Summary Generation (concise single sentence <= 35 words)
        clean_title = article.title.strip().rstrip(".:!?- \t")
        primary_entity = final_tags[0] if final_tags else "Israeli sports"

        # Construct single informative factual sentence
        if any(w in clean_title for w in [":", "-"]):
            summary_sentence = f"{clean_title}."
        else:
            summary_sentence = f"{clean_title}, highlighting key developments for {primary_entity}."

        words = summary_sentence.split()
        if len(words) > 35:
            summary_sentence = " ".join(words[:32]) + "..."
        elif len(words) < 3:
            summary_sentence = f"{clean_title} reported by {article.publisher.capitalize()}."

        # Ensure summary passes AIEnrichedCard validation bounds (10 to 400 chars, max 40 words)
        summary_sentence = summary_sentence.strip()
        if len(summary_sentence) < 10:
            summary_sentence = f"{summary_sentence} - Full sports coverage from FanZone."

        return AIEnrichedCard(
            micro_summary=summary_sentence,
            tags=final_tags,
            tone=tone,
            context_label=context_label,
        )


class AIEnrichmentService:
    """Service dispatcher orchestrating article enrichment, queue consumption, and DB persistence."""

    def __init__(
        self,
        enricher: Optional[Union[GeminiAIEnricher, MockAIEnricher]] = None,
        use_mock: Optional[bool] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        settings_obj: Optional[Settings] = None,
    ) -> None:
        self.settings = settings_obj or get_settings()

        if enricher is not None:
            self.enricher = enricher
        else:
            # Determine mock AI flag
            should_mock = (
                use_mock
                if use_mock is not None
                else (
                    self.settings.is_mock_ai
                    or not self.settings.GEMINI_API_KEY
                    or self.settings.GEMINI_API_KEY.lower() in ("mock", "none", "", "placeholder")
                    or not GENAI_AVAILABLE
                )
            )

            if should_mock:
                self.enricher = MockAIEnricher()
            else:
                self.enricher = GeminiAIEnricher(
                    api_key=api_key or self.settings.GEMINI_API_KEY,
                    model=model or self.settings.GEMINI_MODEL,
                )

    async def enrich_article(self, article: RawArticlePayload) -> AIEnrichedCard:
        """Enrich a RawArticlePayload using the active enrichment engine."""
        try:
            return await self.enricher.enrich_article(article)
        except Exception as e:
            # If live Gemini enrichment encounters an error, fallback gracefully to MockAIEnricher
            if not isinstance(self.enricher, MockAIEnricher):
                logger.warning(
                    "Gemini AI enrichment failed for '%s', falling back to MockAIEnricher: %s",
                    article.title,
                    e,
                )
                fallback_enricher = MockAIEnricher()
                return await fallback_enricher.enrich_article(article)
            raise

    async def enrich_and_store(
        self,
        raw_article: RawArticlePayload,
        repository: ArticleRepository,
    ) -> ArticleModel:
        """Enrich a raw article payload and persist it to the database repository."""
        url_str = str(raw_article.url).strip()

        # Check for existing article by URL to guarantee idempotent processing
        existing = await repository.get_by_url(url_str)
        if existing is not None:
            logger.debug("Article already exists in DB with URL %s, skipping enrichment", url_str)
            return existing

        # Run AI enrichment
        enriched = await self.enrich_article(raw_article)

        # Persist to repository
        article_model = await repository.create_enriched_article(raw_article, enriched)
        logger.info(
            "Enriched and stored article ID=%s: '%s' [%s / %s]",
            article_model.id,
            article_model.title[:40],
            article_model.publisher,
            article_model.tone,
        )
        return article_model

    async def process_queue_item(
        self,
        queue: BaseQueue,
        repository: ArticleRepository,
        timeout: Optional[float] = None,
    ) -> Optional[ArticleModel]:
        """Pop an item from the task queue, enrich it, and persist it to the database.

        Args:
            queue: BaseQueue instance (InMemoryTaskQueue or RedisTaskQueue).
            repository: ArticleRepository bound to active DB session.
            timeout: Optional wait timeout for popping from queue.

        Returns:
            Persisted ArticleModel or None if queue is empty or pop timed out.
        """
        raw_item = await queue.pop(timeout=timeout)
        if raw_item is None:
            return None

        return await self.enrich_and_store(raw_item, repository)
 
 
class FallbackAIEnrichmentService:
    """Deterministic fallback mock AI enrichment service when live AI is unavailable."""

    def __init__(self, use_mock: bool = True, **kwargs: Any) -> None:
        self.use_mock = use_mock
        self._enricher = MockAIEnricher()

    async def enrich_article(self, article: RawArticlePayload) -> AIEnrichedCard:
        """Deterministically enrich a raw article payload."""
        return await self._enricher.enrich_article(article)

    async def enrich_and_store(
        self,
        raw_article: RawArticlePayload,
        repository: ArticleRepository,
    ) -> ArticleModel:
        """Enrich article and persist in repository."""
        enriched = await self.enrich_article(raw_article)
        return await repository.create_enriched_article(raw_article, enriched)
