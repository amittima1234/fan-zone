"""Unit tests for Hebrew sports AI system prompts, few-shot examples, and prompt builder."""

import pytest
from fan_zone.ai.base import ArticleAnalysisResult
from fan_zone.ai.prompts import (
    FEW_SHOT_EXAMPLES,
    SYSTEM_INSTRUCTION,
    build_article_prompt,
    get_few_shot_examples,
    get_system_instruction,
)


class TestAIPrompts:
    """Test suite for system instructions and prompt engineering contracts."""

    def test_system_instruction_completeness(self):
        """Verify system instruction contains core editorial directives and rules."""
        sys_inst = get_system_instruction()
        assert isinstance(sys_inst, str)
        assert len(sys_inst) > 200

        # Core non-clickbait requirements
        assert "Non-Clickbait" in sys_inst or "קליקבייט" in sys_inst
        assert "headline" in sys_inst
        assert "subheadline" in sys_inst
        assert "sport" in sys_inst
        assert "teams" in sys_inst
        assert "players" in sys_inst
        assert "competition" in sys_inst
        assert "tags" in sys_inst

        # Anti-sensationalism rules
        assert "סופרלטיבים" in sys_inst
        assert "סימני שאלה" in sys_inst

    def test_few_shot_examples_schema_validation(self):
        """Ensure all few-shot examples conform strictly to ArticleAnalysisResult schema."""
        examples = get_few_shot_examples()
        assert len(examples) >= 3
        assert examples == FEW_SHOT_EXAMPLES

        sports_covered = set()
        for idx, ex in enumerate(examples):
            assert "input_title" in ex, f"Example {idx} missing input_title"
            assert "input_body" in ex, f"Example {idx} missing input_body"
            assert "output" in ex, f"Example {idx} missing output"

            # Must parse cleanly into ArticleAnalysisResult
            result = ArticleAnalysisResult.model_validate(ex["output"])
            assert len(result.headline) > 0
            assert len(result.subheadline) > 0
            assert result.sport in [
                "כדורגל",
                "כדורסל",
                "טניס",
                "ג'ודו",
                "שחייה",
                "אתלטיקה",
                "ספורט מוטורי",
                "כדוריד",
                "כדורעף",
                "ענפים נוספים",
            ]
            assert isinstance(result.teams, list)
            assert isinstance(result.players, list)
            assert isinstance(result.tags, list)
            sports_covered.add(result.sport)

        # Must cover at least football, basketball, and an individual sport (judo/tennis)
        assert "כדורגל" in sports_covered
        assert "כדורסל" in sports_covered
        assert len(sports_covered) >= 3

    def test_build_article_prompt_basic(self):
        """Verify prompt formatting with title and body."""
        title = "מכבי חיפה ניצחה 0:2 את הפועל באר שבע"
        body = "משחק עונה מרתק בסמי עופר הסתיים בניצחון ירוק."

        prompt = build_article_prompt(title=title, body=body)
        assert title in prompt
        assert body in prompt
        assert "כותרת מקורית:" in prompt
        assert "גוף הכתבה:" in prompt

    def test_build_article_prompt_with_subtitle(self):
        """Verify prompt formatting when subtitle is provided."""
        title = "דרמה בהיכל מנורה"
        subtitle = "שלשה בשניית הסיום העניקה ניצחון לצהובים"
        body = "מכבי תל אביב גברה הערב על יריבתה במשחק צמוד."

        prompt = build_article_prompt(title=title, subtitle=subtitle, body=body)
        assert title in prompt
        assert subtitle in prompt
        assert body in prompt
        assert "כותרת משנה מקורית:" in prompt

    def test_build_article_prompt_empty_and_none_handling(self):
        """Verify prompt formatting with None or empty inputs."""
        prompt = build_article_prompt(title="", subtitle=None, body="")
        assert "כותרת מקורית:" in prompt
        assert isinstance(prompt, str)

    def test_build_article_prompt_truncation(self):
        """Verify prompt builder truncates excessively large text bodies."""
        long_body = "כתבת ספורט ארוכה מאוד. " * 1000
        assert len(long_body) > 10000

        max_limit = 2000
        prompt = build_article_prompt(title="כותרת", body=long_body, max_body_chars=max_limit)
        assert len(prompt) < max_limit + 500

    def test_build_article_prompt_special_characters_and_multiline(self):
        """Verify prompt builder handles quotes, emojis, newlines, and punctuation correctly."""
        title = 'בלעדי: "הוא לא ישחק כאן יותר!" ⚽'
        subtitle = "סערה בחדר ההלבשה של הקבוצה:\n- השחקן הושעה\n- המאמן סירב להגיב"
        body = "פסקה ראשונה.\n\nפסקה שנייה עם ציטוט: \"זה לא מקובל עליי\"."

        prompt = build_article_prompt(title=title, subtitle=subtitle, body=body)
        assert "בלעדי:" in prompt
        assert "הוא לא ישחק כאן יותר!" in prompt
        assert "⚽" in prompt
        assert "סערה בחדר ההלבשה" in prompt
        assert "פסקה ראשונה." in prompt
        assert "פסקה שנייה" in prompt
