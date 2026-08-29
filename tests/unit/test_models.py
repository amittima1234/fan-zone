"""Unit tests for SQLAlchemy 2.0 ORM models and relationships."""

import pytest
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fan_zone.config import Settings
from fan_zone.models.source import Source
from fan_zone.models.article import Article
from fan_zone.models.media import ArticleMedia
from fan_zone.models.tag import Tag, ArticleTag
from fan_zone.models.enums import IngestionStatus, MediaType, TagType


@pytest.mark.asyncio
async def test_config_settings_and_normalization():
    """Test Settings defaults and URL normalizers."""
    settings = Settings(
        DATABASE_URL="sqlite:///./test.db",
        ENVIRONMENT="testing",
        GEMINI_MODEL="gemini-2.5-flash",
    )
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./test.db"
    assert settings.is_testing is True
    assert settings.is_production is False

    pg_settings = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/fanzone")
    assert pg_settings.DATABASE_URL == "postgresql+asyncpg://user:pass@localhost:5432/fanzone"


@pytest.mark.asyncio
async def test_source_model_creation(db_session: AsyncSession):
    """Test creating a Source and reading its properties."""
    source = Source(
        name="sport5",
        display_name="Sport5",
        base_url="https://www.sport5.co.il",
        feed_url="https://www.sport5.co.il/rss.xml",
        is_active=True,
        poll_interval_seconds=300,
    )
    db_session.add(source)
    await db_session.flush()

    assert source.id is not None
    assert source.name == "sport5"
    assert source.code == "sport5"
    assert source.display_name == "Sport5"
    assert source.is_active is True
    assert source.created_at is not None
    assert source.updated_at is not None
    assert "sport5" in repr(source)


@pytest.mark.asyncio
async def test_source_unique_name_constraint(db_session: AsyncSession):
    """Test unique name constraint on Source model."""
    s1 = Source(name="one", display_name="ONE 1", base_url="https://one.co.il")
    s2 = Source(name="one", display_name="ONE 2", base_url="https://one.co.il")
    db_session.add(s1)
    await db_session.flush()

    db_session.add(s2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_tag_model_and_enums(db_session: AsyncSession):
    """Test Tag creation, slug, and tag types."""
    tag = Tag(
        name="מכבי חיפה",
        slug="maccabi-haifa",
        tag_type=TagType.TEAM,
        article_count=5,
    )
    db_session.add(tag)
    await db_session.flush()

    assert tag.id is not None
    assert tag.name == "מכבי חיפה"
    assert tag.tag_type == TagType.TEAM
    assert tag.article_count == 5
    assert "מכבי חיפה" in repr(tag)


@pytest.mark.asyncio
async def test_tag_unique_name_constraint(db_session: AsyncSession):
    """Test unique constraint on Tag name."""
    t1 = Tag(name="כדורגל", slug="football", tag_type=TagType.SPORT)
    t2 = Tag(name="כדורגל", slug="football", tag_type=TagType.SPORT)
    db_session.add(t1)
    await db_session.flush()

    db_session.add(t2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_article_model_and_relations(db_session: AsyncSession):
    """Test Article creation, JSON columns, media and tag relations."""
    source = Source(name="walla", display_name="Walla! Sports", base_url="https://sports.walla.co.il")
    db_session.add(source)
    await db_session.flush()

    published_time = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
    article = Article(
        source_id=source.id,
        canonical_url="https://sports.walla.co.il/item/3600000",
        content_hash="abc123hash456",
        original_title="מכבי תל אביב הודיעה על החתמת זר חדש",
        original_subtitle="הרכש הנוצץ יצטרף לסגל של עודד קטש",
        author="אורי אוזן",
        published_at=published_time,
        raw_paragraphs=["פסקה ראשונה", "פסקה שנייה"],
        cleaned_body="פסקה ראשונה\n\nפסקה שנייה",
        sport="כדורסל",
        competition="יורוליג",
        teams_json=["מכבי תל אביב"],
        players_json=["עודד קטש"],
        tags_json=["החתמה", "זר חדש"],
        ingestion_status=IngestionStatus.AI_PROCESSED,
    )
    db_session.add(article)
    await db_session.flush()

    assert article.id is not None
    assert article.source_id == source.id
    assert article.paragraphs == ["פסקה ראשונה", "פסקה שנייה"]
    assert article.original_subheadline == "הרכש הנוצץ יצטרף לסגל של עודד קטש"
    assert article.teams == ["מכבי תל אביב"]
    assert article.players == ["עודד קטש"]
    assert article.ingestion_status == IngestionStatus.AI_PROCESSED

    # Add media
    media1 = ArticleMedia(
        article_id=article.id,
        url="https://sports.walla.co.il/img1.jpg",
        media_type=MediaType.IMAGE,
        caption="השחקן החדש במדים",
        credit="וואלה ספורט",
        is_primary=True,
        position_index=0,
    )
    media2 = ArticleMedia(
        article_id=article.id,
        url="https://sports.walla.co.il/vid1.mp4",
        media_type=MediaType.VIDEO,
        caption="ביצועי השחקן",
        is_primary=False,
        position_index=1,
    )
    db_session.add_all([media1, media2])

    # Add tag associations
    tag1 = Tag(name="כדורסל", slug="basketball", tag_type=TagType.SPORT)
    tag2 = Tag(name="מכבי תל אביב", slug="maccabi-tel-aviv", tag_type=TagType.TEAM)
    db_session.add_all([tag1, tag2])
    await db_session.flush()

    art_tag1 = ArticleTag(article_id=article.id, tag_id=tag1.id)
    art_tag2 = ArticleTag(article_id=article.id, tag_id=tag2.id)
    db_session.add_all([art_tag1, art_tag2])
    await db_session.flush()

    art_id = article.id
    db_session.expire_all()

    # Verify query with relations
    stmt = select(Article).where(Article.id == art_id)
    res = await db_session.execute(stmt)
    fetched = res.scalar_one()
    assert len(fetched.media) == 2
    assert fetched.lead_image is not None
    assert fetched.lead_image.url == "https://sports.walla.co.il/img1.jpg"
    assert len(fetched.article_tags) == 2
    assert len(fetched.tags) == 2
    assert "מכבי תל אביב" in repr(fetched)


@pytest.mark.asyncio
async def test_article_unique_constraints(db_session: AsyncSession):
    """Test unique constraints on canonical_url and content_hash."""
    source = Source(name="ynet", display_name="Ynet Sport", base_url="https://ynet.co.il/sport")
    db_session.add(source)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    a1 = Article(
        source_id=source.id,
        canonical_url="https://www.ynet.co.il/sport/article/1",
        content_hash="hash_alpha",
        original_title="כותרת ראשונה",
        published_at=now,
    )
    db_session.add(a1)
    await db_session.flush()

    # Duplicate canonical_url
    a2 = Article(
        source_id=source.id,
        canonical_url="https://www.ynet.co.il/sport/article/1",
        content_hash="hash_beta",
        original_title="כותרת שונה",
        published_at=now,
    )
    db_session.add(a2)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_cascade_deletion(db_session: AsyncSession):
    """Test that deleting an Article cascades to Media and ArticleTags but keeps Tags."""
    source = Source(name="sport1", display_name="Sport1", base_url="https://sport1.maariv.co.il")
    db_session.add(source)
    await db_session.flush()

    now = datetime.now(timezone.utc)
    article = Article(
        source_id=source.id,
        canonical_url="https://sport1.maariv.co.il/article/100",
        content_hash="hash_cascade_test",
        original_title="מבחן מחיקה",
        published_at=now,
    )
    db_session.add(article)
    await db_session.flush()

    media = ArticleMedia(
        article_id=article.id,
        url="https://sport1.maariv.co.il/photo.jpg",
        is_primary=True,
    )
    tag = Tag(name="טניס", slug="tennis", tag_type=TagType.SPORT)
    db_session.add_all([media, tag])
    await db_session.flush()

    art_tag = ArticleTag(article_id=article.id, tag_id=tag.id)
    db_session.add(art_tag)
    await db_session.flush()

    # Delete article
    await db_session.delete(article)
    await db_session.flush()

    # Check that ArticleMedia and ArticleTag were deleted
    media_res = await db_session.execute(select(ArticleMedia).where(ArticleMedia.article_id == article.id))
    assert media_res.scalar_one_or_none() is None

    art_tag_res = await db_session.execute(select(ArticleTag).where(ArticleTag.article_id == article.id))
    assert art_tag_res.scalar_one_or_none() is None

    # Tag itself should still exist
    tag_res = await db_session.execute(select(Tag).where(Tag.id == tag.id))
    assert tag_res.scalar_one_or_none() is not None
