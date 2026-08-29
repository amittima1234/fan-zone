"""Base interface and structured Pydantic schemas for AI article analysis."""

from abc import ABC, abstractmethod
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ArticleAnalysisResult(BaseModel):
    """Structured result of AI analysis for a Hebrew sports article.
    
    Contains non-clickbait headline, summarizing subheadline, and classified
    sports entities and topic tags.
    """
    headline: str = Field(
        ...,
        description=(
            "כותרת ראשית עובדתית, אובייקטיבית, תמציתית ונטולת קליקבייט בעברית. "
            "חייבת לגלות את העובדה המרכזית (מי עשה מה, מה התוצאה, מה הוחלט) "
            "ללא סופרלטיבים, ללא שאלות וללא טיזרים מעורפלים. 6 עד 16 מילים."
        ),
    )
    subheadline: str = Field(
        ...,
        description=(
            "כותרת משנה בעברית של 1-2 משפטים עובדתיים המסכמת את עיקרי הידיעה בצורה עניינית "
            "עם הפרטים החשובים (תוצאה, שמות המבקיעים/מצטיינים, פרטי החוזה או הרקע המרכזי)."
        ),
    )
    sport: str = Field(
        ...,
        description=(
            "ענף הספורט הראשי בעברית תקנית מתוך הרשימה: "
            "כדורגל, כדורסל, טניס, ג'ודו, שחייה, אתלטיקה, ספורט מוטורי, כדוריד, כדורעף, ענפים נוספים."
        ),
    )
    teams: List[str] = Field(
        default_factory=list,
        description=(
            "רשימת שמות מועדונים וקבוצות המוזכרים בכתבה בשמם המלא והתקני בעברית "
            "(לדוגמה: 'מכבי תל אביב', 'מכבי חיפה', 'הפועל באר שבע', 'ריאל מדריד', 'לוס אנג'לס לייקרס')."
        ),
    )
    players: List[str] = Field(
        default_factory=list,
        description=(
            "רשימת אישים מרכזיים המוזכרים בכתבה (שחקנים, מאמנים, שופטים, מנהלים, בעלי קבוצות) "
            "בשמם המלא בעברית (לדוגמה: 'ערן זהבי', 'עומר אצילי', 'ברק בכר', 'עודד קטש', 'דני אבדיה')."
        ),
    )
    competition: Optional[str] = Field(
        default=None,
        description=(
            "המפעל, הליגה או הטורניר הרלוונטי (לדוגמה: "
            "'ליגת העל בכדורגל', 'ליגת העל בכדורסל', 'ליגת האלופות', 'יורוליג', 'NBA', 'גביע המדינה', 'ווימבלדון', 'מונדיאל')."
        ),
    )
    tags: List[str] = Field(
        default_factory=list,
        description=(
            "תגיות נושאיות נוספות לקטלוג הכתבה "
            "(לדוגמה: 'העברות', 'פציעות', 'נבחרת ישראל', 'דרבי', 'ראיון', 'סיכום משחק', 'דין משמעתי')."
        ),
    )

    @field_validator("headline", "subheadline", mode="before")
    @classmethod
    def strip_and_clean_text(cls, v: Optional[str]) -> str:
        if v is None:
            return ""
        return str(v).strip()

    @field_validator("sport", mode="before")
    @classmethod
    def clean_sport(cls, v: Optional[str]) -> str:
        if not v or not str(v).strip():
            return "ענפים נוספים"
        return str(v).strip()

    @field_validator("teams", "players", "tags", mode="before")
    @classmethod
    def clean_string_list(cls, v: Optional[List[str]]) -> List[str]:
        if not v:
            return []
        if isinstance(v, str):
            v = [v]
        cleaned: List[str] = []
        seen = set()
        for item in v:
            if item is None:
                continue
            s = str(item).strip()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        return cleaned

    @field_validator("competition", mode="before")
    @classmethod
    def clean_competition(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class BaseAIProcessor(ABC):
    """Abstract base class for sports article AI processors."""

    @abstractmethod
    async def analyze_article(
        self,
        title: str,
        subtitle: Optional[str] = None,
        body: str = "",
    ) -> ArticleAnalysisResult:
        """Process an article and return structured non-clickbait headlines and tags.
        
        Args:
            title: The original raw title of the article.
            subtitle: Optional raw subtitle or lead.
            body: The article text body or concatenated paragraphs.
            
        Returns:
            ArticleAnalysisResult with headline, subheadline, sport, teams, players, competition, and tags.
        """
        pass
