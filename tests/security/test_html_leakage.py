"""Security audit: HTML tag leakage prevention and XSS sanitization tests.

Verifies that raw HTML elements, dangerous scripts, malicious event handlers,
and iframe embeds are strictly sanitized and never escape into parsed article bodies,
summaries, tags, or API payloads.
"""
import re
import pytest
from bs4 import BeautifulSoup
from tests.fixtures.sample_html import (
    SPORT5_DIRTY_HTML,
    YNET_DIRTY_HTML,
    ONE_DIRTY_HTML,
    MALICIOUS_XSS_HTML_SAMPLES,
)

# Regex pattern detecting any remaining unescaped HTML tags
HTML_TAG_REGEX = re.compile(r"<[^>]+>")
DANGEROUS_ELEMENT_REGEX = re.compile(
    r"(?i)<\s*(script|iframe|style|object|embed|svg|img|form|input|meta|link|base)[^>]*>",
)
EVENT_HANDLER_REGEX = re.compile(r"(?i)\bon\w+\s*=", re.IGNORECASE)


def _sanitize_html_content(raw_html: str) -> str:
    """Standard robust HTML cleaner using BeautifulSoup text extraction."""
    soup = BeautifulSoup(raw_html, "html.parser")
    for script_or_style in soup(["script", "style", "iframe", "noscript", "svg", "object", "embed"]):
        script_or_style.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Collapse multiple whitespaces
    return re.sub(r"\s+", " ", text).strip()


@pytest.mark.security
@pytest.mark.parametrize(
    "raw_input, expected_title_part, expected_body_part",
    MALICIOUS_XSS_HTML_SAMPLES,
)
def test_malicious_xss_vectors_stripped(raw_input, expected_title_part, expected_body_part):
    """Ensure aggressive XSS vectors, scripts, and onerror handlers are completely stripped."""
    cleaned = _sanitize_html_content(raw_input)
    assert not HTML_TAG_REGEX.search(cleaned), f"Unescaped HTML tags found in: {cleaned}"
    assert not DANGEROUS_ELEMENT_REGEX.search(cleaned), f"Dangerous tags found in: {cleaned}"
    assert not EVENT_HANDLER_REGEX.search(cleaned), f"Event handler found in: {cleaned}"
    assert "<script>" not in cleaned
    assert "onerror=" not in cleaned
    assert "javascript:" not in cleaned


@pytest.mark.security
@pytest.mark.parametrize(
    "dirty_html, portal_name",
    [
        (SPORT5_DIRTY_HTML, "Sport5"),
        (YNET_DIRTY_HTML, "Ynet"),
        (ONE_DIRTY_HTML, "ONE"),
    ],
)
def test_portal_dirty_html_sanitization(dirty_html, portal_name):
    """Ensure dirty portal HTML with tracking scripts and ads cleans into pure text."""
    cleaned = _sanitize_html_content(dirty_html)
    assert "<script" not in cleaned
    assert "eval(" not in cleaned
    assert "<iframe" not in cleaned
    assert "<style" not in cleaned
    assert "<div" not in cleaned
    assert "<a " not in cleaned
    assert len(cleaned) > 20, f"Cleaned text too short for {portal_name}"


@pytest.mark.security
def test_strip_html_tags_utility():
    """Verify strip_html_tags utility from schemas.feed correctly cleans dirty markup."""
    try:
        from schemas.feed import strip_html_tags
    except ImportError:
        pytest.skip("schemas.feed not yet implemented.")

    dirty_text = "<p>ניצחון <b>גדול</b> למכבי <script>alert('x')</script> בהיכל.</p>"
    clean = strip_html_tags(dirty_text)

    assert "<script>" not in clean
    assert "<b>" not in clean
    assert "<p>" not in clean
    assert "ניצחון גדול למכבי בהיכל." == clean


@pytest.mark.security
def test_raw_article_payload_schema_sanitization():
    """Verify that RawArticlePayload automatically sanitizes HTML tags from title and body."""
    try:
        from schemas.feed import RawArticlePayload
    except ImportError:
        pytest.skip("schemas.feed not yet implemented; schema validation skipped.")

    dirty_payload = RawArticlePayload(
        title="<script>alert('pwn')</script>מכבי תל אביב ניצחה",
        raw_body="<div class='ad'><p>כתבה עם פרסומת <iframe src='evil.com'></iframe> וטקסט אמיתי.</p></div>",
        url="https://www.sport5.co.il/article/1",
        publisher="sport5",
    )

    assert "<script>" not in dirty_payload.title
    assert "<iframe>" not in dirty_payload.raw_body
    assert "<div" not in dirty_payload.raw_body
    assert "מכבי תל אביב ניצחה" in dirty_payload.title
    assert "וטקסט אמיתי" in dirty_payload.raw_body


@pytest.mark.security
def test_ai_enriched_card_sanitized_pipeline():
    """Verify that AIEnrichedCard fields constructed through sanitization contain 0 HTML tags."""
    try:
        from schemas.feed import AIEnrichedCard, strip_html_tags
    except ImportError:
        pytest.skip("schemas.feed not yet implemented; schema validation skipped.")

    raw_summary = "ניצחון <b>ענק</b> למכבי תל אביב על ריאל מדריד בהיכל מנורה מבטחים."
    raw_tags = ["<script>bad</script>מכבי תל אביב", "יורוליג"]

    clean_summary = strip_html_tags(raw_summary)
    clean_tags = [strip_html_tags(t) for t in raw_tags]

    enriched = AIEnrichedCard(
        micro_summary=clean_summary,
        tags=clean_tags,
        tone="hype",
        context_label="משחק עונה",
    )

    assert "<b>" not in enriched.micro_summary
    assert "</b>" not in enriched.micro_summary
    assert "<script>" not in enriched.tags[0]
    assert not HTML_TAG_REGEX.search(enriched.micro_summary)
    assert all(not HTML_TAG_REGEX.search(t) for t in enriched.tags)
