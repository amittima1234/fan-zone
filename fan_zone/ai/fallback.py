"""Rule-based heuristic AI processor for offline fallback and zero-crash guarantee."""

import re
from typing import List, Optional, Tuple

from fan_zone.ai.base import ArticleAnalysisResult, BaseAIProcessor

# Common sensational clickbait prefixes in Israeli sports media
CLICKBAIT_PREFIXES: List[re.Pattern] = [
    re.compile(r"^בלעדי(?:\s+ומטורף)?[:!\s]+", re.IGNORECASE),
    re.compile(r"^פרסום ראשון[:!\s]+", re.IGNORECASE),
    re.compile(r"^צפו בטירוף[:!\s]+", re.IGNORECASE),
    re.compile(r"^צפו[:!\s]+", re.IGNORECASE),
    re.compile(r"^רעידת אדמה[:!\s]+", re.IGNORECASE),
    re.compile(r"^סערת ענק[:!\s]+", re.IGNORECASE),
    re.compile(r"^סערה[:!\s]+", re.IGNORECASE),
    re.compile(r"^(?:אתם\s+)?לא תאמינו(?:\s+מה\s+קרה|\s+מי)?[:!\s]+", re.IGNORECASE),
    re.compile(r"^הלם(?:\s+מוחלט)?(?:\s+בבלומפילד|\s+בסמי עופר|\s+בעולם הכדורסל|\s+בעולם הכדורגל|\s+בספורט)?[:!\s]+", re.IGNORECASE),
    re.compile(r"^הלם[:!\s]+", re.IGNORECASE),
    re.compile(r"^דרמה[:!\s]+", re.IGNORECASE),
    re.compile(r"^דרמת ענק[:!\s]+", re.IGNORECASE),
    re.compile(r"^חשיפה[:!\s]+", re.IGNORECASE),
    re.compile(r"^טירוף[:!\s]+", re.IGNORECASE),
    re.compile(r"^בושה[:!\s]+", re.IGNORECASE),
    re.compile(r"^השפלה[:!\s]+", re.IGNORECASE),
    re.compile(r"^רשמי[:!\s]+", re.IGNORECASE),
    re.compile(r"^הודעה דרמטית[:!\s]+", re.IGNORECASE),
    re.compile(r"^התפתחות מפתיעה[:!\s]+", re.IGNORECASE),
]

# Known Israeli and international clubs with canonical names and colloquial aliases
KNOWN_TEAMS: List[Tuple[str, List[str]]] = [
    ("מכבי תל אביב", ["מכבי תל אביב", "מכבי ת\"א", "מכבי תל-אביב", "הצהובים מתל אביב", "הצהובים"]),
    ("מכבי חיפה", ["מכבי חיפה", "הירוקים מהכרמל", "הירוקים מחיפה", "הירוקים"]),
    ("הפועל באר שבע", ["הפועל באר שבע", "הפועל ב\"ש", "הפועל באר-שבע", "האדומים מהנגב", "באר שבע"]),
    ("הפועל תל אביב", ["הפועל תל אביב", "הפועל ת\"א", "הפועל תל-אביב", "האדומים מתל אביב"]),
    ("בית\"ר ירושלים", ["בית\"ר ירושלים", "בית\"ר י-ם", "בית\"ר ירושלים", "הצהובים-שחורים", "בית\"ר"]),
    ("מכבי נתניה", ["מכבי נתניה", "היהלומים מנתניה", "היהלומים"]),
    ("הפועל ירושלים", ["הפועל ירושלים", "הפועל י-ם"]),
    ("הפועל חיפה", ["הפועל חיפה", "הכרישים מחיפה", "הכרישים"]),
    ("בני סכנין", ["בני סכנין", "איחוד בני סכנין", "סכנין"]),
    ("מכבי פתח תקווה", ["מכבי פתח תקווה", "מכבי פ\"ת", "המלאבסים"]),
    ("הפועל פתח תקווה", ["הפועל פתח תקווה", "הפועל פ\"ת"]),
    ("מ.ס. אשדוד", ["מ.ס. אשדוד", "מ.ס אשדוד", "מועדון ספורט אשדוד"]),
    ("עירוני קריית שמונה", ["עירוני קריית שמונה", "קריית שמונה", "עירוני ק\"ש", "ק\"ש"]),
    ("הפועל חדרה", ["הפועל חדרה", "חדרה"]),
    ("מכבי בני ריינה", ["מכבי בני ריינה", "בני ריינה", "ריינה"]),
    ("הפועל חולון", ["הפועל חולון", "חולוניה", "הסגולים מחולון"]),
    ("בני הרצליה", ["בני הרצליה"]),
    ("עירוני נס ציונה", ["עירוני נס ציונה", "נס ציונה"]),
    ("הפועל גליל עליון", ["הפועל גליל עליון", "גליל עליון"]),
    ("הפועל עפולה", ["הפועל עפולה"]),
    ("עירוני טבריה", ["עירוני טבריה", "טבריה"]),
    ("נבחרת ישראל", ["נבחרת ישראל", "הנבחרת הלאומית", "נבחרת הכדורגל", "נבחרת הכדורסל"]),
    ("ריאל מדריד", ["ריאל מדריד", "הבלאנקוס", "ריאל"]),
    ("ברצלונה", ["ברצלונה", "בארסה", "הקטלאנים"]),
    ("מנצ'סטר סיטי", ["מנצ'סטר סיטי", "סיטי", "הסיטיזנס"]),
    ("מנצ'סטר יונייטד", ["מנצ'סטר יונייטד", "יונייטד", "השדים האדומים"]),
    ("ליברפול", ["ליברפול", "המייטי רדס"]),
    ("ארסנל", ["ארסנל", "התותחנים"]),
    ("צ'לסי", ["צ'לסי", "הבלוז"]),
    ("באיירן מינכן", ["באיירן מינכן", "באיירן"]),
    ("פריז סן ז'רמן", ["פריז סן ז'רמן", "פ.ס.ז'", "פסז'"]),
    ("יובנטוס", ["יובנטוס", "הגברת הזקנה"]),
    ("אינטר", ["אינטר מילאנו", "אינטר"]),
    ("מילאן", ["מילאן", "הרוסונרי"]),
    ("לוס אנג'לס לייקרס", ["לוס אנג'לס לייקרס", "לייקרס"]),
    ("גולדן סטייט ווריורס", ["גולדן סטייט ווריורס", "גולדן סטייט", "ווריורס"]),
    ("בוסטון סלטיקס", ["בוסטון סלטיקס", "סלטיקס"]),
    ("פרטיזן בלגרד", ["פרטיזן בלגרד", "פרטיזן"]),
    ("הכוכב האדום בלגרד", ["הכוכב האדום בלגרד", "הכוכב האדום"]),
    ("פנאתינייקוס", ["פנאתינייקוס", "פנאתינאיקוס", "פאו"]),
    ("אולימפיאקוס", ["אולימפיאקוס"]),
    ("פנרבחצ'ה", ["פנרבחצ'ה", "פנר"]),
    ("אנאדולו אפס", ["אנאדולו אפס", "אפס פילזן"]),
    ("מונאקו", ["מונאקו", "אס מונאקו"]),
]

# Known competitions and leagues
KNOWN_COMPETITIONS: List[Tuple[str, List[str]]] = [
    ("ליגת העל בכדורגל", ["ליגת העל בכדורגל", "ליגת העל", "ליגת winner", "ליגת ווינר"]),
    ("ליגת העל בכדורסל", ["ליגת העל בכדורסל", "ליגת ווינר סל", "ליגת ווינר בכדורסל"]),
    ("ליגת האלופות", ["ליגת האלופות", "צ'מפיונס ליג", "צ'מפיונס", "הצ'מפיונס"]),
    ("הליגה האירופית", ["הליגה האירופית", "האירופית"]),
    ("הקונפרנס ליג", ["הקונפרנס ליג", "קונפרנס ליג"]),
    ("יורוליג", ["יורוליג", "Euroleague"]),
    ("יורוקאפ", ["יורוקאפ", "Eurocup"]),
    ("NBA", ["NBA", "אן בי איי", "אן.בי.אי"]),
    ("גביע המדינה", ["גביע המדינה", "גביע המדינה בכדורגל", "גביע המדינה בכדורסל"]),
    ("גביע הטוטו", ["גביע הטוטו"]),
    ("פרמייר ליג", ["פרמייר ליג", "הליגה האנגלית", "הפרמיירליג"]),
    ("לה ליגה", ["לה ליגה", "הליגה הספרדית", "לה-ליגה"]),
    ("סרייה א'", ["סרייה א'", "הליגה האיטלקית", "סריה א'"]),
    ("בונדסליגה", ["בונדסליגה", "הליגה הגרמנית"]),
    ("ווימבלדון", ["ווימבלדון", "טורניר ווימבלדון"]),
    ("רולאן גארוס", ["רולאן גארוס", "אליפות צרפת הפתוחה"]),
    ("אליפות אוסטרליה הפתוחה", ["אליפות אוסטרליה הפתוחה", "אוסטרליאן אופן"]),
    ("אליפות ארה\"ב הפתוחה", ["אליפות ארה\"ב הפתוחה", "US Open"]),
    ("גראנד סלאם", ["גראנד סלאם", "גראנד פרי"]),
    ("מונדיאל", ["מונדיאל", "גביע העולם"]),
    ("יורו", ["יורו 2024", "אליפות אירופה"]),
    ("ליגת האומות", ["ליגת האומות"]),
]

# Prominent sports personalities
KNOWN_PERSONALITIES: List[str] = [
    "ערן זהבי",
    "עומר אצילי",
    "ברק בכר",
    "עודד קטש",
    "דני אבדיה",
    "מנור סולומון",
    "אוסקר גלוך",
    "רומן סורקין",
    "ים מדר",
    "תמיר בלאט",
    "רועי משפתי",
    "דולב חזיזה",
    "דין דוד",
    "דיא סבע",
    "דור פרץ",
    "דן ביטון",
    "גבי קניקובסקי",
    "שריף כיוף",
    "עמרי גלזר",
    "אלי דסה",
    "רוי רביבו",
    "רן קוז'וך",
    "רן בן שמעון",
    "אלון חזן",
    "גיא לוזון",
    "אופיר דוידזאדה",
    "שגיב יחזקאל",
    "מיגל ויטור",
    "איתי שכטר",
    "פיטר פלצ'יק",
    "ענבר לניר",
    "רז הרשקו",
    "תמנע נלסון לוי",
    "ארטיום דולגופיאט",
    "לינוי אשרם",
    "אנסטסיה גורבנקו",
    "ליאו מסי",
    "כריסטיאנו רונאלדו",
    "קיליאן אמבפה",
    "ארלינג הולאנד",
    "ויניסיוס ג'וניור",
    "ג'וד בלינגהאם",
    "לברון ג'יימס",
    "סטף קרי",
    "לוקה דונצ'יץ'",
    "ניקולה יוקיץ'",
    "נובאק ג'וקוביץ'",
    "קרלוס אלקרס",
    "יאניק סינר",
    "פפ גווארדיולה",
    "קרלו אנצ'לוטי",
    "ז'וזה מוריניו",
    "יורגן קלופ",
    "מיקל ארטטה",
    "קווין פאנטר",
    "ווייד בולדווין",
    "לורנזו בראון",
    "בונזי קולסון",
    "ג'וש ניבו",
]


def clean_clickbait_title(raw_title: str) -> str:
    """Strip clickbait prefixes, dramatic punctuation, and formatting noise from a title."""
    if not raw_title:
        return ""

    cleaned = raw_title.strip()
    cleaned = re.sub(r"^[\s\-_–—#*]+|[\s\-_–—#*]+$", "", cleaned).strip()

    # Strip quotation wrappers if the entire title is in quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    # Strip leading clickbait prefix
    for pattern in CLICKBAIT_PREFIXES:
        match = pattern.search(cleaned)
        if match:
            cleaned = cleaned[match.end():].strip()
            break

    # Strip optional secondary phrase prefix like "אתם לא תאמינו מה קרה" or "אתם לא תאמינו מי"
    phrase_match = re.search(r"^(?:אתם\s+)?לא תאמינו(?:\s+מה\s+קרה|\s+מי)?[:!\s]*", cleaned)
    if phrase_match:
        cleaned = cleaned[phrase_match.end():].strip()

    # Strip quotation wrappers again if prefix stripping revealed quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    cleaned = re.sub(r"^[\s\-_–—#*]+|[\s\-_–—#*]+$", "", cleaned).strip()

    # Remove trailing sensational question marks or exclamation marks
    cleaned = re.sub(r"[?!]+$", "", cleaned).strip()

    # Replace double spaces
    cleaned = re.sub(r"\s+", " ", cleaned)

    return cleaned


def detect_sport(text: str) -> str:
    """Classify the primary sport based on keyword density and sports terminology."""
    football_keywords = [
        "שער", "גול", "פנדל", "חלוץ", "בלם", "קשר", "שוער", "כרטיס אדום", "כרטיס צהוב",
        "נבדל", "קרן", "ליגת העל בכדורגל", "פרמייר ליג", "לה ליגה", "סרייה א", "בונדסליגה",
        "ליגת האלופות", "מונדיאל", "דרבי", "פנדלים", "בעיטה",
        "הבקעה", "משחק העונה", "הרכב", "סגל", "דשא", "סמי עופר", "טדי", "בלומפילד", "טרנר",
    ]
    basketball_keywords = [
        "סל", "שלשה", "שלשות", "ריבאונד", "אסיסט", "אסיסטים", "הטבעה", "דאנק", "חסימה",
        "יורוליג", "Euroleague", "NBA", "אן בי איי", "מנהלת הליגה", "רכז", "פורוורד", "סנטר", "פסק זמן",
        "קליעה", "כדורסל", "היכל מנורה", "היכל שלמה", "היכל קבוצת שלמה", "היכל טוטו", "ווינר סל",
        "טבעת", "לוח", "קו עונשין", "עבירה בלתי ספורטיבית", "דרייב אין", "בית מכבי", "נקודות",
    ]
    tennis_keywords = [
        "טניס", "מערכה", "מערכות", "שבירה", "אייס", "ווימבלדון", "רולאן גארוס",
        "אליפות אוסטרליה", "אליפות ארה\"ב", "ATP", "WTA", "דג'וקוביץ'", "אלקרס",
        "סינר", "חבטה", "טניסאי", "טניסאית", "משחקון",
    ]
    judo_keywords = [
        "ג'ודו", "איפון", "וואזארי", "מזרן", "חליפת ג'ודו", "משקל עד", "גראנד סלאם",
        "ג'ודוקא", "קרב", "מדליית זהב", "מדליית ארד", "מדליית כסף",
    ]
    swimming_keywords = [
        "שחייה", "בריכה", "מקצה", "100 מטר חופשי", "פרפר", "גב", "חזה", "שחיין", "שחיינית",
        "שיא עולם", "שיא ישראלי",
    ]
    athletics_keywords = [
        "אתלטיקה", "ריצה", "מרתון", "קפיצה לרוחק", "קפיצה לגובה", "קפיצה במוט",
        "הטלת כידון", "100 מטר", "אצן", "אצנית",
    ]
    motorsport_keywords = [
        "פורמולה 1", "F1", "גרנד פרי", "מירוץ מכוניות", "מסלול", "נהג מרוצים",
        "פרארי", "רד בול", "מרצדס", "מקלארן", "ורסטאפן", "המילטון",
    ]
    handball_keywords = ["כדוריד", "ליגת העל בכדוריד", "שוער כדוריד", "זריקת 7 מטר"]
    volleyball_keywords = ["כדורעף", "הנחתה", "ליברו", "חסימה בכדורעף", "ליגת העל בכדורעף"]

    f_count = sum(1 for kw in football_keywords if kw in text)
    # Check for football Euro specifically with negative lookahead avoiding EuroLeague / EuroCup collisions
    if re.search(r"(?<![א-תa-zA-Z0-9])יורו(?!ליג|קאפ|פקאפ|[א-תa-zA-Z0-9])", text):
        f_count += 1
    if any(term in text for term in ["יורו 2024", "יורו נבחרות", "אליפות אירופה בכדורגל"]):
        f_count += 1

    b_count = sum(1 for kw in basketball_keywords if kw in text)
    if any(term in text for term in ["יורוליג", "ביורוליג", "היורוליג", "Euroleague"]):
        b_count += 3

    t_count = sum(1 for kw in tennis_keywords if kw in text)
    j_count = sum(1 for kw in judo_keywords if kw in text)
    s_count = sum(1 for kw in swimming_keywords if kw in text)
    a_count = sum(1 for kw in athletics_keywords if kw in text)
    m_count = sum(1 for kw in motorsport_keywords if kw in text)
    h_count = sum(1 for kw in handball_keywords if kw in text)
    v_count = sum(1 for kw in volleyball_keywords if kw in text)

    # Check for basketball score format e.g. "80:75", "98-70"
    score_matches = re.findall(r"\b(\d{2,3})[:\-](\d{2,3})\b", text)
    for score1, score2 in score_matches:
        if int(score1) >= 40 or int(score2) >= 40:
            b_count += 3

    scores = [
        ("כדורגל", f_count),
        ("כדורסל", b_count),
        ("טניס", t_count),
        ("ג'ודו", j_count),
        ("שחייה", s_count),
        ("אתלטיקה", a_count),
        ("ספורט מוטורי", m_count),
        ("כדוריד", h_count),
        ("כדורעף", v_count),
    ]

    scores.sort(key=lambda x: x[1], reverse=True)
    if scores[0][1] > 0:
        return scores[0][0]
    return "כדורגל"


def extract_teams(text: str) -> List[str]:
    """Extract mentioned sports teams in canonical Hebrew forms."""
    found_teams: List[str] = []
    seen = set()

    for canonical, aliases in KNOWN_TEAMS:
        for alias in aliases:
            if alias in text:
                if canonical not in seen:
                    seen.add(canonical)
                    found_teams.append(canonical)
                break

    return found_teams


def extract_competition(text: str, sport: str) -> Optional[str]:
    """Extract the specific league, competition, or tournament mentioned."""
    for canonical, aliases in KNOWN_COMPETITIONS:
        for alias in aliases:
            if alias in text:
                # Disambiguate "ליגת העל" based on sport
                if canonical == "ליגת העל בכדורגל" and sport == "כדורסל":
                    return "ליגת העל בכדורסל"
                return canonical
    return None


def extract_players(text: str) -> List[str]:
    """Extract prominent sports personalities (players, coaches) mentioned in text."""
    found: List[str] = []
    seen = set()

    for person in KNOWN_PERSONALITIES:
        if person in text and person not in seen:
            seen.add(person)
            found.append(person)

    return found


def extract_topic_tags(text: str, sport: str, teams: List[str], competition: Optional[str]) -> List[str]:
    """Generate contextual topic tags for the article."""
    tags: List[str] = []
    seen = set()

    def add_tag(t: str) -> None:
        if t and t not in seen:
            seen.add(t)
            tags.append(t)

    # Core sport
    add_tag(sport)

    # Topic indicators
    if any(k in text for k in ["חתם", "החתמה", "העברה", "העברות", "מועמד", "סיכם", "רכש", "טרייד"]):
        add_tag("העברות")
        add_tag("רכש")
    if any(k in text for k in ["פציעה", "נפצע", "ייעדר", "בדיקת MRI", "קרע", "ניתוח"]):
        add_tag("פציעות")
    if any(k in text for k in ["ניצחון", "הפסד", "ניצחה", "הביסה", "נפרדו בתיקו", "תוצאת סיום", "גברה על"]):
        add_tag("סיכום משחק")
    if any(k in text for k in ["נבחרת ישראל", "אלון חזן", "רן בן שמעון", "מוקדמות"]):
        add_tag("נבחרת ישראל")
    if any(k in text for k in ["בית הדין", "דין משמעתי", "הורחק", "הרחקה", "קנס", "תובע ההתאחדות"]):
        add_tag("דין משמעתי")
    if any(k in text for k in ["ראיון", "מדבר על הכל", "בראיון מיוחד", "מסע במסיבת עיתונאים"]):
        add_tag("ראיון")
    if any(k in text for k in ["דרבי"]):
        add_tag("דרבי")

    # Add competition if present
    if competition:
        add_tag(competition)

    # Add up to 2 primary teams
    for team in teams[:2]:
        add_tag(team)

    return tags


def extract_subheadline(body: str, subtitle: Optional[str], fallback_title: str) -> str:
    """Extract a concise, factual 1-2 sentence subheadline."""
    if subtitle and len(subtitle.strip()) > 15:
        clean_sub = clean_clickbait_title(subtitle)
        if not clean_sub.endswith("."):
            clean_sub += "."
        return clean_sub[:250]

    # Split body into clean sentences
    sentences = [
        s.strip()
        for s in re.split(r"[.\n!?]", body or "")
        if len(s.strip()) > 20 and not s.strip().startswith("צילום:") and not s.strip().startswith("מאת:")
    ]

    if sentences:
        sub = ". ".join(sentences[:2])
        if not sub.endswith("."):
            sub += "."
        return sub[:250]

    return f"דיווח ספורט: {fallback_title}."


def fallback_article_analysis(
    title: str,
    subtitle: Optional[str] = None,
    body: str = "",
) -> ArticleAnalysisResult:
    """Analyze a Hebrew sports article using robust heuristic rule-based extraction.
    
    Provides deterministic, fast, and 100% offline analysis ensuring zero pipeline crashes.
    """
    clean_title = clean_clickbait_title(title)
    if not clean_title:
        clean_title = "עדכון ספורט"

    combined_text = f"{title or ''} {subtitle or ''} {body or ''}"

    sport = detect_sport(combined_text)
    teams = extract_teams(combined_text)
    competition = extract_competition(combined_text, sport)
    players = extract_players(combined_text)
    tags = extract_topic_tags(combined_text, sport, teams, competition)
    subheadline = extract_subheadline(body, subtitle, clean_title)

    return ArticleAnalysisResult(
        headline=clean_title,
        subheadline=subheadline,
        sport=sport,
        teams=teams,
        players=players,
        competition=competition,
        tags=tags,
    )


class RuleBasedAIProcessor(BaseAIProcessor):
    """Concrete BaseAIProcessor implementation using the heuristic fallback engine."""

    async def analyze_article(
        self,
        title: str,
        subtitle: Optional[str] = None,
        body: str = "",
    ) -> ArticleAnalysisResult:
        """Process article with rule-based heuristics."""
        return fallback_article_analysis(title=title, subtitle=subtitle, body=body)
