"""Unit tests for Israeli sports news scrapers, 5-tier fallback cascade, and registry."""

from datetime import datetime, timezone
import pytest
from bs4 import BeautifulSoup

from fan_zone.scrapers.base import (
    BaseSourceParser,
    ExtractedArticle,
    ExtractedImage,
    clean_html_text,
    compute_content_hash,
    extract_heuristic_dom,
    extract_json_ld,
    extract_opengraph,
    extract_trafilatura,
    normalize_canonical_url,
    parse_datetime,
)
from fan_zone.scrapers.sport5 import Sport5Parser
from fan_zone.scrapers.one import ONEParser
from fan_zone.scrapers.walla import WallaParser
from fan_zone.scrapers.ynet import YnetParser
from fan_zone.scrapers.sport1 import Sport1Parser
from fan_zone.scrapers.israel_hayom import IsraelHayomParser
from fan_zone.scrapers.haaretz import HaaretzParser
from fan_zone.scrapers.registry import (
    ScraperRegistry,
    get_scraper,
    get_scraper_for_url,
    list_scrapers,
)


class TestSport5Scraper:
    """Unit tests for Sport5 scraper with HTML fixtures."""

    @pytest.fixture
    def sport5_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>מכבי תל אביב גברה על ריאל | ספורט 5</title>
        </head>
        <body>
            <article class="article-content">
                <h1 class="article-title">ניצחון דרמטי: מכבי תל אביב גברה 82:85 על ריאל מדריד</h1>
                <h2 class="article-subtitle">משחק ענק של הצהובים בהיכל. ווייד בולדווין להט עם 28 נקודות.</h2>
                <span class="article-credit">רועי כהן</span>
                <span class="article-date">28.08.26 - 22:30</span>
                <div class="article-main-image">
                    <img src="https://images.sport5.co.il/main_123.jpg" alt="בולדווין חוגג" />
                    <div class="main-image-caption">בולדווין חוגג ניצחון (צילום: אלן שיבר)</div>
                </div>
                <div class="article-body">
                    <p>מכבי תל אביב השיגה הערב ניצחון יוקרתי במיוחד בהיכל מנורה מבטחים.</p>
                    <p>הצהובים של עודד קטש גברו 82:85 על ריאל מדריד במסגרת המחזור ה-15 של היורוליג.</p>
                    <p>ווייד בולדווין הצטיין עם 28 נקודות ו-6 אסיסטים והוביל את המנצחת.</p>
                </div>
                <div class="article-gallery">
                    <img src="https://images.sport5.co.il/gal_1.jpg" />
                    <img src="https://images.sport5.co.il/gal_2.jpg" />
                </div>
                <div class="article-tags">
                    <a href="/tag/1">מכבי תל אביב</a>
                    <a href="/tag/2">יורוליג</a>
                </div>
            </article>
        </body>
        </html>
        """

    def test_sport5_parsing(self, sport5_html):
        parser = Sport5Parser()
        url = "https://www.sport5.co.il/articles.aspx?FolderID=64&docID=450000"
        extracted = parser.parse_article_html(sport5_html, url)

        assert extracted is not None
        assert extracted.source_name == "Sport5"
        assert extracted.canonical_url == normalize_canonical_url(url)
        assert "ניצחון דרמטי" in extracted.original_title
        assert "ווייד בולדווין להט" in extracted.original_subtitle
        assert extracted.author == "רועי כהן"
        assert extracted.published_at.year == 2026
        assert extracted.published_at.month == 8
        assert extracted.published_at.day == 28
        assert len(extracted.paragraphs) == 3
        assert extracted.main_image is not None
        assert extracted.main_image.url == "https://images.sport5.co.il/main_123.jpg"
        assert "אלן שיבר" in (extracted.main_image.caption or "")
        assert len(extracted.gallery_images) == 2
        assert "מכבי תל אביב" in extracted.tags


class TestONEScraper:
    """Unit tests for ONE scraper with RSS and HTML fixtures."""

    @pytest.fixture
    def one_rss_xml(self):
        return """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
            <channel>
                <title>ONE Sport News</title>
                <item>
                    <title>מכבי חיפה ניצחה 0:2 את בית"ר ירושלים</title>
                    <link>https://www.one.co.il/Article/2026/456789.html?utm_source=rss</link>
                    <pubDate>Fri, 28 Aug 2026 21:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>
        """

    @pytest.fixture
    def one_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>ONE כתבה</title></head>
        <body>
            <div id="article-content">
                <h1 class="article-title">מכבי חיפה ניצחה 0:2 את בית"ר ירושלים בסמי עופר</h1>
                <h2 class="article-subtitle">דין דוד ודיא סבע הבקיעו לירוקים, שהעפילו לפסגת ליגת העל.</h2>
                <span class="article-writer">גידי ליפקין</span>
                <span class="article-date">28/08/2026 21:15</span>
                <div class="article-main-img">
                    <img src="https://images.one.co.il/images/d/dsm/123.jpg" />
                    <div class="img-credit">צילום: רדאד ג'בארה</div>
                </div>
                <div class="article-body-content">
                    <p>מכבי חיפה רשמה הערב ניצחון מרשים על בית"ר ירושלים באצטדיון סמי עופר.</p>
                    <p>הקבוצה של ברק בכר שלטה במשחק לכל אורכו והשיגה שלוש נקודות יקרות.</p>
                </div>
            </div>
        </body>
        </html>
        """

    def test_one_rss_parsing(self, one_rss_xml):
        parser = ONEParser()
        links = parser.parse_rss_feed(one_rss_xml)
        assert len(links) == 1
        assert "one.co.il" in links[0]

    def test_one_article_parsing(self, one_html):
        parser = ONEParser()
        url = "https://www.one.co.il/Article/2026/456789.html"
        extracted = parser.parse_article_html(one_html, url)
        assert extracted is not None
        assert extracted.source_name == "ONE"
        assert "מכבי חיפה ניצחה 0:2" in extracted.original_title
        assert "דין דוד ודיא סבע" in extracted.original_subtitle
        assert extracted.author == "גידי ליפקין"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image.url == "https://images.one.co.il/images/d/dsm/123.jpg"
        assert "רדאד ג'בארה" in (extracted.main_image.credit or "")


class TestWallaScraper:
    """Unit tests for Walla! Sports scraper with HTML fixtures."""

    @pytest.fixture
    def walla_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>וואלה ספורט</title></head>
        <body>
            <article class="article-text">
                <h1 class="title">הפועל תל אביב זכתה בגביע המדינה בכדורסל</h1>
                <h2 class="subtitle">האדומים חגגו תואר היסטורי לאחר דרמה גדולה בהיכל.</h2>
                <div class="article-author"><span>אור שקדי</span></div>
                <span class="date">28.08.2026, 23:45</span>
                <figure class="main-media">
                    <img src="https://img.wcdn.co.il/f_auto,w_700,t_54/1/2/3/4.jpg" />
                    <figcaption>הנפת הגביע בהיכל (צילום: ברני ארדוב)</figcaption>
                </figure>
                <div class="css-article-body">
                    <p>הפועל תל אביב השלימה הערב מסע מופלא כשזכתה בגביע המדינה.</p>
                    <p>במשחק צמוד ומורט עצבים ניצחו האדומים של סטפנוס דדאס את היריבה העירונית.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_walla_parsing(self, walla_html):
        parser = WallaParser()
        url = "https://sports.walla.co.il/item/3691234"
        extracted = parser.parse_article_html(walla_html, url)
        assert extracted is not None
        assert extracted.source_name == "Walla! Sports"
        assert "הפועל תל אביב זכתה בגביע" in extracted.original_title
        assert "האדומים חגגו תואר" in extracted.original_subtitle
        assert extracted.author == "אור שקדי"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image.url == "https://img.wcdn.co.il/f_auto,w_700,t_54/1/2/3/4.jpg"


class TestYnetScraper:
    """Unit tests for Ynet Sport scraper with HTML fixtures."""

    @pytest.fixture
    def ynet_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>Ynet ספורט</title></head>
        <body>
            <article>
                <h1 class="mainTitle">ערן זהבי הודיע: אמשיך לעונה נוספת במכבי תל אביב</h1>
                <h2 class="subTitle">הקפטן הוותיק חתם על חוזה חדש לעונה אחת: "רעב לתארים נוספים".</h2>
                <div class="authorName">נדב צנציפר</div>
                <time class="date">28.08.26 , 17:30</time>
                <figure data-component="media">
                    <img src="https://images1.ynet.co.il/PicServer5/2026/08/28/123.jpg" />
                    <figcaption><span class="caption">זהבי במדים הצהובים</span></figcaption>
                </figure>
                <div data-component="article-body">
                    <p>עכשיו זה רשמי: ערן זהבי ממשיך במכבי תל אביב.</p>
                    <p>החלוץ הוותיק חתם היום על הארכת חוזהו במועדון לעונה נוספת.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_ynet_parsing(self, ynet_html):
        parser = YnetParser()
        url = "https://www.ynet.co.il/sport/israelisoccer/article/y12345678"
        extracted = parser.parse_article_html(ynet_html, url)
        assert extracted is not None
        assert extracted.source_name == "Ynet Sport"
        assert "ערן זהבי הודיע" in extracted.original_title
        assert "הקפטן הוותיק חתם" in extracted.original_subtitle
        assert extracted.author == "נדב צנציפר"
        assert len(extracted.paragraphs) == 2


class TestSport1Scraper:
    """Unit tests for Sport1 / Maariv scraper with HTML fixtures."""

    @pytest.fixture
    def sport1_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>ספורט 1 מעריב</title></head>
        <body>
            <article>
                <h1 class="entry-title">ברק בכר: "הראינו אופי של אלופים, הדרך עוד ארוכה"</h1>
                <h2 class="entry-subtitle">מאמן מכבי חיפה החמיא לשחקניו לאחר הניצחון במשחק העונה.</h2>
                <span class="author-name">שלמה וייס</span>
                <time class="entry-date">2026-08-28T22:45:00+03:00</time>
                <figure class="featured-image">
                    <img src="https://sport1.maariv.co.il/wp-content/uploads/2026/08/bachar.jpg" />
                    <figcaption class="image-caption">ברק בכר על הקווים (צילום: אריאל שלום)</figcaption>
                </figure>
                <div class="entry-content">
                    <p>במכבי חיפה חגגו את הניצחון החשוב שהחזיר את הקבוצה למקום הראשון.</p>
                    <p>המאמן ברק בכר הדגיש במסיבת העיתונאים את חשיבות המשכיות היכולת הגבוהה.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_sport1_parsing(self, sport1_html):
        parser = Sport1Parser()
        url = "https://sport1.maariv.co.il/israeli-soccer/ligat-haal/article/1234567"
        extracted = parser.parse_article_html(sport1_html, url)
        assert extracted is not None
        assert extracted.source_name == "Sport1"
        assert "ברק בכר" in extracted.original_title
        assert extracted.author == "שלמה וייס"
        assert len(extracted.paragraphs) == 2


class TestIsraelHayomScraper:
    """Unit tests for Israel Hayom scraper with HTML fixtures."""

    @pytest.fixture
    def israel_hayom_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head><title>ישראל היום ספורט</title></head>
        <body>
            <article>
                <h1 class="article-title">דני אבדיה קלע 24 נקודות בניצחון פורטלנד</h1>
                <h2 class="article-subtitle">משחק שיא לישראלי שקטף גם 9 ריבאונדים ומסר 6 אסיסטים.</h2>
                <div class="writer-name">אבי סגל</div>
                <time class="article-date">28.08.2026, 06:30</time>
                <div class="article-main-media">
                    <img src="https://www.israelhayom.co.il/wp-content/uploads/2026/08/avdija.jpg" />
                </div>
                <div class="article-content">
                    <p>דני אבדיה ממשיך להוכיח את מעמדו כאחד השחקנים המובילים של פורטלנד טרייל בלייזרס.</p>
                    <p>הפורוורד הישראלי הצטיין הלילה בניצחון על גולדן סטייט ווריורס.</p>
                </div>
            </article>
        </body>
        </html>
        """

    def test_israel_hayom_parsing(self, israel_hayom_html):
        parser = IsraelHayomParser()
        url = "https://www.israelhayom.co.il/sport/nba/article/1654321"
        extracted = parser.parse_article_html(israel_hayom_html, url)
        assert extracted is not None
        assert extracted.source_name == "Israel Hayom"
        assert "דני אבדיה קלע" in extracted.original_title
        assert "משחק שיא לישראלי" in extracted.original_subtitle
        assert extracted.author == "אבי סגל"
        assert len(extracted.paragraphs) == 2


class TestHaaretzScraper:
    """Unit tests for Haaretz scraper with HTML fixtures."""

    @pytest.fixture
    def haaretz_html(self):
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>הארץ ספורט</title>
            <meta property="og:title" content="המהפכה השקטה של ענף השחייה בישראל" />
            <meta property="og:description" content="ההישגים באליפויות העולם מעידים על תוכנית עבודה יסודית וארוכת טווח." />
            <meta property="og:image" content="https://img.haarets.co.il/img_123.jpg" />
        </head>
        <body>
            <article data-test="articleBody">
                <h1 data-test="articleHeadline">המהפכה השקטה של ענף השחייה בישראל</h1>
                <h2 data-test="articleSubtitle">ההישגים באליפויות העולם מעידים על תוכנית עבודה יסודית וארוכת טווח.</h2>
                <span data-test="authorName">איתמר קציר</span>
                <time data-test="publishDate">2026-08-28T18:00:00.000Z</time>
                <figure data-test="mainFigure">
                    <img src="https://img.haarets.co.il/img_123.jpg" />
                    <figcaption data-test="caption">אנסטסיה גורבנקו במים (צילום: אי-פי)</figcaption>
                </figure>
                <p data-test="articleParagraph">השחייה הישראלית רושמת את אחד הפרקים המרשימים ביותר בתולדותיה.</p>
                <div data-test="articleParagraph">דור חדש של שחיינים צעירים מגיע לגמרים עולמיים ומביא מדליות יוקרתיות.</div>
            </article>
        </body>
        </html>
        """

    def test_haaretz_parsing(self, haaretz_html):
        parser = HaaretzParser()
        url = "https://www.haaretz.co.il/sport/swimming/2026-08-28/ty-article/0000018f-1234"
        extracted = parser.parse_article_html(haaretz_html, url)
        assert extracted is not None
        assert extracted.source_name == "Haaretz"
        assert "המהפכה השקטה" in extracted.original_title
        assert extracted.author == "איתמר קציר"
        assert len(extracted.paragraphs) == 2


class Test5TierFallbackCascade:
    """Unit tests for the 5-tier extraction fallback cascade."""

    def test_fallback_to_json_ld_when_no_css(self):
        html = """
        <html>
        <head>
            <script type="application/ld+json">
            {
                "@type": "NewsArticle",
                "headline": "כותרת מ-JSON-LD",
                "description": "תיאור מ-JSON-LD",
                "articleBody": "פסקה ראשונה מהגוף.\nפסקה שנייה מהגוף.",
                "author": "ישראל ישראלי",
                "datePublished": "2026-08-28T12:00:00Z",
                "image": "https://example.com/ld_image.jpg"
            }
            </script>
        </head>
        <body>
            <div class="custom-unknown-container">תוכן ללא סלקטורים מוכרים</div>
        </body>
        </html>
        """
        parser = BaseSourceParser()
        extracted = parser.parse_article_html(html, "https://example.com/article/1")
        assert extracted.original_title == "כותרת מ-JSON-LD"
        assert extracted.original_subtitle == "תיאור מ-JSON-LD"
        assert len(extracted.paragraphs) == 2
        assert extracted.author == "ישראל ישראלי"
        assert extracted.main_image.url == "https://example.com/ld_image.jpg"

    def test_fallback_to_opengraph_when_no_json_ld(self):
        html = """
        <html>
        <head>
            <meta property="og:title" content="כותרת OpenGraph" />
            <meta property="og:description" content="תיאור OpenGraph" />
            <meta property="og:image" content="https://example.com/og_image.jpg" />
        </head>
        <body>
            <p>טקסט פסקה באורך סביר מעל עשרים תווים לבדיקת DOM.</p>
        </body>
        </html>
        """
        parser = BaseSourceParser()
        extracted = parser.parse_article_html(html, "https://example.com/article/2")
        assert extracted.original_title == "כותרת OpenGraph"
        assert extracted.original_subtitle == "תיאור OpenGraph"
        assert extracted.main_image.url == "https://example.com/og_image.jpg"

    def test_fallback_to_dom_heuristics(self):
        html = """
        <html>
        <head><title>כותרת הטאג כותרת | אתר ספורט</title></head>
        <body>
            <h1>כותרת ראשית H1</h1>
            <p>פסקה ראשונה בגוף הכתבה שמכילה מספיק תווים כדי להיחשב טקסט תוכן אמיתי.</p>
            <p>פסקה שנייה בגוף הכתבה שמכילה גם היא מספיק תווים כדי להילכד על ידי הניתוח.</p>
            <img src="https://example.com/content_img.jpg" />
        </body>
        </html>
        """
        parser = BaseSourceParser()
        extracted = parser.parse_article_html(html, "https://example.com/article/3")
        assert extracted.original_title == "כותרת ראשית H1"
        assert len(extracted.paragraphs) == 2
        assert extracted.main_image.url == "https://example.com/content_img.jpg"


class TestScraperRegistry:
    """Unit tests for ScraperRegistry lookups and url domain matching."""

    def test_registry_lookups(self):
        registry = ScraperRegistry()
        assert registry.get_scraper("sport5").source_name == "Sport5"
        assert registry.get_scraper("one").source_name == "ONE"
        assert registry.get_scraper("walla").source_name == "Walla! Sports"
        assert registry.get_scraper("ynet").source_name == "Ynet Sport"
        assert registry.get_scraper("sport1").source_name == "Sport1"
        assert registry.get_scraper("israel_hayom").source_name == "Israel Hayom"
        assert registry.get_scraper("haaretz").source_name == "Haaretz"

    def test_url_domain_detection(self):
        registry = ScraperRegistry()
        assert registry.get_scraper_for_url("https://www.sport5.co.il/articles.aspx?docID=1").source_name == "Sport5"
        assert registry.get_scraper_for_url("https://www.one.co.il/Article/123.html").source_name == "ONE"
        assert registry.get_scraper_for_url("https://sports.walla.co.il/item/123").source_name == "Walla! Sports"
        assert registry.get_scraper_for_url("https://www.ynet.co.il/sport/article/123").source_name == "Ynet Sport"
        assert registry.get_scraper_for_url("https://sport1.maariv.co.il/article/123").source_name == "Sport1"
        assert registry.get_scraper_for_url("https://www.israelhayom.co.il/sport/article/123").source_name == "Israel Hayom"
        assert registry.get_scraper_for_url("https://www.haaretz.co.il/sport/123").source_name == "Haaretz"

    def test_list_all_scrapers(self):
        scrapers = list_scrapers()
        assert len(scrapers) == 7
        codes = {s.source_code for s in scrapers}
        assert codes == {"sport5", "one", "walla", "ynet", "sport1", "israel_hayom", "haaretz"}
