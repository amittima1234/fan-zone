"""Unit tests for MockAIProcessor and heuristic fallback across diverse Hebrew sports articles."""

import pytest
import time
from fan_zone.ai.base import ArticleAnalysisResult
from fan_zone.ai.mock import MockAIProcessor
from fan_zone.ai.fallback import (
    clean_clickbait_title,
    detect_sport,
    extract_competition,
    extract_players,
    extract_teams,
    fallback_article_analysis,
)


class TestMockAIProcessor:
    """Test suite for offline hermetic MockAIProcessor."""

    @pytest.mark.asyncio
    async def test_mock_football_article_analysis(self):
        """Verify mock correctly categorizes a football match report."""
        processor = MockAIProcessor()
        title = "בלעדי: מכבי חיפה גברה 1:2 על מכבי תל אביב במשחק העונה"
        subtitle = "דין דוד ודיא סבע הבקיעו לירוקים בסמי עופר. דור פרץ צימק לצהובים."
        body = (
            "מכבי חיפה השיגה ניצחון יוקרתי על מכבי תל אביב בליגת העל בכדורגל. "
            "דין דוד העלה את הירוקים ליתרון בדקה ה-23 לאחר בישול נהדר של דיא סבע. "
            "דור פרץ השווה זמנית עבור הצהובים, אך שער נוסף של סבע חתם את התוצאה."
        )

        result = await processor.analyze_article(title=title, subtitle=subtitle, body=body)

        assert isinstance(result, ArticleAnalysisResult)
        assert "בלעדי:" not in result.headline
        assert "מכבי חיפה" in result.headline or "מכבי חיפה" in result.teams
        assert result.sport == "כדורגל"
        assert "מכבי חיפה" in result.teams
        assert "מכבי תל אביב" in result.teams
        assert result.competition == "ליגת העל בכדורגל"
        assert any(player in result.players for player in ["דין דוד", "דיא סבע", "דור פרץ"])
        assert "סיכום משחק" in result.tags
        assert processor.call_count == 1

    @pytest.mark.asyncio
    async def test_mock_basketball_euroleague_analysis(self):
        """Verify mock categorizes a basketball Euroleague game."""
        processor = MockAIProcessor()
        title = "רעידת אדמה: מכבי תל אביב ניצחה 82:85 את ריאל מדריד ביורוליג"
        body = (
            "ניצחון ענק לצהובים בהיכל מנורה. ווייד בולדווין להט עם 28 נקודות ו-6 אסיסטים, "
            "ועודד קטש חגג על הקווים מול אלופת אירופה."
        )

        result = await processor.analyze_article(title=title, body=body)

        assert "רעידת אדמה:" not in result.headline
        assert result.sport == "כדורסל"
        assert "מכבי תל אביב" in result.teams
        assert "ריאל מדריד" in result.teams
        assert result.competition == "יורוליג"
        assert "ווייד בולדווין" in result.players or "עודד קטש" in result.players
        assert "סיכום משחק" in result.tags

    @pytest.mark.asyncio
    async def test_mock_transfer_news_analysis(self):
        """Verify mock categorizes transfer news and tags 'העברות'."""
        processor = MockAIProcessor()
        title = "פרסום ראשון: דן ביטון סיכם את תנאיו בהפועל באר שבע לשלוש עונות"
        body = (
            "הקשר דן ביטון בדרך לאדומים מבירת הנגב. השחקן סיכם על חתימה במועדון "
            "ויצטרף לאימונים תחת רן קוז'וך לקראת משחקי גביע המדינה."
        )

        result = await processor.analyze_article(title=title, body=body)

        assert "פרסום ראשון:" not in result.headline
        assert result.sport == "כדורגל"
        assert "הפועל באר שבע" in result.teams
        assert "דן ביטון" in result.players or "רן קוז'וך" in result.players
        assert "העברות" in result.tags
        assert "רכש" in result.tags

    @pytest.mark.asyncio
    async def test_mock_tennis_analysis(self):
        """Verify mock categorizes tennis tournament."""
        processor = MockAIProcessor()
        title = "נובאק ג'וקוביץ' העפיל לגמר ווימבלדון אחרי ניצחון בארבע מערכות"
        body = "הטניסאי הסרבי גבר על יריבו בקרב של 3 שעות והבטיח מקום בגמר הטורניר היוקרתי."

        result = await processor.analyze_article(title=title, body=body)

        assert result.sport == "טניס"
        assert result.competition == "ווימבלדון"
        assert "נובאק ג'וקוביץ'" in result.players

    @pytest.mark.asyncio
    async def test_mock_judo_analysis(self):
        """Verify mock categorizes judo championship."""
        processor = MockAIProcessor()
        title = "מדליית זהב! פיטר פלצ'יק ניצח באיפון בגמר גראנד סלאם"
        body = "הג'ודוקא הישראלי פיטר פלצ'יק סיים יום קרבות מושלם על המזרן בטוקיו."

        result = await processor.analyze_article(title=title, body=body)

        assert result.sport == "ג'ודו"
        assert "פיטר פלצ'יק" in result.players

    @pytest.mark.asyncio
    async def test_mock_custom_response_override(self):
        """Verify custom_response injection works deterministically."""
        custom = ArticleAnalysisResult(
            headline="כותרת מותאמת אישית",
            subheadline="כותרת משנה מותאמת אישית לבדיקה.",
            sport="כדורגל",
            teams=["מכבי נתניה"],
            players=["שחקן בדיקה"],
            competition="גביע הטוטו",
            tags=["בדיקה"],
        )
        processor = MockAIProcessor(custom_response=custom)
        result = await processor.analyze_article(title="כותרת מקורית כלשהי")

        assert result == custom
        assert result.headline == "כותרת מותאמת אישית"
        assert processor.call_count == 1

    @pytest.mark.asyncio
    async def test_mock_simulation_failure_flags(self):
        """Verify error simulation flags trigger expected exceptions."""
        # Failure simulation
        proc_fail = MockAIProcessor(simulate_failure=True)
        with pytest.raises(RuntimeError, match="Service Unavailable"):
            await proc_fail.analyze_article(title="כותרת")

        # Rate limit simulation
        proc_rate = MockAIProcessor(simulate_rate_limit=True)
        with pytest.raises(RuntimeError, match="429 Resource Exhausted"):
            await proc_rate.analyze_article(title="כותרת")

        # Timeout simulation
        proc_timeout = MockAIProcessor(simulate_timeout=True)
        with pytest.raises(TimeoutError, match="timed out"):
            await proc_timeout.analyze_article(title="כותרת")

    @pytest.mark.asyncio
    async def test_mock_delay_simulation(self):
        """Verify simulated delay works properly."""
        processor = MockAIProcessor(delay_seconds=0.05)
        start_time = time.monotonic()
        await processor.analyze_article(title="כותרת בדיקה", body="גוף בדיקה")
        elapsed = time.monotonic() - start_time
        assert elapsed >= 0.04

    def test_mock_stats_reset(self):
        """Verify metrics tracking and resetting."""
        processor = MockAIProcessor()
        assert processor.call_count == 0
        processor.call_count = 5
        processor.last_title = "כותרת"
        processor.reset_stats()
        assert processor.call_count == 0
        assert processor.last_title is None


class TestHeuristicFallbackUnit:
    """Direct unit tests for heuristic NLP extraction functions."""

    def test_clean_clickbait_title_prefixes(self):
        """Test stripping diverse sensational prefixes."""
        prefixes = [
            ("בלעדי: רכש חדש לכרמל", "רכש חדש לכרמל"),
            ("פרסום ראשון: נסגרה העסקה", "נסגרה העסקה"),
            ("צפו: השער המדהים בדרבי", "השער המדהים בדרבי"),
            ("רעידת אדמה: סערת ענק בהנהלה", "סערת ענק בהנהלה"),
            ("לא תאמינו: מי חתם במועדון?", "מי חתם במועדון"),
            ("דרמה: החלטה ברגע האחרון!", "החלטה ברגע האחרון"),
            ("\"רשמי: השחקן חתם\"", "השחקן חתם"),
        ]
        for raw, expected in prefixes:
            assert clean_clickbait_title(raw) == expected

    def test_detect_sport_classification(self):
        """Test accurate sports category classification."""
        assert detect_sport("החלוץ בעט פנדל מדויק לשער והבקיע גול") == "כדורגל"
        assert detect_sport("קלע שלשה מדהימה וקטף 10 ריבאונדים בהיכל מנורה") == "כדורסל"
        assert detect_sport("ניצח במערכה השלישית עם אייס אדיר בווימבלדון") == "טניס"
        assert detect_sport("זכה באיפון מרשים בגמר הג'ודו במשקל עד 100 ק\"ג") == "ג'ודו"
        assert detect_sport("קבע שיא ישראלי חדש בבריכה ב-100 מטר חופשי") == "שחייה"
        assert detect_sport("נהג הפרארי זינק מהפול פוזישן בגרנד פרי פורמולה 1") == "ספורט מוטורי"

    def test_extract_teams_canonicalization(self):
        """Test canonicalization of club nicknames and abbreviations."""
        text = "הצהובים מתל אביב יפגשו את הירוקים מהכרמל והאדומים מהנגב"
        teams = extract_teams(text)
        assert "מכבי תל אביב" in teams
        assert "מכבי חיפה" in teams
        assert "הפועל באר שבע" in teams

    def test_extract_competition(self):
        """Test competition extraction and disambiguation."""
        assert extract_competition("משחק בעונת היורוליג", "כדורסל") == "יורוליג"
        assert extract_competition("קרב במסגרת ליגת העל", "כדורגל") == "ליגת העל בכדורגל"
        assert extract_competition("קרב במסגרת ליגת העל", "כדורסל") == "ליגת העל בכדורסל"
        assert extract_competition("מפגש ב-NBA בין הקבוצות", "כדורסל") == "NBA"

    def test_extract_teams_advanced_nicknames(self):
        """Test extraction and canonicalization of diverse Israeli and European nicknames."""
        text = "המלאבסים גברו על היהלומים, בעוד הבלאנקוס והקטלאנים נפרדו בתיקו. התותחנים חוגגים."
        teams = extract_teams(text)
        assert "מכבי פתח תקווה" in teams
        assert "מכבי נתניה" in teams
        assert "ריאל מדריד" in teams
        assert "ברצלונה" in teams
        assert "ארסנל" in teams

    def test_detect_sport_additional_disciplines(self):
        """Test athletics, handball, and volleyball sports classification."""
        assert detect_sport("רץ המרתון סיים את 42 הקילומטרים באתלטיקה קלה") == "אתלטיקה"
        assert detect_sport("שחקן הכדוריד כבש שער דרמטי בזריקת 7 מטר בליגת העל בכדוריד") == "כדוריד"
        assert detect_sport("הנחתה אדירה וחסימה מוצלחת על הרשת בליגת העל בכדורעף") == "כדורעף"

    def test_extract_players_comprehensive(self):
        """Test player, coach, and personality name extraction."""
        text = "ערן זהבי ועומר אצילי שוחחו עם המאמנים ברק בכר ועודד קטש. דני אבדיה בלט בוושינגטון."
        players = extract_players(text)
        assert "ערן זהבי" in players
        assert "עומר אצילי" in players
        assert "ברק בכר" in players
        assert "עודד קטש" in players
        assert "דני אבדיה" in players

    def test_fallback_article_analysis_boundary_inputs(self):
        """Test fallback analyzer behavior on empty or minimal inputs."""
        res_empty = fallback_article_analysis(title="", subtitle="", body="")
        assert res_empty.headline == "עדכון ספורט"
        assert res_empty.sport in ["כדורגל", "ענפים נוספים"]
        assert isinstance(res_empty.teams, list)
        assert isinstance(res_empty.players, list)
        assert isinstance(res_empty.tags, list)

    def test_fallback_article_analysis_injury_and_discipline_tags(self):
        """Test topic tag generation for injuries and disciplinary cases."""
        res_injury = fallback_article_analysis(
            title="מכה למכבי חיפה: השחקן סובל מקרע בשריר וייעדר חודש",
            body="בדיקת MRI אישרה את חומרת הפציעה של החלוץ.",
        )
        assert "פציעות" in res_injury.tags
        assert "מכבי חיפה" in res_injury.teams

        res_disc = fallback_article_analysis(
            title="בית הדין המשמעתי: קנס כספי כבד להפועל תל אביב",
            body="תובע ההתאחדות דרש הרחקה של המאמן בעקבות האירועים בדרבי.",
        )
        assert "דין משמעתי" in res_disc.tags
        assert "דרבי" in res_disc.tags
        assert "הפועל תל אביב" in res_disc.teams
