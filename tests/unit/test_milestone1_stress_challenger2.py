"""Empirical & Stress Verification Suite for Milestone 1 (Challenger 2).

Tests:
1. Batch insertion of 50+ articles with diverse sports, teams, competitions, tags, and sources.
2. Single & multi-criteria filtering matrix.
3. Hebrew full-text substring search across original_title, ai_headline, cleaned_body.
4. Pagination offset/limit and ordering by published_at DESC.
5. Transaction rollback and DB consistency on constraint violations.
"""

import hashlib
import unicodedata
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.models.article import Article, ArticleMedia
from fan_zone.models.source import Source
from fan_zone.models.tag import Tag, ArticleTag
from fan_zone.models.enums import IngestionStatus, MediaType, TagType
from fan_zone.repositories.source_repo import SourceRepository
from fan_zone.repositories.tag_repo import TagRepository
from fan_zone.repositories.article_repo import ArticleRepository
from fan_zone.schemas.source import SourceCreate


# Helper fixtures & generators
def generate_50_plus_test_articles(source_ids: dict):
    """Generates 60 structured articles with distinct combinations of attributes."""
    base_time = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    articles = []

    sports_pool = [
        ("כדורגל", ["ליגת העל", "ליגת האלופות", "הליגה האירופית"]),
        ("כדורסל", ["יורוליג", "ליגת העל בכדורסל", "יורוקאפ"]),
        ("טניס", ["ווימבלדון", "רולאן גארוס", "אליפות ארה\"ב הפתוחה"]),
        ("ג'ודו", ["גרנד סלאם תל אביב", "אליפות אירופה בג'ודו"]),
        ("אתלטיקה", ["אליפות העולם באתלטיקה", "ליגת היהלום"]),
    ]

    teams_pool = {
        "כדורגל": ["מכבי חיפה", "מכבי תל אביב", "הפועל תל אביב", "בית\"ר ירושלים", "הפועל באר שבע", "ברצלונה", "ריאל מדריד"],
        "כדורסל": ["מכבי תל אביב", "הפועל ירושלים", "הפועל תל אביב", "ריאל מדריד", "פנאתינייקוס", "אולימפיאקוס"],
        "טניס": ["איגוד הטניס"],
        "ג'ודו": ["נבחרת ישראל בג'ודו"],
        "אתלטיקה": ["נבחרת ישראל באתלטיקה"],
    }

    players_pool = {
        "כדורגל": ["ערן זהבי", "דיא סבע", "עומר אצילי", "קיליאן אמבפה", "לאמין ימאל"],
        "כדורסל": ["ווייד בולדווין", "רומן סורקין", "ים מדר", "פקונדו קמפאסו"],
        "טניס": ["נובאק ג'וקוביץ'", "קרלוס אלקרס", "ישי עוליאל"],
        "ג'ודו": ["פיטר פלצ'יק", "רז הרשקו", "תמנע נלסון לוי"],
        "אתלטיקה": ["בלסינג אפריפה", "לונה צ'מטאי"],
    }

    source_names = ["sport5", "one", "walla", "ynet", "sport1", "israelhayom", "haaretz"]

    for i in range(60):
        s_idx = i % len(sports_pool)
        sport, competitions = sports_pool[s_idx]
        comp = competitions[i % len(competitions)]
        source_name = source_names[i % len(source_names)]
        source_id = source_ids[source_name]

        teams = [teams_pool[sport][i % len(teams_pool[sport])]]
        if len(teams_pool[sport]) > 1 and (i % 2 == 0):
            second_team = teams_pool[sport][(i + 1) % len(teams_pool[sport])]
            if second_team != teams[0]:
                teams.append(second_team)

        players = [players_pool[sport][i % len(players_pool[sport])]]
        tags = [sport, comp] + teams + players + [f"נושא_{i % 5}"]

        pub_time = base_time + timedelta(hours=i * 6)

        # Diverse search tokens in various fields
        hebrew_phrases = [
            ("סנסציה גדולה בהיכל", "ניצחון דרמטי בדקה ה-90", "הופעה מחשמלת של השחקנים במחצית השנייה"),
            ("הודעה רשמית על מעבר", "החתמה נוצצת בקיץ", "המועדון הודיע היום רשמית על צירוף הכוכב"),
            ("קרב צמרת מותח", "חלוקת נקודות במשחק העונה", "אירוע ספורט יוצא דופן שננעל בשוויון"),
            ("תצוגת ענק על המשטח", "ניצחון חלק בשלוש מערכות", "הפגנת עליונות מוחלטת מהרגע הראשון"),
            ("מדליית זהב יוקרתית", "הישג חסר תקדים לישראל", "הקרב על הפודיום הסתיים בהמנון התקווה"),
        ]
        phrase = hebrew_phrases[i % len(hebrew_phrases)]

        art_data = {
            "source_id": source_id,
            "canonical_url": f"https://www.{source_name}.co.il/article/item_{i}_{hash(pub_time)}",
            "original_title": f"[{source_name.upper()}] {phrase[0]} - {teams[0]} ({comp}) #{i}",
            "original_subtitle": f"דיווח מיוחד: {phrase[1]} בהובלת {players[0]}.",
            "author": f"כתב ספורט {i % 7}",
            "published_at": pub_time,
            "raw_paragraphs": [
                f"{phrase[2]}.",
                f"שחקני {teams[0]} סיפקו תצוגת מופת במסגרת {comp}.",
                f"המאמן החמיא במיוחד ל{players[0]} על היכולת הגבוהה.",
            ],
            "cleaned_body": f"{phrase[2]}.\n\nשחקני {teams[0]} סיפקו תצוגת מופת במסגרת {comp}.\n\nהמאמן החמיא במיוחד ל{players[0]} על היכולת הגבוהה.",
            "ai_headline": f"כותרת אובייקטיבית: {teams[0]} גברה על היריבה ב{comp} #{i}",
            "ai_subheadline": f"סיכום AI: {phrase[1]} בניצחון המרשים.",
            "sport": sport,
            "competition": comp,
            "teams_json": teams,
            "players_json": players,
            "tags_json": tags,
            "ingestion_status": IngestionStatus.AI_PROCESSED if i % 4 != 0 else IngestionStatus.PENDING,
            "media": [
                {
                    "url": f"https://cdn.{source_name}.co.il/images/img_{i}_lead.jpg",
                    "media_type": MediaType.IMAGE,
                    "caption": f"תמונת משחק #{i} - {teams[0]}",
                    "credit": "צלם מערכת",
                    "is_primary": True,
                    "position_index": 0,
                },
                {
                    "url": f"https://cdn.{source_name}.co.il/images/img_{i}_gallery.jpg",
                    "media_type": MediaType.IMAGE,
                    "caption": f"גלריה נוספת #{i}",
                    "credit": "סוכנות צילום",
                    "is_primary": False,
                    "position_index": 1,
                },
            ],
        }
        articles.append(art_data)

    return articles


# ==========================================
# Challenge 1: Batch Insert 50+ Articles
# ==========================================

@pytest.mark.asyncio
async def test_batch_insert_60_articles_with_rich_relations(db_session: AsyncSession):
    """
    Challenge 1:
    - Seeds all 7 sources.
    - Inserts 60 diverse articles across 5 sports, 12 competitions, 15 teams, and 7 sources.
    - Verifies persistence, media cascade, and automatic tag generation.
    """
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)
    tag_repo = TagRepository(db_session)

    sources = await source_repo.seed_default_sources()
    assert len(sources) == 7
    source_map = {s.name: s.id for s in sources}

    dataset = generate_50_plus_test_articles(source_map)
    assert len(dataset) == 60

    created_articles = []
    for art_payload in dataset:
        art, is_created = await article_repo.upsert_article(art_payload)
        assert is_created is True
        assert art.id is not None
        created_articles.append(art)

    assert len(created_articles) == 60

    # Verify count in database
    articles, total_count = await article_repo.list_articles(limit=100)
    assert total_count == 60
    assert len(articles) == 60

    # Verify all 60 articles have media items and tags attached
    for art in articles:
        assert len(art.media) == 2
        assert art.lead_image is not None
        assert art.lead_image.is_primary is True
        assert len(art.tags) > 0
        assert art.source is not None

    # Verify tag repository reflects all generated tags
    all_tags = await tag_repo.list_tags(limit=200)
    assert len(all_tags) > 20
    for t in all_tags:
        assert t.article_count > 0


# ==========================================
# Challenge 2: Single & Multi-Criteria Filtering
# ==========================================

@pytest.mark.asyncio
async def test_filtering_single_and_multi_criteria(db_session: AsyncSession):
    """
    Challenge 2:
    - Verifies exact and combined filters:
      * sport="כדורגל"
      * team="מכבי חיפה"
      * source_name="one" (and case-insensitivity "ONE")
      * sport="כדורגל" AND team="מכבי חיפה" AND source="one"
      * competition="יורוליג" AND sport="כדורסל"
      * status=IngestionStatus.PENDING vs AI_PROCESSED
      * Disjoint criteria return 0 results accurately.
    """
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    sources = await source_repo.seed_default_sources()
    source_map = {s.name: s.id for s in sources}
    dataset = generate_50_plus_test_articles(source_map)

    for art_payload in dataset:
        await article_repo.upsert_article(art_payload)

    # 1. Single filter: Sport
    football_articles, fb_count = await article_repo.list_articles(sport="כדורגל", limit=100)
    assert fb_count == 12
    for art in football_articles:
        assert art.sport == "כדורגל"

    basketball_articles, bb_count = await article_repo.list_articles(sport="כדורסל", limit=100)
    assert bb_count == 12
    for art in basketball_articles:
        assert art.sport == "כדורסל"

    judo_articles, judo_count = await article_repo.list_articles(sport="ג'ודו", limit=100)
    assert judo_count == 12

    # 2. Single filter: Source (Case Insensitivity)
    one_lower_articles, one_lower_count = await article_repo.list_articles(source_name="one", limit=100)
    one_upper_articles, one_upper_count = await article_repo.list_articles(source_name="ONE", limit=100)
    assert one_lower_count > 0
    assert one_lower_count == one_upper_count
    for art in one_lower_articles:
        assert art.source.name == "one"

    # 3. Single filter: Team
    haifa_articles, haifa_count = await article_repo.list_articles(team="מכבי חיפה", limit=100)
    assert haifa_count > 0
    for art in haifa_articles:
        assert "מכבי חיפה" in art.teams_json

    # 4. Single filter: Competition
    euroleague_articles, el_count = await article_repo.list_articles(competition="יורוליג", limit=100)
    assert el_count > 0
    for art in euroleague_articles:
        assert art.competition == "יורוליג"

    # 5. Multi-criteria: Sport="כדורגל" AND Team="מכבי חיפה" AND Source="one"
    filtered_articles, f_count = await article_repo.list_articles(
        sport="כדורגל",
        team="מכבי חיפה",
        source_name="one",
        limit=100,
    )
    # Validate every result satisfies all three criteria simultaneously
    for art in filtered_articles:
        assert art.sport == "כדורגל"
        assert "מכבי חיפה" in art.teams_json
        assert art.source.name == "one"

    # 6. Multi-criteria: Sport="כדורסל" AND Competition="יורוליג" AND Team="מכבי תל אביב"
    maccabi_bb, maccabi_bb_count = await article_repo.list_articles(
        sport="כדורסל",
        competition="יורוליג",
        team="מכבי תל אביב",
        limit=100,
    )
    assert maccabi_bb_count > 0
    for art in maccabi_bb:
        assert art.sport == "כדורסל"
        assert art.competition == "יורוליג"
        assert "מכבי תל אביב" in art.teams_json

    # 7. Status filter
    pending_articles, p_count = await article_repo.list_articles(status=IngestionStatus.PENDING, limit=100)
    assert p_count == 15  # 60 // 4 = 15
    for art in pending_articles:
        assert art.ingestion_status == IngestionStatus.PENDING

    ai_articles, ai_count = await article_repo.list_articles(status=IngestionStatus.AI_PROCESSED, limit=100)
    assert ai_count == 45
    assert p_count + ai_count == 60

    # 8. Date range filtering
    base_time = datetime(2026, 8, 1, 10, 0, 0, tzinfo=timezone.utc)
    t_start = base_time + timedelta(days=2)
    t_end = base_time + timedelta(days=5)
    range_articles, range_count = await article_repo.list_articles(date_from=t_start, date_to=t_end, limit=100)
    assert range_count > 0
    for art in range_articles:
        pub = art.published_at.replace(tzinfo=timezone.utc) if art.published_at.tzinfo is None else art.published_at
        assert t_start <= pub <= t_end

    # 9. Disjoint criteria: Sport="טניס" AND Team="מכבי חיפה" -> must return 0
    disjoint_articles, d_count = await article_repo.list_articles(
        sport="טניס",
        team="מכבי חיפה",
    )
    assert d_count == 0
    assert len(disjoint_articles) == 0


# ==========================================
# Challenge 3: Hebrew Full-Text Substring Search
# ==========================================

@pytest.mark.asyncio
async def test_hebrew_fulltext_substring_search(db_session: AsyncSession):
    """
    Challenge 3:
    - Tests Hebrew substring matching across:
      1. original_title
      2. ai_headline
      3. cleaned_body / raw_paragraphs
      4. Hebrew words with apostrophes/quotes (בית"ר, ג'ודו)
      5. Substring search combined with specific category filters.
    """
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    sources = await source_repo.seed_default_sources()
    source_map = {s.name: s.id for s in sources}
    dataset = generate_50_plus_test_articles(source_map)

    for art_payload in dataset:
        await article_repo.upsert_article(art_payload)

    # 1. Search term appearing in original_title ("סנסציה גדולה")
    res1, count1 = await article_repo.list_articles(search_query="סנסציה גדולה")
    assert count1 > 0
    for art in res1:
        assert ("סנסציה גדולה" in art.original_title or
                (art.ai_headline and "סנסציה גדולה" in art.ai_headline) or
                (art.cleaned_body and "סנסציה גדולה" in art.cleaned_body))

    # 2. Search term appearing in ai_headline ("גברה על היריבה")
    res2, count2 = await article_repo.list_articles(search_query="גברה על היריבה")
    assert count2 > 0
    for art in res2:
        assert (art.ai_headline and "גברה על היריבה" in art.ai_headline) or (art.original_title and "גברה על היריבה" in art.original_title)

    # 3. Search term appearing in cleaned_body ("במחצית השנייה")
    res3, count3 = await article_repo.list_articles(search_query="במחצית השנייה")
    assert count3 > 0
    for art in res3:
        assert ("במחצית השנייה" in (art.cleaned_body or "") or
                "במחצית השנייה" in art.original_title or
                "במחצית השנייה" in (art.original_subtitle or ""))

    # 4. Hebrew terms with special characters: בית"ר and ג'ודו
    res_beitar, count_beitar = await article_repo.list_articles(search_query="בית\"ר")
    assert count_beitar > 0

    res_judo, count_judo = await article_repo.list_articles(search_query="ג'ודו")
    assert count_judo > 0

    # 5. Combined Hebrew search + facet filter
    # Search "זהבי" with sport="כדורגל"
    res_comb, count_comb = await article_repo.list_articles(
        search_query="זהבי",
        sport="כדורגל",
    )
    assert count_comb > 0
    for art in res_comb:
        assert art.sport == "כדורגל"
        text_content = f"{art.original_title} {art.original_subtitle or ''} {art.cleaned_body or ''} {art.ai_headline or ''}"
        assert "זהבי" in text_content

    # 6. Non-matching query returns 0
    res_none, count_none = await article_repo.list_articles(search_query="ביטוי_שאינו_קיים_בטוח_12345")
    assert count_none == 0
    assert len(res_none) == 0


# ==========================================
# Challenge 4: Pagination & Ordering
# ==========================================

@pytest.mark.asyncio
async def test_pagination_and_ordering_stress(db_session: AsyncSession):
    """
    Challenge 4:
    - Tests ordering by published_at DESC (and ASC).
    - Iterates pages with skip/limit to ensure zero duplicates and full partition coverage of 60 items.
    - Tests out-of-range skip boundary.
    """
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    sources = await source_repo.seed_default_sources()
    source_map = {s.name: s.id for s in sources}
    dataset = generate_50_plus_test_articles(source_map)

    for art_payload in dataset:
        await article_repo.upsert_article(art_payload)

    # 1. Verify DESC ordering
    all_articles, total = await article_repo.list_articles(limit=100, sort_desc=True)
    assert total == 60
    assert len(all_articles) == 60
    for i in range(len(all_articles) - 1):
        assert all_articles[i].published_at >= all_articles[i + 1].published_at

    # 2. Verify ASC ordering
    asc_articles, asc_total = await article_repo.list_articles(limit=100, sort_desc=False)
    assert asc_total == 60
    assert len(asc_articles) == 60
    for i in range(len(asc_articles) - 1):
        assert asc_articles[i].published_at <= asc_articles[i + 1].published_at

    # Check inverse symmetry
    assert all_articles[0].id == asc_articles[-1].id
    assert all_articles[-1].id == asc_articles[0].id

    # 3. Paged iteration (pages of 10)
    page_size = 10
    collected_ids = []
    for page in range(6):
        page_items, p_total = await article_repo.list_articles(skip=page * page_size, limit=page_size)
        assert p_total == 60
        assert len(page_items) == page_size
        collected_ids.extend([a.id for a in page_items])

    # Ensure no duplicates across pages and all 60 unique IDs are collected
    assert len(collected_ids) == 60
    assert len(set(collected_ids)) == 60

    # 4. Out of bounds offset
    oob_items, oob_total = await article_repo.list_articles(skip=1000, limit=20)
    assert oob_total == 60
    assert len(oob_items) == 0


# ==========================================
# Challenge 5: Transaction Rollback & Constraint Violations
# ==========================================

@pytest.mark.asyncio
async def test_transaction_rollback_on_constraint_violation(db_session: AsyncSession):
    """
    Challenge 5:
    - Verifies transaction rollback when unique constraint on canonical_url is violated.
    - Verifies foreign key violation rollback on invalid source_id.
    - Verifies batch transaction atomicity: if an error occurs mid-batch, rollback restores previous state cleanly.
    """
    source_repo = SourceRepository(db_session)
    article_repo = ArticleRepository(db_session)

    source, _ = await source_repo.create_or_get(
        SourceCreate(name="sport5", display_name="Sport5", base_url="https://sport5.co.il")
    )
    source_id = source.id
    now = datetime.now(timezone.utc)

    # 1. Insert valid initial article
    base_art = {
        "source_id": source_id,
        "canonical_url": "https://sport5.co.il/valid_art_1",
        "original_title": "כתבה תקינה 1",
        "published_at": now,
        "raw_paragraphs": ["תוכן תקין"],
    }
    art1, _ = await article_repo.upsert_article(base_art)
    await db_session.commit()
    art1_id = art1.id

    initial_count = await db_session.scalar(select(func.count(Article.id)))
    assert initial_count == 1

    # 2. Violate foreign key constraint (invalid source_id 999999) directly in session
    invalid_fk_article = Article(
        source_id=999999,
        canonical_url="https://sport5.co.il/invalid_fk",
        content_hash="hash_fk_fail",
        original_title="שגיאת מפתח זר",
        published_at=now,
    )
    db_session.add(invalid_fk_article)
    with pytest.raises(IntegrityError):
        await db_session.flush()

    # Perform rollback
    await db_session.rollback()

    # Verify session is healthy and initial count is still 1
    count_after_rollback = await db_session.scalar(select(func.count(Article.id)))
    assert count_after_rollback == 1
    existing = await article_repo.get_by_id(art1_id)
    assert existing is not None

    # 3. Violate unique canonical_url constraint directly via ORM insert
    dup_url_article = Article(
        source_id=source_id,
        canonical_url="https://sport5.co.il/valid_art_1",  # Same as art1
        content_hash="unique_hash_123",
        original_title="שגיאת כפילות",
        published_at=now,
    )
    db_session.add(dup_url_article)
    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()

    # Check DB integrity again
    count_after_dup_rollback = await db_session.scalar(select(func.count(Article.id)))
    assert count_after_dup_rollback == 1

    # 4. Atomic batch insertion test: insert 3 items, 4th item violates constraint
    batch_items = [
        Article(source_id=source_id, canonical_url=f"https://sport5.co.il/batch_{i}", content_hash=f"batch_hash_{i}", original_title=f"כותרת {i}", published_at=now)
        for i in range(3)
    ]
    # Add a 4th item with duplicate URL of art1
    batch_items.append(
        Article(source_id=source_id, canonical_url="https://sport5.co.il/valid_art_1", content_hash="batch_hash_fail", original_title="כשל", published_at=now)
    )

    for item in batch_items:
        db_session.add(item)

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()

    # Verify NONE of the 3 batch items were committed due to rollback
    final_count = await db_session.scalar(select(func.count(Article.id)))
    assert final_count == 1


# ==============================================================================
# MILESTONE 2: MULTI-SOURCE SCRAPERS & INGESTION ENGINE TESTS
# ==============================================================================

from fan_zone.scrapers.base import (
    BaseSourceParser,
    ExtractedArticle,
    ExtractedImage,
    normalize_canonical_url,
    compute_content_hash,
    clean_html_text,
    parse_datetime,
    extract_json_ld,
    extract_opengraph,
    extract_heuristic_dom,
)
from fan_zone.scrapers.sport5 import Sport5Parser
from fan_zone.scrapers.one import ONEParser
from fan_zone.scrapers.walla import WallaParser
from fan_zone.scrapers.ynet import YnetParser
from fan_zone.scrapers.sport1 import Sport1Parser
from fan_zone.scrapers.israel_hayom import IsraelHayomParser
from fan_zone.scrapers.haaretz import HaaretzParser
from fan_zone.scrapers.registry import ScraperRegistry, get_scraper, get_scraper_for_url, list_scrapers
from fan_zone.services.ingestion_service import IngestionService


class TestCanonicalUrlNormalization:
    """Unit tests for URL normalization, tracking parameter stripping, and canonicalization."""

    def test_strip_tracking_parameters(self):
        url = "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450000&utm_source=facebook&utm_medium=cpc&fbclid=IwAR12345&ref=hp"
        normalized = normalize_canonical_url(url)
        assert "utm_source" not in normalized
        assert "utm_medium" not in normalized
        assert "fbclid" not in normalized
        assert "ref=" not in normalized
        assert "FolderID=64" in normalized
        assert "docID=450000" in normalized
        assert normalized.startswith("https://www.sport5.co.il/articles.aspx?")

    def test_sort_query_parameters(self):
        url1 = "https://sports.walla.co.il/item/123456?b=2&a=1"
        url2 = "https://sports.walla.co.il/item/123456?a=1&b=2"
        assert normalize_canonical_url(url1) == normalize_canonical_url(url2)
        assert normalize_canonical_url(url1) == "https://sports.walla.co.il/item/123456?a=1&b=2"

    def test_lowercase_scheme_and_host(self):
        url = "HTTP://WWW.ONE.CO.IL/Article/2026/1234.html"
        normalized = normalize_canonical_url(url)
        assert normalized.startswith("https://www.one.co.il/Article/2026/1234.html")

    def test_strip_trailing_slash_and_fragment(self):
        url = "https://www.ynet.co.il/sport/article/r123456/#comments"
        normalized = normalize_canonical_url(url)
        assert normalized == "https://www.ynet.co.il/sport/article/r123456"

    def test_empty_and_invalid_inputs(self):
        assert normalize_canonical_url("") == ""
        assert normalize_canonical_url(None) == ""
        assert normalize_canonical_url("   ") == ""


class TestContentHashingDeduplication:
    """Unit tests for content fingerprinting and SHA-256 deduplication."""

    def test_deterministic_hash_output(self):
        title = "מכבי תל אביב ניצחה את ריאל מדריד"
        paragraphs = ["משחק מצוין של הצהובים.", "ווייד בולדווין הוביל את הקלעים."]
        h1 = compute_content_hash(title, paragraphs)
        h2 = compute_content_hash(title, paragraphs)
        assert h1 == h2
        assert len(h1) == 64

    def test_unicode_nfc_normalization(self):
        # Decomposed Hebrew vs Composed Hebrew
        composed = "מכבי חיפה"
        decomposed = unicodedata.normalize("NFD", composed)
        h_composed = compute_content_hash(composed, ["פסקת מבחן"])
        h_decomposed = compute_content_hash(decomposed, ["פסקת מבחן"])
        assert h_composed == h_decomposed

    def test_branding_suffix_stripping(self):
        title1 = "מכבי תל אביב הביסה את הפועל | ספורט 5"
        title2 = "מכבי תל אביב הביסה את הפועל - וואלה! ספורט"
        title3 = "מכבי תל אביב הביסה את הפועל"
        paragraphs = ["ניצחון ענק בדרבי התל אביבי."]
        assert compute_content_hash(title1, paragraphs) == compute_content_hash(title3, paragraphs)
        assert compute_content_hash(title2, paragraphs) == compute_content_hash(title3, paragraphs)

    def test_whitespace_normalization(self):
        title = " כותרת  עם   רווחים  "
        paragraphs = ["  פסקה   ראשונה \t ", "\n\n פסקה   שנייה   "]
        h1 = compute_content_hash(title, paragraphs)
        h2 = compute_content_hash("כותרת עם רווחים", ["פסקה ראשונה", "פסקה שנייה"])
        assert h1 == h2


class TestSport5Scraper:
    """Unit tests for Sport5 scraper with HTML fixtures."""

    @pytest.fixture
    def sport5_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>מכבי תל אביב גברה על ריאל | ספורט 5</title>
        </head>
        <body>
            <article class="article-content">
                <h1 class="article-title">ניצחון דרמטי: מכבי תל אביב גברה 82:85 על ריאל מדריד</h1>
                <h2 class="article-subtitle">משחק ענק של הצהובים בהיכל. ווייד בולדווין להט עם 28 נקודות.</h2>
                <span class="article-credit">רועי כהן</span>
                <span class="article-date">28.08.26 - 22:30</span>
                <div class="article-main-image">
                    <img src="https://images.sport5.co.il/main_123.jpg" alt="בולדווין חוגג" />
                    <div class="main-image-caption">בולדווין חוגג ניצחון (צילום: אלן שיבר)</div>
                </div>
                <div class="article-body">
                    <p>מכבי תל אביב השיגה הערב ניצחון יוקרתי במיוחד בהיכל מנורה מבטחים.</p>
                    <p>הצהובים של עודד קטש גברו 82:85 על ריאל מדריד במסגרת המחזור ה-15 של היורוליג.</p>
                    <p>ווייד בולדווין הצטיין עם 28 נקודות ו-6 אסיסטים והוביל את המנצחת.</p>
                </div>
                <div class="article-gallery">
                    <img src="https://images.sport5.co.il/gal_1.jpg" />
                    <img src="https://images.sport5.co.il/gal_2.jpg" />
                </div>
                <div class="article-tags">
                    <a href="/tag/1">מכבי תל אביב</a>
                    <a href="/tag/2">יורוליג</a>
                </div>
            </article>
        </body>
        </html>
        """

    def test_sport5_parsing(self, sport5_html):
        parser = Sport5Parser()
        url = "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450000"
        extracted = parser.parse_article_html(sport5_html, url)

        assert extracted is not None
        assert extracted.source_name == "Sport5"
        assert extracted.canonical_url == normalize_canonical_url(url)
        assert "ניצחון דרמטי" in extracted.original_title
        assert "ווייד בולדווין להט" in extracted.original_subtitle
        assert extracted.author == "רועי כהן"
        assert extracted.published_at.year == 2026
        assert extracted.published_at.month == 8
        assert extracted.published_at.day == 28
        assert len(extracted.paragraphs) == 3
        assert extracted.main_image is not None
        assert extracted.main_image.url == "https://images.sport5.co.il/main_123.jpg"
        assert "אלן שיבר" in (extracted.main_image.caption or "")
        assert len(extracted.gallery_images) == 2
        assert "מכבי תל אביב" in extracted.tags


class TestONEScraper:
    """Unit tests for ONE scraper with RSS and HTML fixtures."""

    @pytest.fixture
    def one_rss_xml(self):
        return """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
            <channel>
                <title>ONE Sport News</title>
                <item>
                    <title>מכבי חיפה ניצחה 0:2 את בית"ר ירושלים</title>
                    <link>https://www.one.co.il/Article/2026/456789.html?utm_source=rss</link>
                    <pubDate>Fri, 28 Aug 2026 21:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>
        """

    @pytest.fixture
    def one_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>ONE כתבה</title></head>
        <body>
            <div id="article-content">
                <h1 class="article-title">מכבי חיפה ניצחה 0:2 את בית"ר ירושלים בסמי עופר</h1>
                <h2 class="article-subtitle">דין דוד ודיא סבע הבקיעו לירוקים, שהעפילו לפסגת ליגת העל.</h2>
                <span class="article-writer">גידי ליפקין</span>
                <span class="article-date">28/08/2026 21:15</span>
                <div class="article-main-img">
                    <img src="https://images.one.co.il/images/d/dsm/123.jpg" />
                    <div class="img-credit">צילום: רדאד ג'בארה</div>
                </div>
                <div class="article-body-content">
                    <p>מכבי חיפה רשמה הערב ניצחון מרשים על בית"ר ירושלים באצטדיון סמי עופר.</p>
                    <p>הקבוצה של ברק בכר שלטה במשחק לכל אורכו והשיגה שלוש נקודות יקרות.</p>
                </div>
            </div>
        </body>
        </html>
        """

    def test_one_rss_parsing(self, one_rss_xml):
        parser = ONEParser()
        links = parser.parse_rss_feed(one_rss_xml)
        assert len(links) == 1
        assert "one.co.il" in links[0]

    def test_one_article_parsing(self, one_html):
        parser = ONEParser()
        url = "https://www.one.co.il/Article/2026/456789.html"
        extracted = parser.parse_article_html(one_html, url)
        assert extracted is not None
        assert extracted.source_name == "ONE"
        assert "מכבי חיפה ניצחה 0:2" in extracted.original_title
        assert "דין דוד ודיא סבע" in extracted.original_subtitle
        assert extracted.author == "גידי ליפקין"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image.url == "https://images.one.co.il/images/d/dsm/123.jpg"
        assert "רדאד ג'בארה" in (extracted.main_image.credit or "")


class TestWallaScraper:
    """Unit tests for Walla! Sports scraper with HTML fixtures."""

    @pytest.fixture
    def walla_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>וואלה! ספורט</title></head>
        <body>
            <article class="css-article-content">
                <h1 class="title">הפועל תל אביב הביסה את הפועל ירושלים בדרבי האדומות</h1>
                <h2 class="subtitle">תומר גינת כיכב עם 22 נקודות, הקבוצה של דדאס שמרה על המקום הראשון.</h2>
                <span class="author-name">אופיר סער</span>
                <time datetime="2026-08-28T21:30:00+03:00">יום שישי, 28 באוגוסט 2026, 21:30</time>
                <figure class="main-media">
                    <img src="https://img.wcdn.co.il/f_auto,q_auto,w_1000,t_54/12345.jpg" />
                    <figcaption>תומר גינת חוגג סל (צילום: ברני ארדוב)</figcaption>
                </figure>
                <div class="css-article-body">
                    <p>הפועל תל אביב המשיכה הערב את פתיחת העונה המצוינת שלה עם ניצחון מוחץ.</p>
                    <p>האדומים מתל אביב הובילו מהפתיחה ועד לסיום ולא השאירו סיכוי לירושלמים.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_walla_parsing(self, walla_html):
        parser = WallaParser()
        url = "https://sports.walla.co.il/item/3699999"
        extracted = parser.parse_article_html(walla_html, url)
        assert extracted is not None
        assert extracted.source_name == "Walla! Sports"
        assert "הפועל תל אביב הביסה" in extracted.original_title
        assert "תומר גינת כיכב" in extracted.original_subtitle
        assert extracted.author == "אופיר סער"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image is not None
        assert "wcdn.co.il" in extracted.main_image.url


class TestYnetScraper:
    """Unit tests for Ynet Sport scraper with HTML fixtures."""

    @pytest.fixture
    def ynet_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Ynet Sport</title>
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "NewsArticle",
                "headline": "ערן זהבי חתם על הארכת חוזה במכבי תל אביב",
                "datePublished": "2026-08-28T19:45:00+03:00",
                "author": {"@type": "Person", "name": "נדב צנציפר"}
            }
            </script>
        </head>
        <body>
            <article data-component="article">
                <h1 class="mainTitle">ערן זהבי חתם על הארכת חוזה במכבי תל אביב</h1>
                <h2 class="subTitle">הכוכב הוותיק ימשיך לעונה נוספת בקריית שלום: "זה הבית שלי".</h2>
                <div class="authorName">נדב צנציפר</div>
                <time class="date">28.08.26, 19:45</time>
                <figure data-component="media">
                    <img src="https://images.ynet.co.il/PicServer5/2026/08/28/12345_wa.jpg" />
                    <figcaption><span class="caption">ערן זהבי חותם על החוזה</span> <span class="credit">(צילום: ראובן שוורץ)</span></figcaption>
                </figure>
                <div data-component="article-body">
                    <p>ערן זהבי ומכבי תל אביב הגיעו היום לסיכום על הארכת חוזהו בעונה נוספת.</p>
                    <p>החלוץ הביע את שביעות רצונו מההסכם והבטיח להמשיך להוביל את המועדון לתארים.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_ynet_parsing(self, ynet_html):
        parser = YnetParser()
        url = "https://www.ynet.co.il/sport/israelisoccer/article/bj123456"
        extracted = parser.parse_article_html(ynet_html, url)
        assert extracted is not None
        assert extracted.source_name == "Ynet Sport"
        assert "ערן זהבי חתם" in extracted.original_title
        assert "הכוכב הוותיק ימשיך" in extracted.original_subtitle
        assert extracted.author == "נדב צנציפר"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image is not None


class TestSport1Scraper:
    """Unit tests for Sport1 scraper with HTML fixtures."""

    @pytest.fixture
    def sport1_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>ספורט 1</title></head>
        <body>
            <article class="article-wrapper">
                <h1 class="article-title">ברצלונה ניצחה 1:3 את ריאל מדריד בקלאסיקו</h1>
                <h2 class="article-subtitle">לאמין ימאל וראפיניה כיכבו בניצחון החוץ הענק בסנטיאגו ברנבאו.</h2>
                <div class="author-details"><span class="name">יניב טוכמן</span></div>
                <time class="entry-date">28/08/2026 23:00</time>
                <figure class="featured-image">
                    <img src="https://sport1.maariv.co.il/wp-content/uploads/2026/08/clasico.jpg" />
                    <figcaption class="image-caption">לאמין ימאל חוגג שער (רויטרס)</figcaption>
                </figure>
                <div class="article-body">
                    <p>ברצלונה השיגה ניצחון יוקרתי במיוחד בקלאסיקו הספרדי.</p>
                    <p>הקטלאנים של האנזי פליק הציגו כדורגל מרהיב והגדילו את הפער בפסגה.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_sport1_parsing(self, sport1_html):
        parser = Sport1Parser()
        url = "https://sport1.maariv.co.il/world-soccer/article/998877/"
        extracted = parser.parse_article_html(sport1_html, url)
        assert extracted is not None
        assert extracted.source_name == "Sport1"
        assert "ברצלונה ניצחה 1:3" in extracted.original_title
        assert "לאמין ימאל" in extracted.original_subtitle
        assert extracted.author == "יניב טוכמן"
        assert len(extracted.paragraphs) == 2


class TestIsraelHayomScraper:
    """Unit tests for Israel Hayom scraper with HTML fixtures."""

    @pytest.fixture
    def israel_hayom_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>ישראל היום ספורט</title></head>
        <body>
            <article class="article-page">
                <h1 class="article-title">דני אבדיה קלע 25 נקודות בניצחון פורטלנד</h1>
                <h2 class="article-subtitle">משחק שיא לישראלי שתרם גם 10 ריבאונדים ו-7 אסיסטים.</h2>
                <div class="writer-name">אבי סגל</div>
                <time class="article-date">28/8/2026, 06:30</time>
                <div class="article-main-media">
                    <img src="https://www.israelhayom.co.il/wp-content/uploads/2026/08/avdija.jpg" />
                </div>
                <div class="article-content">
                    <p>דני אבדיה ממשיך להוכיח את מעמדו כאחד השחקנים המובילים של פורטלנד טרייל בלייזרס.</p>
                    <p>הפורוורד הישראלי הצטיין הלילה בניצחון על גולדן סטייט ווריורס.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_israel_hayom_parsing(self, israel_hayom_html):
        parser = IsraelHayomParser()
        url = "https://www.israelhayom.co.il/sport/nba/article/1654321"
        extracted = parser.parse_article_html(israel_hayom_html, url)
        assert extracted is not None
        assert extracted.source_name == "Israel Hayom"
        assert "דני אבדיה קלע" in extracted.original_title
        assert "משחק שיא לישראלי" in extracted.original_subtitle
        assert extracted.author == "אבי סגל"
        assert len(extracted.paragraphs) == 2


class TestHaaretzScraper:
    """Unit tests for Haaretz scraper with HTML fixtures."""

    @pytest.fixture
    def haaretz_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>הארץ ספורט</title>
            <meta property="og:title" content="המהפכה השקטה של ענף השחייה בישראל" />
            <meta property="og:description" content="ההישגים באליפויות העולם מעידים על תוכנית עבודה יסודית וארוכת טווח." />
            <meta property="og:image" content="https://img.haarets.co.il/img_123.jpg" />
        </head>
        <body>
            <article data-test="articleBody">
                <h1 data-test="articleHeadline">המהפכה השקטה של ענף השחייה בישראל</h1>
                <h2 data-test="articleSubtitle">ההישגים באליפויות העולם מעידים על תוכנית עבודה יסודית וארוכת טווח.</h2>
                <span data-test="authorName">איתמר קציר</span>
                <time data-test="publishDate">2026-08-28T18:00:00.000Z</time>
                <figure data-test="mainFigure">
                    <img src="https://img.haarets.co.il/img_123.jpg" />
                    <figcaption data-test="caption">אנסטסיה גורבנקו במים (צילום: אי-פי)</figcaption>
                </figure>
                <p data-test="articleParagraph">השחייה הישראלית רושמת את אחד הפרקים המרשימים ביותר בתולדותיה.</p>
                <p data-test="articleParagraph">דור חדש של שחיינים צעירים מגיע לגמרים עולמיים ומביא מדליות יוקרתיות.</p>
            </article>
        </body>
        </html>
        """

    def test_haaretz_parsing(self, haaretz_html):
        parser = HaaretzParser()
        url = "https://www.haaretz.co.il/sport/swimming/2026-08-28/ty-article/0000018f-1234"
        extracted = parser.parse_article_html(haaretz_html, url)
        assert extracted is not None
        assert extracted.source_name == "Haaretz"
        assert "המהפכה השקטה" in extracted.original_title
        assert extracted.author == "איתמר קציר"
        assert len(extracted.paragraphs) == 2


class Test5TierFallbackCascade:
    """Unit tests for the 5-tier extraction fallback cascade."""

    def test_fallback_to_json_ld_when_no_css(self):
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@type": "NewsArticle",
                "headline": "כותרת מ-JSON-LD",
                "description": "תיאור מ-JSON-LD",
                "articleBody": "פסקה ראשונה מהגוף.\nפסקה שנייה מהגוף.",
                "author": "ישראל ישראלי",
                "datePublished": "2026-08-28T12:00:00Z",
                "image": "https://example.com/ld_image.jpg"
            }
            </script>
        </head>
        <body>
            <div class="custom-unknown-container">תוכן ללא סלקטורים מוכרים</div>
        </body>
        </html>
        """
        parser = BaseSourceParser()
        extracted = parser.parse_article_html(html, "https://example.com/article/1")
        assert extracted.original_title == "כותרת מ-JSON-LD"
        assert extracted.original_subtitle == "תיאור מ-JSON-LD"
        assert len(extracted.paragraphs) == 2
        assert extracted.author == "ישראל ישראלי"
        assert extracted.main_image.url == "https://example.com/ld_image.jpg"

    def test_fallback_to_opengraph_when_no_json_ld(self):
        html = """
        <html>
        <head>
            <meta property="og:title" content="כותרת OpenGraph" />
            <meta property="og:description" content="תיאור OpenGraph" />
            <meta property="og:image" content="https://example.com/og_image.jpg" />
        </head>
        <body>
            <p>טקסט פסקה באורך סביר מעל עשרים תווים לבדיקת DOM.</p>
        </body>
        </html>
        """
        parser = BaseSourceParser()
        extracted = parser.parse_article_html(html, "https://example.com/article/2")
        assert extracted.original_title == "כותרת OpenGraph"
        assert extracted.original_subtitle == "תיאור OpenGraph"
        assert extracted.main_image.url == "https://example.com/og_image.jpg"

    def test_fallback_to_dom_heuristics(self):
        html = """
        <html>
        <head><title>כותרת הטאג כותרת | אתר ספורט</title></head>
        <body>
            <h1>כותרת ראשית H1</h1>
            <p>פסקה ראשונה בגוף הכתבה שמכילה מספיק תווים כדי להיחשב טקסט תוכן אמיתי.</p>
            <p>פסקה שנייה בגוף הכתבה שמכילה גם היא מספיק תווים כדי להילכד על ידי הניתוח.</p>
            <img src="https://example.com/content_img.jpg" />
        </body>
        </html>
        """
        parser = BaseSourceParser()
        extracted = parser.parse_article_html(html, "https://example.com/article/3")
        assert extracted.original_title == "כותרת ראשית H1"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image.url == "https://example.com/content_img.jpg"


class TestScraperRegistry:
    """Unit tests for ScraperRegistry lookups and url domain matching."""

    def test_registry_lookups(self):
        registry = ScraperRegistry()
        assert registry.get_scraper("sport5").source_name == "Sport5"
        assert registry.get_scraper("one").source_name == "ONE"
        assert registry.get_scraper("walla").source_name == "Walla! Sports"
        assert registry.get_scraper("ynet").source_name == "Ynet Sport"
        assert registry.get_scraper("sport1").source_name == "Sport1"
        assert registry.get_scraper("israel_hayom").source_name == "Israel Hayom"
        assert registry.get_scraper("haaretz").source_name == "Haaretz"

    def test_url_domain_detection(self):
        registry = ScraperRegistry()
        assert registry.get_scraper_for_url("https://www.sport5.co.il/articles.aspx?docID=1").source_name == "Sport5"
        assert registry.get_scraper_for_url("https://www.one.co.il/Article/123.html").source_name == "ONE"
        assert registry.get_scraper_for_url("https://sports.walla.co.il/item/123").source_name == "Walla! Sports"
        assert registry.get_scraper_for_url("https://www.ynet.co.il/sport/article/123").source_name == "Ynet Sport"
        assert registry.get_scraper_for_url("https://sport1.maariv.co.il/article/123").source_name == "Sport1"
        assert registry.get_scraper_for_url("https://www.israelhayom.co.il/sport/article/123").source_name == "Israel Hayom"
        assert registry.get_scraper_for_url("https://www.haaretz.co.il/sport/123").source_name == "Haaretz"

    def test_list_all_scrapers(self):
        scrapers = list_scrapers()
        assert len(scrapers) == 7
        codes = {s.source_code for s in scrapers}
        assert codes == {"sport5", "one", "walla", "ynet", "sport1", "israel_hayom", "haaretz"}


class MockAIAnalysisResult:
    """Mock AI enrichment result."""
    def __init__(self, headline, subheadline, sport, teams, players, competition, tags):
        self.headline = headline
        self.subheadline = subheadline
        self.sport = sport
        self.teams = teams
        self.players = players
        self.competition = competition
        self.tags = tags


class MockAIProcessor:
    """Mock AI processor for integration tests."""
    async def analyze_article(self, title: str, subtitle: Optional[str], body: str):
        return MockAIAnalysisResult(
            headline="כותרת AI עובדתית ומדויקת ללא קליקבייט",
            subheadline="כותרת משנה AI מתמצתת את עיקר ההתרחשות במשפט אחד.",
            sport="כדורסל",
            teams=["מכבי תל אביב", "ריאל מדריד"],
            players=["ווייד בולדווין", "עודד קטש"],
            competition="יורוליג",
            tags=["מכבי תל אביב", "יורוליג", "כדורסל"],
        )


@pytest.mark.asyncio
class TestIngestionServiceIntegration:
    """Integration tests for IngestionService with seeded SQLite database and mock HTTP/AI."""

    async def test_ingest_extracted_article_with_ai(self, seeded_session: AsyncSession):
        ai = MockAIProcessor()
        service = IngestionService(db=seeded_session, ai_processor=ai)
        source = await SourceRepository(seeded_session).get_by_code("sport5")

        extracted = ExtractedArticle(
            source_name="Sport5",
            source_domain="sport5.co.il",
            original_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=999999",
            canonical_url="https://www.sport5.co.il/articles.aspx?FolderID=64&docID=999999",
            content_hash=compute_content_hash("כותרת מקורית", ["פסקה אחת", "פסקה שתיים"]),
            original_title="כותרת מקורית וסנסציונית: אתם לא תאמינו מה קרה!",
            original_subtitle="כותרת משנה מקורית",
            author="כתב ספורט 5",
            published_at=datetime(2026, 8, 28, 20, 0, 0, tzinfo=timezone.utc),
            paragraphs=["פסקה אחת", "פסקה שתיים"],
            raw_body_text="פסקה אחת\n\nפסקה שתיים",
            main_image=ExtractedImage(url="https://images.sport5.co.il/lead.jpg", caption="תמונה ראשית", is_main=True),
            gallery_images=[ExtractedImage(url="https://images.sport5.co.il/gal1.jpg")],
            tags=["ספורט 5"],
        )

        article, is_created = await service.process_and_persist_article(extracted, source)
        assert is_created is True
        assert article is not None
        assert article.id is not None
        assert article.ai_headline == "כותרת AI עובדתית ומדויקת ללא קליקבייט"
        assert article.ai_subheadline == "כותרת משנה AI מתמצתת את עיקר ההתרחשות במשפט אחד."
        assert article.sport == "כדורסל"
        assert article.competition == "יורוליג"
        assert "מכבי תל אביב" in article.teams_json
        assert "ווייד בולדווין" in article.players_json
        assert article.ingestion_status == IngestionStatus.AI_PROCESSED
        assert len(article.media) == 2
        assert article.media[0].is_primary is True
        assert article.media[0].url == "https://images.sport5.co.il/lead.jpg"

    async def test_ingest_deduplication_by_url_and_hash(self, seeded_session: AsyncSession):
        service = IngestionService(db=seeded_session)
        source = await SourceRepository(seeded_session).get_by_code("one")

        extracted = ExtractedArticle(
            source_name="ONE",
            source_domain="one.co.il",
            original_url="https://www.one.co.il/Article/2026/888888.html",
            canonical_url="https://www.one.co.il/Article/2026/888888.html",
            content_hash=compute_content_hash("כותרת כפילות", ["פסקה א", "פסקה ב"]),
            original_title="כותרת כפילות",
            published_at=datetime(2026, 8, 28, 15, 0, 0, tzinfo=timezone.utc),
            paragraphs=["פסקה א", "פסקה ב"],
            raw_body_text="פסקה א\n\nפסקה ב",
        )

        art1, created1 = await service.process_and_persist_article(extracted, source)
        assert created1 is True

        # Second ingestion with identical content hash
        art2, created2 = await service.process_and_persist_article(extracted, source)
        assert created2 is False
        assert art2.id == art1.id

    async def test_ai_failure_fallback_resilience(self, seeded_session: AsyncSession):
        class FailingAIProcessor:
            async def analyze_article(self, title, subtitle, body):
                raise TimeoutError("Gemini API timed out after 10s")

        service = IngestionService(db=seeded_session, ai_processor=FailingAIProcessor())
        source = await SourceRepository(seeded_session).get_by_code("walla")

        extracted = ExtractedArticle(
            source_name="Walla! Sports",
            source_domain="walla.co.il",
            original_url="https://sports.walla.co.il/item/7777777",
            canonical_url="https://sports.walla.co.il/item/7777777",
            content_hash=compute_content_hash("כותרת כשל AI", ["פסקה אחת"]),
            original_title="כותרת כשל AI",
            original_subtitle="משנה כשל AI",
            published_at=datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc),
            paragraphs=["פסקה אחת"],
            raw_body_text="פסקה אחת",
        )

        art, is_created = await service.process_and_persist_article(extracted, source)
        assert is_created is True
        assert art.ingestion_status == IngestionStatus.AI_FALLBACK
        assert "Gemini API timed out" in (art.error_message or "")
        assert art.ai_headline == "כותרת כשל AI"
