"""Unit tests for SQLAlchemy ORM models (Milestone 3)."""

from datetime import datetime, timezone
import pytest
from sqlalchemy import DateTime, Integer, JSON, String, Text

from db.session import Base
from models.feed import ArticleModel, utc_now


@pytest.mark.unit
class TestArticleModelSchema:
    """Unit tests validating ArticleModel schema, column definitions, and constraints."""

    def test_table_name(self):
        """Verify the database table name is 'articles'."""
        assert ArticleModel.__tablename__ == "articles"

    def test_all_expected_columns_exist(self):
        """Verify all mandatory and optional columns exist in the table metadata."""
        cols = ArticleModel.__table__.columns
        expected_columns = {
            "id",
            "title",
            "url",
            "publisher",
            "published_at",
            "raw_body",
            "micro_summary",
            "tags",
            "tone",
            "context_label",
            "category",
            "author",
            "image_url",
            "created_at",
            "updated_at",
        }
        assert expected_columns.issubset(set(cols.keys()))

    def test_primary_key_column(self):
        """Verify 'id' is the integer primary key."""
        col = ArticleModel.__table__.columns["id"]
        assert col.primary_key is True
        assert isinstance(col.type, Integer)

    def test_unique_url_constraint(self):
        """Verify 'url' column is marked unique and indexed."""
        col = ArticleModel.__table__.columns["url"]
        assert col.unique is True or col.index is True
        assert isinstance(col.type, String)
        assert col.type.length == 1000

    def test_column_nullability_rules(self):
        """Verify required fields are not nullable while optional fields are nullable."""
        cols = ArticleModel.__table__.columns

        # Non-nullable required fields
        non_nullable_fields = [
            "title",
            "url",
            "publisher",
            "published_at",
            "raw_body",
            "micro_summary",
            "tags",
            "tone",
            "context_label",
            "created_at",
            "updated_at",
        ]
        for field in non_nullable_fields:
            assert cols[field].nullable is False, f"Field '{field}' should be non-nullable"

        # Nullable optional metadata fields
        nullable_fields = ["category", "author", "image_url"]
        for field in nullable_fields:
            assert cols[field].nullable is True, f"Field '{field}' should be nullable"

    def test_column_types(self):
        """Verify column types match the architectural specifications."""
        cols = ArticleModel.__table__.columns
        assert isinstance(cols["title"].type, String)
        assert cols["title"].type.length == 500
        assert isinstance(cols["publisher"].type, String)
        assert cols["publisher"].type.length == 50
        assert isinstance(cols["published_at"].type, DateTime)
        assert cols["published_at"].type.timezone is True
        assert isinstance(cols["raw_body"].type, Text)
        assert isinstance(cols["micro_summary"].type, Text)
        assert isinstance(cols["tags"].type, JSON)
        assert isinstance(cols["tone"].type, String)
        assert cols["tone"].type.length == 20
        assert isinstance(cols["context_label"].type, String)
        assert cols["context_label"].type.length == 50
        assert isinstance(cols["category"].type, String)
        assert cols["category"].type.length == 100
        assert isinstance(cols["author"].type, String)
        assert cols["author"].type.length == 100
        assert isinstance(cols["image_url"].type, String)
        assert cols["image_url"].type.length == 1000
        assert isinstance(cols["created_at"].type, DateTime)
        assert isinstance(cols["updated_at"].type, DateTime)

    def test_indexed_columns(self):
        """Verify that high-frequency query columns have indexes configured."""
        cols = ArticleModel.__table__.columns
        indexed_fields = ["url", "publisher", "published_at", "tone", "context_label"]
        for field in indexed_fields:
            assert cols[field].index is True or cols[field].unique is True, (
                f"Field '{field}' should be indexed"
            )


@pytest.mark.unit
class TestArticleModelInstance:
    """Unit tests validating ArticleModel instance behavior, repr, serialization, and helpers."""

    def test_model_instantiation(self):
        """Verify creating an ArticleModel instance with valid fields."""
        pub_date = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)
        article = ArticleModel(
            id=1,
            title="מכבי תל אביב ניצחה ביורוליג",
            url="https://www.sport5.co.il/articles.aspx?docID=12345",
            publisher="sport5",
            published_at=pub_date,
            raw_body="טקסט מלא של הכתבה",
            micro_summary="מכבי תל אביב גברה על ריאל מדריד ביורוליג.",
            tags=["מכבי תל אביב", "יורוליג"],
            tone="hype",
            context_label="יורוליג",
            category="כדורסל",
            author="עמרי פולק",
            image_url="https://images.sport5.co.il/pic.jpg",
        )

        assert article.id == 1
        assert article.title == "מכבי תל אביב ניצחה ביורוליג"
        assert article.url == "https://www.sport5.co.il/articles.aspx?docID=12345"
        assert article.publisher == "sport5"
        assert article.published_at == pub_date
        assert article.tags == ["מכבי תל אביב", "יורוליג"]
        assert article.tone == "hype"
        assert article.category == "כדורסל"

    def test_model_repr_string(self):
        """Verify __repr__ formats a concise informative representation."""
        article = ArticleModel(
            id=42,
            title="כותרת קצרה",
            publisher="ynet",
        )
        repr_str = repr(article)
        assert "<ArticleModel" in repr_str
        assert "id=42" in repr_str
        assert "publisher='ynet'" in repr_str
        assert "title='כותרת קצרה'" in repr_str

    def test_model_repr_truncates_long_title(self):
        """Verify __repr__ truncates titles exceeding 30 characters."""
        long_title = "כותרת ארוכה מאוד מאוד של כתבת ספורט מרכזית בישראל"
        article = ArticleModel(
            id=10,
            title=long_title,
            publisher="one",
        )
        repr_str = repr(article)
        assert "..." in repr_str

    def test_to_dict_serialization(self):
        """Verify to_dict returns a complete dictionary matching model attributes."""
        pub_date = datetime(2026, 8, 29, 10, 0, 0, tzinfo=timezone.utc)
        article = ArticleModel(
            id=7,
            title="הפועל תל אביב החתימה שחקן",
            url="https://www.ynet.co.il/article/123",
            publisher="ynet",
            published_at=pub_date,
            raw_body="גוף הכתבה",
            micro_summary="הפועל תל אביב השלימה החתמה חשובה.",
            tags=["הפועל תל אביב", "כדורגל ישראלי"],
            tone="objective",
            context_label="העברות",
            category="ליגת העל",
            author="גידי ליפקין",
            image_url=None,
        )

        d = article.to_dict()
        assert d["id"] == 7
        assert d["title"] == "הפועל תל אביב החתימה שחקן"
        assert d["url"] == "https://www.ynet.co.il/article/123"
        assert d["publisher"] == "ynet"
        assert d["tags"] == ["הפועל תל אביב", "כדורגל ישראלי"]
        assert d["tone"] == "objective"
        assert d["context_label"] == "העברות"
        assert d["author"] == "גידי ליפקין"
        assert d["image_url"] is None

    def test_utc_now_helper(self):
        """Verify utc_now returns a timezone-aware UTC datetime."""
        now = utc_now()
        assert isinstance(now, datetime)
        assert now.tzinfo is not None
        assert now.tzinfo == timezone.utc
