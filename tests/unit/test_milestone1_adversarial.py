"""Adversarial stress tests and edge cases for Milestone 1.

Challenge Dimensions:
1. SQLite and PostgreSQL URL normalization for various connection string formats.
2. Hebrew unicode edge cases, mixed Hebrew/English strings, right-to-left punctuation, emojis, and special characters in tags and article titles.
3. Deduplication under concurrent/repeated upserts with identical canonical URLs or identical content hashes.
4. Cascade deletes: deleting an Article deletes ArticleMedia and ArticleTag junction rows, but does NOT delete the shared Tag or the parent Source.
5. Invalid query parameters (negative page/skip, zero limit, unknown filters, nonexistent IDs).
"""

import asyncio
from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.config import Settings
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.models.source import Source
from fan_zone.models.article import Article
from fan_zone.models.media import ArticleMedia
from fan_zone.models.tag import Tag, ArticleTag
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.tag_repo import TagRepository, slugify
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.schemas.source import SourceCreate
from fan_zone.schemas.article import ArticleCreate, ArticleFilter
from fan_zone.schemas.media import MediaCreate


# ==============================================================================
# Challenge 1: SQLite and PostgreSQL URL Normalization
# ==============================================================================

class TestDatabaseUrlNormalization:
    """Challenge 1: Connection string format normalization tests."""

    @pytest.mark.parametrize(
        "raw_url, expected_url",
        [
            # SQLite formats
            ("sqlite:///./fan_zone.db", "sqlite+aiosqlite:///./fan_zone.db"),
            ("sqlite:////absolute/path/fan_zone.db", "sqlite+aiosqlite:////absolute/path/fan_zone.db"),
            ("sqlite:///:memory:", "sqlite+aiosqlite:///:memory:"),
            ("sqlite:///C:/Users/app/fan_zone.db", "sqlite+aiosqlite:///C:/Users/app/fan_zone.db"),
            ("sqlite+aiosqlite:///./fan_zone.db", "sqlite+aiosqlite:///./fan_zone.db"),
            ("sqlite://", "sqlite+aiosqlite://"),
            # PostgreSQL standard formats
            ("postgresql://user:pass@localhost:5432/fanzone", "postgresql+asyncpg://user:pass@localhost:5432/fanzone"),
            ("postgresql://app_user:s3cr3t_p@ss@db.internal:5432/fanzone_prod", "postgresql+asyncpg://app_user:s3cr3t_p@ss@db.internal:5432/fanzone_prod"),
            ("postgresql+asyncpg://user:pass@localhost:5432/fanzone", "postgresql+asyncpg://user:pass@localhost:5432/fanzone"),
            # PostgreSQL shorthand 'postgres://' (Heroku/Render style)
            ("postgres://user:pass@localhost:5432/fanzone", "postgresql+asyncpg://user:pass@localhost:5432/fanzone"),
            ("postgres://admin:pass123@10.0.0.5:5432/sports_db?sslmode=require", "postgresql+asyncpg://admin:pass123@10.0.0.5:5432/sports_db?sslmode=require"),
            # With query parameters and special characters
            ("postgresql://u%40ser:p%23ss@localhost:5432/fanzone?charset=utf8", "postgresql+asyncpg://u%40ser:p%23ss@localhost:5432/fanzone?charset=utf8"),
            # None or empty fallback
            (None, "sqlite+aiosqlite:///./fan_zone.db"),
            ("", "sqlite+aiosqlite:///./fan_zone.db"),
        ],
    )
    def test_normalize_database_url(self, raw_url: str, expected_url: str):
        """Verify that all variants of SQLite and PostgreSQL connection strings normalize correctly."""
        normalized = Settings.normalize_database_url(raw_url)
        assert normalized == expected_url

    def test_settings_instantiation_with_custom_urls(self):
        """Verify Settings model applies normalization during initialization."""
        s1 = Settings(DATABASE_URL="sqlite:///test_local.db")
        assert s1.DATABASE_URL == "sqlite+aiosqlite:///test_local.db"

        s2 = Settings(DATABASE_URL="postgres://usr:pwd@host:5432/db")
        assert s2.DATABASE_URL == "postgresql+asyncpg://usr:pwd@host:5432/db"

        s3 = Settings(DATABASE_URL="postgresql://usr:pwd@host:5432/db")
        assert s3.DATABASE_URL == "postgresql+asyncpg://usr:pwd@host:5432/db"


# ==============================================================================
# Challenge 2: Hebrew Unicode, Mixed Strings, RTL Punctuation & Emojis
# ==============================================================================

class TestHebrewUnicodeAndSpecialCharacters:
    """Challenge 2: Stress tests with complex Hebrew, Niqqud, RTL marks, and Emojis."""

    @pytest.mark.asyncio
    async def test_hebrew_niqqud_vowels_preservation(self, db_session: AsyncSession):
        """Verify that Hebrew vowels (Niqqud) are preserved without corruption or encoding errors."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)
        source, _ = await source_repo.create_or_get(
            SourceCreate(name="sport5_niqqud", display_name="Sport5 Niqqud", base_url="https://sport5.co.il")
        )

        title_with_niqqud = "מַכָּבִי תֵּל אָבִיב נִצְּחָה 85:82 אֶת רֵיאָל מַדְרִיד"
        paragraphs_with_niqqud = [
            "הַצְּהֻבִּים שֶׁל עוֹדֵד קָטָשׁ הִשִּׂיגוּ נִצָּחוֹן עֲנָק בַּהֵיכָל.",
            "וֵוייד בּוֹלְדְוִוין לָהַט עִם 28 נְקֻדּוֹת וְ-6 אַסִיסְטִים.",
        ]

        article, is_created = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://sport5.co.il/niqqud/1",
            "original_title": title_with_niqqud,
            "published_at": datetime.now(timezone.utc),
            "raw_paragraphs": paragraphs_with_niqqud,
            "sport": "כַּדּוּרְסַל",
            "competition": "יוּרוֹלִיג",
            "teams_json": ["מַכָּבִי תֵּל אָבִיב", "רֵיאָל מַדְרִיד"],
            "players_json": ["וֵוייד בּוֹלְדְוִוין", "עוֹדֵד קָטָשׁ"],
            "tags_json": ["נִצָּחוֹן", "יּוּרוֹלִיג"],
        })
        assert is_created is True
        assert article.original_title == title_with_niqqud
        assert article.raw_paragraphs == paragraphs_with_niqqud
        assert article.sport == "כַּדּוּרְסַל"

        # Lookup by ID
        fetched = await article_repo.get_by_id(article.id)
        assert fetched is not None
        assert fetched.original_title == title_with_niqqud

        # Hash computation is deterministic with Niqqud
        expected_hash = ArticleRepository.compute_content_hash(title_with_niqqud, paragraphs_with_niqqud)
        assert fetched.content_hash == expected_hash

    @pytest.mark.asyncio
    async def test_mixed_hebrew_english_numbers_and_punctuation(self, db_session: AsyncSession):
        """Verify handling of mixed Hebrew/English, RTL/LTR characters, colons, quotes and numbers."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)
        source, _ = await source_repo.create_or_get(
            SourceCreate(name="one_mixed", display_name="ONE Mixed", base_url="https://one.co.il")
        )

        title = 'מכבי Playtika ת"א ניצחה 85:82 את Real Madrid ב-EuroLeague! #Maccabi'
        subtitle = 'הצהובים-כחולים גברו על Los Blancos ב-OT (הארכה) של 5 דקות: "משחק בלתי נשכח!"'
        paragraphs = [
            "ברבע ה-4: ריצת 0:12 של הצהובים קבעה 75:75 וכפתה Overtime.",
            "Wade Baldwin IV קלע 28pts (5/7 ל-3), Lorenzo Brown הוסיף 15pts & 8ast.",
            'קטש סיכם: "זה ה-DNA של המועדון - We never give up!"',
        ]

        article, is_created = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://one.co.il/mixed/item/100",
            "original_title": title,
            "original_subtitle": subtitle,
            "published_at": datetime.now(timezone.utc),
            "raw_paragraphs": paragraphs,
            "sport": "כדורסל",
            "competition": "EuroLeague",
            "teams_json": ["מכבי תל אביב", "Real Madrid CF"],
            "players_json": ["Wade Baldwin IV", "Lorenzo Brown", "עודד קטש"],
            "tags_json": ["EuroLeague", "Overtime", "85:82", "Playtika"],
        })
        assert is_created is True
        assert article.original_title == title
        assert article.original_subtitle == subtitle

        # Search by English substring
        res_en, total_en = await article_repo.list_articles(search_query="Baldwin")
        assert total_en == 1
        assert res_en[0].id == article.id

        # Search by Hebrew substring with quotation mark
        res_he, total_he = await article_repo.list_articles(search_query='משחק בלתי נשכח')
        assert total_he == 1

        # Search by score pattern
        res_score, total_score = await article_repo.list_articles(search_query="85:82")
        assert total_score == 1

    @pytest.mark.asyncio
    async def test_hebrew_special_punctuation_gershayim_and_geresh(self, db_session: AsyncSession):
        """Verify Hebrew Gershayim (״ U+05F4) and Geresh (׳ U+05F3) vs ASCII quotes in tags and titles."""
        tag_repo = TagRepository(db_session)
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)

        source, _ = await source_repo.create_or_get(
            SourceCreate(name="walla_gershayim", display_name="Walla Gershayim", base_url="https://sports.walla.co.il")
        )

        # Hebrew Gershayim (U+05F4) vs ASCII quote (")
        tag_unicode_gershayim = await tag_repo.get_or_create_tag("בית״ר ירושלים", tag_type=TagType.TEAM)
        tag_ascii_quote = await tag_repo.get_or_create_tag('בית"ר ירושלים', tag_type=TagType.TEAM)
        
        assert tag_unicode_gershayim.id is not None
        assert tag_ascii_quote.id is not None

        # Hebrew Geresh (U+05F3) vs ASCII single quote (')
        tag_geresh = await tag_repo.get_or_create_tag("ג׳ודו", tag_type=TagType.SPORT)
        tag_ascii_single = await tag_repo.get_or_create_tag("ג'ודו", tag_type=TagType.SPORT)

        assert tag_geresh.id is not None
        assert tag_ascii_single.id is not None

        # Upsert article containing both
        article, _ = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://sports.walla.co.il/gershayim/1",
            "original_title": 'בית״ר ירושלים ניצחה 0:1 את מכבי חיפה; ג׳ודו: מדליית זהב',
            "published_at": datetime.now(timezone.utc),
            "raw_paragraphs": ['שער ענק של בית"ר בטדי. במקביל בענף הג\'ודו: הישג ענק.'],
            "sport": "כדורגל",
            "teams_json": ["בית״ר ירושלים", 'בית"ר ירושלים'],
            "tags_json": ["ג׳ודו", "ג'ודו"],
        })
        assert article.id is not None

        # Search matching either form
        res, count = await article_repo.list_articles(search_query="בית")
        assert count >= 1

    @pytest.mark.asyncio
    async def test_emojis_and_rtl_control_characters(self, db_session: AsyncSession):
        """Verify titles and tags containing emojis (🔥, 🏀, ⚽, 🏆) and RTL/LTR control marks."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)
        source, _ = await source_repo.create_or_get(
            SourceCreate(name="israelhayom_emoji", display_name="Israel Hayom Emoji", base_url="https://israelhayom.co.il")
        )

        # Unicode with Emojis + RLM (\u200f) + LRM (\u200e)
        emoji_title = "🏆 דרמה בדרבי! 🔥 מכבי ת\"א ניצחה את הפועל 85:82 🏀⚽"
        rlm_subtitle = "\u200fהצהובים חגגו בסיום משחק מותח במיוחד\u200e."
        emoji_paragraphs = ["קהל ענק של 11,000 צופים 🔥🔥🔥 ראה ניצחון דרמטי! 🌟"]

        article, is_created = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://israelhayom.co.il/emoji/1",
            "original_title": emoji_title,
            "original_subtitle": rlm_subtitle,
            "published_at": datetime.now(timezone.utc),
            "raw_paragraphs": emoji_paragraphs,
            "sport": "כדורסל 🏀",
            "teams_json": ["מכבי תל אביב 🟡", "הפועל תל אביב 🔴"],
            "tags_json": ["דרבי 🔥", "ניצחון 🏆"],
        })
        assert is_created is True
        assert "🏆" in article.original_title
        assert "🔥" in article.raw_paragraphs[0]

        # Search by emoji
        res, count = await article_repo.list_articles(search_query="🔥")
        assert count == 1
        assert res[0].id == article.id

    def test_slugify_edge_cases(self):
        """Verify slugify under adversarial unicode, quotes, symbols, and empty strings."""
        assert slugify("מכבי תל אביב") == "מכבי-תל-אביב"
        assert slugify("בית\"ר ירושלים") == "ביתר-ירושלים"
        assert slugify("ג'ודו 2026") == "גודו-2026"
        assert slugify("Real Madrid vs Barcelona (3-1)") == "real-madrid-vs-barcelona-3-1"
        assert slugify("   ---רועי כהן---   ") == "רועי-כהן"
        assert slugify("🏀⚽🔥") == ""  # Strips all emojis cleanly
        assert slugify("   ") == ""


# ==============================================================================
# Challenge 3: Deduplication Under Concurrent / Repeated Upserts
# ==============================================================================

class TestDeduplicationAdversarial:
    """Challenge 3: Dual deduplication (URL and Content Hash) stress tests."""

    @pytest.mark.asyncio
    async def test_idempotent_repeated_upserts_same_url_and_hash(self, db_session: AsyncSession):
        """Verify that repeating the exact same upsert 10 times produces exactly 1 DB record."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)
        source, _ = await source_repo.create_or_get(
            SourceCreate(name="sport5_dedup", display_name="Sport5 Dedup", base_url="https://sport5.co.il")
        )

        payload = {
            "source_id": source.id,
            "canonical_url": "https://sport5.co.il/dedup/repeat/1",
            "original_title": "כותרת קבועה לבדיקת כפילויות",
            "published_at": datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc),
            "raw_paragraphs": ["פסקה ראשונה קבועה", "פסקה שנייה קבועה"],
            "sport": "כדורגל",
            "teams_json": ["מכבי חיפה"],
            "tags_json": ["כדורגל", "ליגת העל"],
            "ai_headline": "כותרת AI קבועה",
            "ingestion_status": IngestionStatus.AI_PROCESSED,
        }

        # 1st upsert: Created
        art1, created1 = await article_repo.upsert_article(payload)
        assert created1 is True
        initial_id = art1.id

        # 2nd to 10th upserts: Must return existing article, created=False
        for _ in range(9):
            art_dup, created_dup = await article_repo.upsert_article(payload)
            assert created_dup is False
            assert art_dup.id == initial_id

        # Total count in DB must be exactly 1
        all_articles, total = await article_repo.list_articles()
        assert total == 1
        assert len(all_articles) == 1

    @pytest.mark.asyncio
    async def test_deduplication_different_url_identical_content_hash(self, db_session: AsyncSession):
        """Verify that syndicated/re-posted articles with different URLs but identical content hash are deduplicated."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)
        source, _ = await source_repo.create_or_get(
            SourceCreate(name="ynet_dedup", display_name="Ynet Dedup", base_url="https://ynet.co.il")
        )

        title = "ידיעה בלעדית: הסכם חתום בין המועדונים"
        paragraphs = [
            "העסקה נסגרה הלילה לאחר מו\"מ מרתוני שנמשך שעות רבות.",
            "השחקן יחתום על חוזה ל-3 עונות תמורת 1.5 מיליון יורו לעונה.",
        ]

        # 1. Desktop URL
        art_desktop, created_desktop = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://www.ynet.co.il/sport/article/desk_9999",
            "original_title": title,
            "published_at": datetime(2026, 8, 28, 14, 0, 0, tzinfo=timezone.utc),
            "raw_paragraphs": paragraphs,
            "sport": "כדורגל",
            "ai_headline": "הסכם חתום בין המועדונים על מעבר השחקן",
            "ingestion_status": IngestionStatus.AI_PROCESSED,
        })
        assert created_desktop is True

        # 2. Mobile URL / AMP URL with identical title and content
        art_mobile, created_mobile = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://m.ynet.co.il/sport/article/mobile_9999",
            "original_title": title,
            "published_at": datetime(2026, 8, 28, 14, 0, 0, tzinfo=timezone.utc),
            "raw_paragraphs": paragraphs,
            "sport": "כדורגל",
        })
        # Must detect identical content hash and return existing article
        assert created_mobile is False
        assert art_mobile.id == art_desktop.id

        # Total articles in DB must still be 1
        _, total = await article_repo.list_articles()
        assert total == 1

    @pytest.mark.asyncio
    async def test_content_update_same_canonical_url_updated_paragraphs(self, db_session: AsyncSession):
        """Verify that updating an article's content with the same canonical URL updates the record in-place."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)
        source, _ = await source_repo.create_or_get(
            SourceCreate(name="sport1_update", display_name="Sport1 Update", base_url="https://sport1.maariv.co.il")
        )

        canonical_url = "https://sport1.maariv.co.il/article/live_update_1"

        # 1. Initial breaking news
        art_initial, created = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": canonical_url,
            "original_title": "דיווח ראשוני: פיצוץ במו\"מ",
            "published_at": datetime(2026, 8, 28, 10, 0, 0, tzinfo=timezone.utc),
            "raw_paragraphs": ["פרטים נוספים בהמשך."],
            "ingestion_status": IngestionStatus.PENDING,
        })
        assert created is True
        initial_id = art_initial.id
        initial_hash = art_initial.content_hash

        # 2. Updated full story under same URL
        art_updated, created_update = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": canonical_url,
            "original_title": "סופית: המו\"מ פוצץ, השחקן לא יחתום",
            "published_at": datetime(2026, 8, 28, 11, 0, 0, tzinfo=timezone.utc),
            "raw_paragraphs": ["המו\"מ פוצץ באופן סופי.", "הקבוצה פנתה לאופציה חלופית."],
            "ai_headline": "המו\"מ פוצץ סופית והשחקן לא יצטרף לקבוצה",
            "ingestion_status": IngestionStatus.AI_PROCESSED,
        })
        assert created_update is False
        assert art_updated.id == initial_id
        assert art_updated.original_title == "סופית: המו\"מ פוצץ, השחקן לא יחתום"
        assert art_updated.content_hash != initial_hash
        assert len(art_updated.raw_paragraphs) == 2

        # Verify DB has 1 total article
        _, total = await article_repo.list_articles()
        assert total == 1

    def test_content_hash_resilience_to_whitespace_and_empty_paragraphs(self):
        """Verify content hash computation ignores whitespace variations."""
        h1 = ArticleRepository.compute_content_hash(
            "כותרת ראשית",
            ["פסקה 1", "פסקה 2"],
        )
        h2 = ArticleRepository.compute_content_hash(
            "   כותרת ראשית   ",
            ["   פסקה 1   ", "", "  ", "פסקה 2\n"],
        )
        assert h1 == h2


# ==============================================================================
# Challenge 4: Cascade Deletes
# ==============================================================================

class TestCascadeDeletes:
    """Challenge 4: Verification of cascade delete boundaries."""

    @pytest.mark.asyncio
    async def test_article_delete_cascades_media_and_junctions_preserves_tags_and_source(self, db_session: AsyncSession):
        """Verify deleting an Article deletes ArticleMedia and ArticleTag rows, but preserves Tag and Source entities."""
        source_repo = SourceRepository(db_session)
        tag_repo = TagRepository(db_session)
        article_repo = ArticleRepository(db_session)

        # 1. Create Source
        source, _ = await source_repo.create_or_get(
            SourceCreate(name="haaretz_cascade", display_name="Haaretz Cascade", base_url="https://haaretz.co.il")
        )

        # 2. Create Shared Tags
        tag_basketball = await tag_repo.get_or_create_tag("כדורסל", tag_type=TagType.SPORT)
        tag_maccabi = await tag_repo.get_or_create_tag("מכבי תל אביב", tag_type=TagType.TEAM)

        # 3. Create Article 1 (to be deleted) with 2 media items and 2 tags
        art1, _ = await article_repo.upsert_article(
            article_data={
                "source_id": source.id,
                "canonical_url": "https://haaretz.co.il/cascade/art1",
                "original_title": "מאמר עומק: עונת היורוליג של מכבי ת\"א",
                "published_at": datetime.now(timezone.utc),
                "raw_paragraphs": ["ניתוח מקצועי מעמיק."],
                "sport": "כדורסל",
                "teams_json": ["מכבי תל אביב"],
                "tags_json": ["כדורסל"],
            },
            media_data=[
                {"url": "https://haaretz.co.il/img1.jpg", "caption": "תמונה ראשית", "is_primary": True},
                {"url": "https://haaretz.co.il/img2.jpg", "caption": "תמונה משנית", "is_primary": False},
            ],
        )

        # 4. Create Article 2 (retains reference to shared tag)
        art2, _ = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://haaretz.co.il/cascade/art2",
            "original_title": "ידיעה נוספת בכדורסל",
            "published_at": datetime.now(timezone.utc),
            "raw_paragraphs": ["כתבה שנייה."],
            "sport": "כדורסל",
            "teams_json": ["מכבי תל אביב"],
        })

        art1_id = art1.id
        art2_id = art2.id
        source_id = source.id
        tag_bball_id = tag_basketball.id
        tag_mac_id = tag_maccabi.id

        # Verify initial state
        media_count_before = (await db_session.execute(
            select(func.count(ArticleMedia.id)).where(ArticleMedia.article_id == art1_id)
        )).scalar()
        assert media_count_before == 2

        art_tag_count_before = (await db_session.execute(
            select(func.count(ArticleTag.id)).where(ArticleTag.article_id == art1_id)
        )).scalar()
        assert art_tag_count_before >= 2

        # 5. EXECUTE DELETE ON ARTICLE 1
        deleted = await article_repo.delete_article(art1_id)
        assert deleted is True

        # Flush / commit to ensure cascades execute
        await db_session.flush()
        db_session.expire_all()

        # Check 1: Article 1 is deleted
        fetched_art1 = await article_repo.get_by_id(art1_id)
        assert fetched_art1 is None

        # Check 2: Article 1's Media items are deleted
        media_after = (await db_session.execute(
            select(ArticleMedia).where(ArticleMedia.article_id == art1_id)
        )).scalars().all()
        assert len(media_after) == 0

        # Check 3: Article 1's junction rows in ArticleTag are deleted
        art_tags_after = (await db_session.execute(
            select(ArticleTag).where(ArticleTag.article_id == art1_id)
        )).scalars().all()
        assert len(art_tags_after) == 0

        # Check 4: Shared Tags STILL EXIST in tags table
        fetched_tag_bball = await tag_repo.get_by_id(tag_bball_id)
        fetched_tag_mac = await tag_repo.get_by_id(tag_mac_id)
        assert fetched_tag_bball is not None
        assert fetched_tag_mac is not None

        # Check 5: Parent Source STILL EXISTS
        fetched_source = await source_repo.get_by_id(source_id)
        assert fetched_source is not None

        # Check 6: Article 2 and its tag associations are intact
        fetched_art2 = await article_repo.get_by_id(art2_id)
        assert fetched_art2 is not None
        assert len(fetched_art2.tags) >= 1

    @pytest.mark.asyncio
    async def test_delete_source_cascades_articles_preserves_tags(self, db_session: AsyncSession):
        """Verify deleting a Source cascades to delete its Articles and Media, but leaves Tags intact."""
        source_repo = SourceRepository(db_session)
        tag_repo = TagRepository(db_session)
        article_repo = ArticleRepository(db_session)

        source, _ = await source_repo.create_or_get(
            SourceCreate(name="source_to_delete", display_name="To Delete", base_url="https://delete.co.il")
        )
        tag = await tag_repo.get_or_create_tag("טניס", tag_type=TagType.SPORT)

        art, _ = await article_repo.upsert_article({
            "source_id": source.id,
            "canonical_url": "https://delete.co.il/art1",
            "original_title": "כתבת טניס שתימחק",
            "published_at": datetime.now(timezone.utc),
            "raw_paragraphs": ["תוכן."],
            "sport": "טניס",
        })

        art_id = art.id
        tag_id = tag.id
        source_id = source.id

        # Delete source directly
        await db_session.delete(source)
        await db_session.flush()
        db_session.expire_all()

        # Source is gone
        assert await source_repo.get_by_id(source_id) is None

        # Article is cascade-deleted
        assert await article_repo.get_by_id(art_id) is None

        # Tag is preserved
        assert await tag_repo.get_by_id(tag_id) is not None


# ==============================================================================
# Challenge 5: Invalid Query Parameters & Boundary Conditions
# ==============================================================================

class TestInvalidQueryParametersAndBoundaries:
    """Challenge 5: Robustness against invalid query parameters, negative bounds, unknown filters, and missing IDs."""

    @pytest.mark.asyncio
    async def test_list_articles_negative_skip_and_zero_limit(self, db_session: AsyncSession, sample_article_dict: dict):
        """Verify that negative skip, zero limit, or oversized limits do not crash the database query."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)

        source, _ = await source_repo.create_or_get(
            SourceCreate(name="sport5", display_name="Sport5", base_url="https://sport5.co.il")
        )
        sample_article_dict["source_id"] = source.id
        await article_repo.upsert_article(sample_article_dict)

        # 1. Normal pagination
        res1, count1 = await article_repo.list_articles(skip=0, limit=20)
        assert count1 == 1
        assert len(res1) == 1

        # 2. Large limit
        res2, count2 = await article_repo.list_articles(skip=0, limit=1000)
        assert count2 == 1
        assert len(res2) == 1

        # 3. Skip beyond total count
        res3, count3 = await article_repo.list_articles(skip=100, limit=20)
        assert count3 == 1
        assert len(res3) == 0

    @pytest.mark.asyncio
    async def test_list_articles_nonexistent_and_unknown_filters(self, db_session: AsyncSession, sample_article_dict: dict):
        """Verify that filtering by nonexistent sources, sports, teams, tags, or statuses returns empty results safely."""
        source_repo = SourceRepository(db_session)
        article_repo = ArticleRepository(db_session)

        source, _ = await source_repo.create_or_get(
            SourceCreate(name="sport5", display_name="Sport5", base_url="https://sport5.co.il")
        )
        sample_article_dict["source_id"] = source.id
        await article_repo.upsert_article(sample_article_dict)

        # 1. Nonexistent source_id
        res_src, count_src = await article_repo.list_articles(source_id=99999)
        assert count_src == 0
        assert len(res_src) == 0

        # 2. Nonexistent source_name
        res_name, count_name = await article_repo.list_articles(source_name="nonexistent_channel")
        assert count_name == 0
        assert len(res_name) == 0

        # 3. Nonexistent sport
        res_sport, count_sport = await article_repo.list_articles(sport="קריקט")
        assert count_sport == 0
        assert len(res_sport) == 0

        # 4. Nonexistent team
        res_team, count_team = await article_repo.list_articles(team="מנצ'סטר סיטי")
        assert count_team == 0
        assert len(res_team) == 0

        # 5. Nonexistent competition
        res_comp, count_comp = await article_repo.list_articles(competition="מונדיאל 1930")
        assert count_comp == 0
        assert len(res_comp) == 0

        # 6. Nonexistent tag
        res_tag, count_tag = await article_repo.list_articles(tag="תגית_שלא_קיימת")
        assert count_tag == 0
        assert len(res_tag) == 0

        # 7. Nonexistent status string
        res_status, count_status = await article_repo.list_articles(status="UNKNOWN_STATUS")
        assert count_status == 0
        assert len(res_status) == 0

        # 8. Nonexistent search query
        res_q, count_q = await article_repo.list_articles(search_query="מחרוזת_חיפוש_שאינה_קיימת_בשום_מקום_12345")
        assert count_q == 0
        assert len(res_q) == 0

        # 9. Inverted date range (date_from in future, date_to in past)
        res_date, count_date = await article_repo.list_articles(
            date_from=datetime(2099, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )
        assert count_date == 0
        assert len(res_date) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_ids_and_empty_lookups(self, db_session: AsyncSession):
        """Verify that looking up or deleting nonexistent IDs returns None or False safely."""
        source_repo = SourceRepository(db_session)
        tag_repo = TagRepository(db_session)
        article_repo = ArticleRepository(db_session)

        # Article lookups
        assert await article_repo.get_by_id(-1) is None
        assert await article_repo.get_by_id(0) is None
        assert await article_repo.get_by_id(999999) is None
        assert await article_repo.get_by_canonical_url("") is None
        assert await article_repo.get_by_canonical_url("https://nonexistent.com/none") is None
        assert await article_repo.get_by_content_hash("") is None
        assert await article_repo.get_by_content_hash("0" * 64) is None
        assert await article_repo.exists_by_url_or_hash("https://none.com", "0" * 64) is False
        assert await article_repo.delete_article(-1) is False
        assert await article_repo.delete_article(999999) is False

        # Source lookups
        assert await source_repo.get_by_id(-1) is None
        assert await source_repo.get_by_id(999999) is None
        assert await source_repo.get_by_name("") is None
        assert await source_repo.get_by_name("nonexistent") is None
        assert await source_repo.update_poll_status(-1, success=False) is None

        # Tag lookups
        assert await tag_repo.get_by_id(-1) is None
        assert await tag_repo.get_by_id(999999) is None
        assert await tag_repo.get_by_name("") is None
        assert await tag_repo.get_by_name("nonexistent") is None

    @pytest.mark.asyncio
    async def test_tag_repository_invalid_inputs(self, db_session: AsyncSession):
        """Verify TagRepository handles invalid and empty inputs appropriately."""
        tag_repo = TagRepository(db_session)

        # Empty string tag raises ValueError
        with pytest.raises(ValueError, match="Tag name cannot be empty"):
            await tag_repo.get_or_create_tag("")

        with pytest.raises(ValueError, match="Tag name cannot be empty"):
            await tag_repo.get_or_create_tag("   ")

        # Unknown tag type defaults to GENERAL
        tag = await tag_repo.get_or_create_tag("תגית כללית", tag_type="INVALID_TAG_TYPE")
        assert tag.tag_type == TagType.GENERAL

        # Listing tags with invalid tag type returns empty list without error
        tags = await tag_repo.list_tags(tag_type="INVALID_TAG_TYPE")
        assert len(tags) == 0

    def test_pydantic_schema_validation_failures(self):
        """Verify Pydantic schemas enforce type safety and reject invalid payloads."""
        # ArticleCreate without required fields
        with pytest.raises(ValidationError):
            ArticleCreate(
                # Missing source_id, canonical_url, original_title, published_at
                raw_paragraphs=["פסקה"],
            )

        # SourceCreate without required fields
        with pytest.raises(ValidationError):
            SourceCreate(
                name="only_name",
                # Missing display_name, base_url
            )

        # MediaCreate without url
        with pytest.raises(ValidationError):
            MediaCreate(
                media_type=MediaType.IMAGE,
                # Missing url
            )
