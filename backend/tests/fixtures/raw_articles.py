"""Pre-populated RawArticlePayload fixtures representing Israeli sports news.

Provides both raw dictionary representations and dynamic Pydantic object
instantiations with graceful fallback.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# 1. Canonical Raw Article Dictionaries
# ---------------------------------------------------------------------------

SPORT5_RAW_ARTICLE: Dict[str, Any] = {
    "title": "ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג",
    "raw_body": (
        "תצוגת ענק של הצהובים בהיכל מנורה מבטחים הבטיחה ניצחון יוקרתי ומקום בפלייאוף היורוליג. "
        "חניכיו של עודד קטש הציגו כדורסל מלהיב ומחויב החל מהרבע הראשון. "
        "ווייד בולדווין להט עם 24 נקודות ו-7 אסיסטים, בעוד לורנזו בראון שלט בקצב והוסיף 18 נקודות משלו. "
        "ריאל מדריד ניסתה לחזור ברבע השלישי, אך הגנה קשוחה של ג'וש ניבו וחטיפות קריטיות של בונזי קולסון "
        "סגרו את הסיפור בדקות הסיום לקול תשואות 11,000 צופים נלהבים ביציעים."
    ),
    "url": "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450101",
    "publisher": "sport5",
    "published_at": datetime(2026, 8, 29, 10, 45, 0, tzinfo=timezone.utc),
    "category": "כדורסל",
    "author": "עמרי פולק",
    "image_url": "https://images.sport5.co.il/maccabi_real_2026.jpg",
}

YNET_RAW_ARTICLE: Dict[str, Any] = {
    "title": "סערה בבית\"ר ירושלים: החלוץ הזר הודיע על עזיבה מיידית",
    "raw_body": (
        "זעזוע בבירה יומיים בלבד לפני משחק העונה מול מכבי תל אביב באצטדיון טדי. "
        "החלוץ לא הגיע לאימון הבוקר ושלח מכתב באמצעות עורך דינו בדרישה להתיר את חוזהו באופן מיידי "
        "לטובת הצעה כספית מפתה מקבוצה בליגה הטורקית הבכירה. "
        "בבית\"ר ירושלים זועמים על ההתנהלות והבהירו כי ינקטו בצעדים משפטיים מחמירים במידה ולא ישוב לאימונים."
    ),
    "url": "https://www.ynet.co.il/sport/israelifootball/article/r1j8xk9211",
    "publisher": "ynet",
    "published_at": datetime(2026, 8, 29, 10, 10, 0, tzinfo=timezone.utc),
    "category": "ליגת העל",
    "author": "גידי ליפקין",
    "image_url": "https://images.ynet.co.il/beitar_2026.jpg",
}

ONE_RAW_ARTICLE: Dict[str, Any] = {
    "title": "פרסום ראשון: הפועל באר שבע פתחה במו\"מ לצירוף קשר נבחרת רומניה",
    "raw_body": (
        "אלונה ברקת נותנת אור ירוק למהלך המרכזי של חלון ההעברות באצטדיון טוטו טרנר. "
        "הקשר הרומני בן ה-26, שהרשים מאוד במשחקי היורו האחרונים, מבוקש על ידי הצוות המקצועי "
        "במטרה לחזק את חוליית הקישור לקראת שלב הבתים בקונפרנס ליג. המו\"מ מתקדם ובמועדון מקווים לחתימה בקרוב."
    ),
    "url": "https://www.one.co.il/Article/25-26/1,1,3,0/478901.html",
    "publisher": "one",
    "published_at": datetime(2026, 8, 29, 10, 40, 0, tzinfo=timezone.utc),
    "category": "הפועל באר שבע",
    "author": "איציק כלפי",
    "image_url": "https://images.one.co.il/hapoel_bs_transfer.jpg",
}

MACCABI_TA_BASKETBALL_RAW_ARTICLE = SPORT5_RAW_ARTICLE

MACCABI_HAIFA_FOOTBALL_RAW_ARTICLE: Dict[str, Any] = {
    "title": "לקראת הדרבי החיפאי: ברק בכר מתלבט במערך ההתקפי בסמי עופר",
    "raw_body": (
        "מכבי חיפה השלימה את הכנותיה לדרבי הגדול מול הפועל חיפה. "
        "למעלה מ-30,000 צופים הבטיחו את מקומם באצטדיון סמי עופר. דין דוד צפוי לפתוח בחוד ההתקפה, "
        "בעוד צ'ארון שרי חוזר להרכב הראשון לאחר שקיבל מנוחה במשחק גביע הטוטו באמצע השבוע."
    ),
    "url": "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450102",
    "publisher": "sport5",
    "published_at": datetime(2026, 8, 29, 9, 30, 0, tzinfo=timezone.utc),
    "category": "ליגת העל",
    "author": "תומר לוי",
    "image_url": "https://images.sport5.co.il/haifa_derby.jpg",
}

HAPOEL_TA_DERBY_RAW_ARTICLE: Dict[str, Any] = {
    "title": "הפועל תל אביב בכדורסל השלימה את הסגל עם גארד אמריקאי נוצץ",
    "raw_body": (
        "האדומים מתל אביב הודיעו רשמית על החתמתו של גארד בעל עבר עשיר ביורוליג. "
        "ההחתמה מגיעה כשבוע לפני הדרבי התל-אביבי הלוהט מול מכבי. במועדון מכוונים לזכייה ביורוקאפ "
        "ולהשגת הכרטיס ההיסטורי ליורוליג."
    ),
    "url": "https://www.ynet.co.il/sport/israelibasketball/article/s99k2l1100",
    "publisher": "ynet",
    "published_at": datetime(2026, 8, 29, 8, 20, 0, tzinfo=timezone.utc),
    "category": "כדורסל ישראלי",
    "author": "אפרת עמורבן",
    "image_url": "https://images.ynet.co.il/hapoel_ta_basket.jpg",
}

TRANSFER_RAW_ARTICLE: Dict[str, Any] = ONE_RAW_ARTICLE

INJURY_RAW_ARTICLE: Dict[str, Any] = {
    "title": "מכה לנבחרת ישראל: מנור סולומון נפצע בקרסול וייעדר כחודש",
    "raw_body": (
        "הקשר הישראלי עבר הבוקר בדיקת MRI שאישרה פגיעה ברצועות הקרסול. "
        "סולומון יחמיץ את צמד המפגשים הקריטיים של נבחרת ישראל במסגרת ליגת האומות מול צרפת ואיטליה. "
        "בצוות הרפואי של הנבחרת מקווים כי יחזור לכשירות לקראת חלון המשחקים הבא באוקטובר."
    ),
    "url": "https://www.one.co.il/Article/25-26/1,1,3,0/478902.html",
    "publisher": "one",
    "published_at": datetime(2026, 8, 29, 9, 0, 0, tzinfo=timezone.utc),
    "category": "נבחרת ישראל",
    "author": "גידי ליפקין",
    "image_url": "https://images.one.co.il/solomon_injury.jpg",
}

OLYMPIC_JUDO_RAW_ARTICLE: Dict[str, Any] = {
    "title": "מדליית זהב היסטורית לנבחרת הג'ודו של ישראל באליפות אירופה",
    "raw_body": (
        "הישג ספורטיבי כביר בטביליסי: פיטר פלצ'יק ורז הרשקו כיכבו בקרבות הגמר המכריעים "
        "והעניקו לנבחרת ישראל את המקום הראשון בפודיום הקבוצתי. "
        "מאמן הנבחרת אורן סמדג'ה אמר בדמעות: 'זהו רגע מכונן עבור הספורט הישראלי'."
    ),
    "url": "https://sports.walla.co.il/item/369901",
    "publisher": "walla",
    "published_at": datetime(2026, 8, 29, 8, 0, 0, tzinfo=timezone.utc),
    "category": "ג'ודו",
    "author": "יניב טוכמן",
    "image_url": "https://images.walla.co.il/judo_gold.jpg",
}

# ---------------------------------------------------------------------------
# 2. Master List of Sample Raw Articles
# ---------------------------------------------------------------------------

SAMPLE_RAW_ARTICLES: List[Dict[str, Any]] = [
    SPORT5_RAW_ARTICLE,
    YNET_RAW_ARTICLE,
    ONE_RAW_ARTICLE,
    MACCABI_HAIFA_FOOTBALL_RAW_ARTICLE,
    HAPOEL_TA_DERBY_RAW_ARTICLE,
    INJURY_RAW_ARTICLE,
    OLYMPIC_JUDO_RAW_ARTICLE,
]


# ---------------------------------------------------------------------------
# 3. Factory Helpers (Safe Dynamic Model Instantiation)
# ---------------------------------------------------------------------------

def get_sample_raw_payloads() -> List[Any]:
    """Returns a list of RawArticlePayload Pydantic instances if schemas exist, else dicts."""
    try:
        from schemas.feed import RawArticlePayload
        return [RawArticlePayload(**art) for art in SAMPLE_RAW_ARTICLES]
    except (ImportError, Exception):
        return [art.copy() for art in SAMPLE_RAW_ARTICLES]


def get_sample_raw_payload_by_publisher(publisher: str) -> Optional[Any]:
    """Returns a sample article payload matching the given publisher."""
    for art in SAMPLE_RAW_ARTICLES:
        if art.get("publisher", "").lower() == publisher.lower():
            try:
                from schemas.feed import RawArticlePayload
                return RawArticlePayload(**art)
            except (ImportError, Exception):
                return art.copy()
    return None
