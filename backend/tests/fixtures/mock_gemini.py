"""Mock Gemini response payloads matching the AIEnrichedCard schema.

Provides structured response dictionaries and mock response objects mimicking the
google-genai SDK structured outputs interface for offline testing.
"""
import json
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 1. Canonical AIEnrichedCard Dictionaries by Sports Topic
# ---------------------------------------------------------------------------

MOCK_DERBY_ENRICHED_CARD: Dict[str, Any] = {
    "micro_summary": "מכבי חיפה משלימה הכנות אחרונות לדרבי מול הפועל חיפה בסמי עופר כשדין דוד ושרי צפויים לפתוח.",
    "tags": ["מכבי חיפה", "הפועל חיפה", "ליגת העל", "כדורגל ישראלי", "דרבי חיפאי"],
    "tone": "hype",
    "context_label": "משחק עונה",
}

MOCK_TRANSFER_ENRICHED_CARD: Dict[str, Any] = {
    "micro_summary": "הפועל באר שבע פתחה במשא ומתן מתקדם לצירוף קשר נבחרת רומניה לחיזוק מרכז השדה לקראת הקונפרנס ליג.",
    "tags": ["הפועל באר שבע", "חלון ההעברות", "קונפרנס ליג", "כדורגל ישראלי"],
    "tone": "objective",
    "context_label": "העברות",
}

MOCK_INJURY_ENRICHED_CARD: Dict[str, Any] = {
    "micro_summary": "מנור סולומון סובל מפציעה ברצועות הקרסול וייעדר כחודש מצמד משחקי נבחרת ישראל בליגת האומות.",
    "tags": ["מנור סולומון", "נבחרת ישראל", "ליגת האומות", "פציעות"],
    "tone": "critical",
    "context_label": "פציעות",
}

MOCK_EUROLEAGUE_ENRICHED_CARD: Dict[str, Any] = {
    "micro_summary": "מכבי תל אביב גברה 82:86 על ריאל מדריד בהיכל מנורה בהובלת בולדווין והבטיחה מקום בפלייאוף היורוליג.",
    "tags": ["מכבי תל אביב", "ריאל מדריד", "יורוליג", "כדורסל", "ווייד בולדווין"],
    "tone": "hype",
    "context_label": "יורוליג",
}

MOCK_STATISTICS_ENRICHED_CARD: Dict[str, Any] = {
    "micro_summary": "דני אבדיה רשם דאבל-דאבל של 18 נקודות ו-11 ריבאונדים בניצחון החוץ של וושינגטון על שיקגו.",
    "tags": ["דני אבדיה", "NBA", "וושינגטון וויזארדס", "כדורסל"],
    "tone": "objective",
    "context_label": "NBA",
}

MOCK_BEITAR_CRITICAL_ENRICHED_CARD: Dict[str, Any] = {
    "micro_summary": "זעזוע בבית\"ר ירושלים בעקבות עזיבת החלוץ הזר לפני משחק העונה, במועדון שוקלים צעדים משפטיים.",
    "tags": ["בית\"ר ירושלים", "ליגת העל", "ברק אברמוב", "כדורגל ישראלי"],
    "tone": "critical",
    "context_label": "משבר במועדון",
}

MOCK_JUDO_ENRICHED_CARD: Dict[str, Any] = {
    "micro_summary": "נבחרת ישראל בג'ודו זכתה במדליית זהב היסטורית באליפות אירופה הקבוצתית בטביליסי לאחר ניצחונות של פלצ'יק והרשקו.",
    "tags": ["ג'ודו", "נבחרת ישראל", "פיטר פלצ'יק", "רז הרשקו", "ספורט אולימפי"],
    "tone": "hype",
    "context_label": "ספורט אולימפי",
}

# ---------------------------------------------------------------------------
# 2. Topic Registry Mapping
# ---------------------------------------------------------------------------

MOCK_GEMINI_RESPONSES: Dict[str, Dict[str, Any]] = {
    "derby": MOCK_DERBY_ENRICHED_CARD,
    "transfer": MOCK_TRANSFER_ENRICHED_CARD,
    "injury": MOCK_INJURY_ENRICHED_CARD,
    "euroleague": MOCK_EUROLEAGUE_ENRICHED_CARD,
    "statistics": MOCK_STATISTICS_ENRICHED_CARD,
    "beitar": MOCK_BEITAR_CRITICAL_ENRICHED_CARD,
    "judo": MOCK_JUDO_ENRICHED_CARD,
}


# ---------------------------------------------------------------------------
# 3. Mock Google GenAI SDK Response Wrapper
# ---------------------------------------------------------------------------

class MockGenerateContentResponse:
    """Emulates a google-genai GenerateContentResponse with structured output parsing."""

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.text = json.dumps(data, ensure_ascii=False)

    @property
    def parsed(self) -> Any:
        """Returns Pydantic AIEnrichedCard instance if schema exists, else dict."""
        try:
            from schemas.feed import AIEnrichedCard
            return AIEnrichedCard(**self._data)
        except (ImportError, Exception):
            return self._data.copy()

    def __repr__(self) -> str:
        return f"<MockGenerateContentResponse parsed={self.parsed}>"


def create_mock_gemini_response(
    topic: str = "euroleague",
    custom_overrides: Optional[Dict[str, Any]] = None,
) -> MockGenerateContentResponse:
    """Factory creating a MockGenerateContentResponse for a given sports scenario."""
    base_data = MOCK_GEMINI_RESPONSES.get(topic, MOCK_EUROLEAGUE_ENRICHED_CARD).copy()
    if custom_overrides:
        base_data.update(custom_overrides)
    return MockGenerateContentResponse(base_data)
