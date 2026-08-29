"""Authentic sample RSS XML feeds for Israeli sports portals (Sport5, Ynet, ONE, Walla).

These fixtures contain valid UTF-8 Hebrew sports news feeds with realistic items,
dates, categories, and author metadata for deterministic offline testing.
"""

SPORT5_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>אתר ערוץ הספורט - חדשות ספורט, כדורגל ישראלי ועולמי, כדורסל</title>
    <link>https://www.sport5.co.il</link>
    <description>מבזקי ספורט בזמן אמת, תוצאות, טבלאות וסיקורים בלעדיים מכל ענפי הספורט בישראל ובעולם</description>
    <language>he</language>
    <lastBuildDate>Sat, 29 Aug 2026 14:00:00 +0300</lastBuildDate>
    <item>
      <title>ניצחון ענק: מכבי תל אביב גברה 82:86 על ריאל מדריד ביורוליג</title>
      <link>https://www.sport5.co.il/articles.aspx?FolderID=64&amp;docID=450101</link>
      <description>תצוגת ענק של הצהובים בהיכל מנורה מבטחים. 24 נקודות לבולדווין וקאמבק הירואי ברבע האחרון הבטיחו מקום בפלייאוף.</description>
      <pubDate>Sat, 29 Aug 2026 13:45:00 +0300</pubDate>
      <guid isPermaLink="true">https://www.sport5.co.il/articles.aspx?FolderID=64&amp;docID=450101</guid>
      <category>כדורסל</category>
      <category>יורוליג</category>
      <category>מכבי תל אביב</category>
      <dc:creator>עמרי פולק</dc:creator>
    </item>
    <item>
      <title>לקראת הדרבי הגדול: מכבי חיפה מוכנה למפגש מול הפועל חיפה</title>
      <link>https://www.sport5.co.il/articles.aspx?FolderID=64&amp;docID=450102</link>
      <description>דגו מתלבט בנוגע למערך בסמי עופר. דין דוד צפוי לפתוח בחוד, שרי חוזר להרכב אחרי מנוחה קצרה.</description>
      <pubDate>Sat, 29 Aug 2026 12:30:00 +0300</pubDate>
      <guid isPermaLink="true">https://www.sport5.co.il/articles.aspx?FolderID=64&amp;docID=450102</guid>
      <category>כדורגל ישראלי</category>
      <category>ליגת העל</category>
      <category>מכבי חיפה</category>
      <dc:creator>תומר לוי</dc:creator>
    </item>
    <item>
      <title>דני אבדיה הצטיין בוושינגטון עם דאבל-דאבל של 18 נקודות ו-11 ריבאונדים</title>
      <link>https://www.sport5.co.il/articles.aspx?FolderID=400&amp;docID=450103</link>
      <description>הישראלי הוביל את הוויזארדס לניצחון חוץ יוקרתי על שיקגו בולס. מאמנו שיבח: "הבגרות שלו על המגרש יוצאת דופן".</description>
      <pubDate>Sat, 29 Aug 2026 10:15:00 +0300</pubDate>
      <guid isPermaLink="true">https://www.sport5.co.il/articles.aspx?FolderID=400&amp;docID=450103</guid>
      <category>NBA</category>
      <category>ישראלים בחו"ל</category>
      <dc:creator>יואב מודעי</dc:creator>
    </item>
  </channel>
</rss>"""

YNET_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>ynet ספורט - כדורגל, כדורסל וספורט ישראלי ועולמי</title>
    <link>https://www.ynet.co.il/sport</link>
    <description>כל חדשות הספורט בארץ ובעולם, כתבות עומק ופרשנויות - ynet ספורט</description>
    <language>he-il</language>
    <pubDate>Sat, 29 Aug 2026 13:50:00 GMT</pubDate>
    <item>
      <title>סערה בבית"ר ירושלים: החלוץ הזר הודיע על עזיבה מיידית</title>
      <link>https://www.ynet.co.il/sport/israelifootball/article/r1j8xk9211</link>
      <description>זעזוע בבירה יומיים לפני משחק העונה. ברק אברמוב: "אף שחקן אינו מעל המועדון, נתחזק בחלון ההעברות הקרוב".</description>
      <pubDate>Sat, 29 Aug 2026 13:10:00 GMT</pubDate>
      <guid isPermaLink="true">https://www.ynet.co.il/sport/israelifootball/article/r1j8xk9211</guid>
      <category>ליגת העל</category>
      <category>בית"ר ירושלים</category>
      <author>גידי ליפקין</author>
    </item>
    <item>
      <title>הפועל תל אביב בכדורסל החתימה גארד אמריקאי נוצץ</title>
      <link>https://www.ynet.co.il/sport/israelibasketball/article/s99k2l1100</link>
      <description>האדומים השלימו את הסגל עם שחקן בעל עבר עשיר ביורוליג וב-NBA. סטפנוס דדאס: "מדובר בחיזוק משמעותי ליורוקאפ".</description>
      <pubDate>Sat, 29 Aug 2026 11:20:00 GMT</pubDate>
      <guid isPermaLink="true">https://www.ynet.co.il/sport/israelibasketball/article/s99k2l1100</guid>
      <category>כדורסל ישראלי</category>
      <category>הפועל תל אביב</category>
      <author>אפרת עמורבן</author>
    </item>
  </channel>
</rss>"""

ONE_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>ONE - ספורט: כדורגל, כדורסל וספורט ישראלי ועולמי</title>
    <link>https://www.one.co.il</link>
    <description>אתר הספורט המוביל בישראל: דיווחים ראשוניים, פרסומים ראשונים וראיונות בלעדיים</description>
    <language>he</language>
    <lastBuildDate>Sat, 29 Aug 2026 14:15:00 +0300</lastBuildDate>
    <item>
      <title>פרסום ראשון: הפועל באר שבע פתחה במו"מ לצירוף קשר נבחרת רומניה</title>
      <link>https://www.one.co.il/Article/25-26/1,1,3,0/478901.html</link>
      <description>אלונה ברקת נותנת אור ירוק למהלך. השחקן מבוקש גם בליגה הפולנית, אך בטרנר מקווים לסגור את העסקה תוך 48 שעות.</description>
      <pubDate>Sat, 29 Aug 2026 13:40:00 +0300</pubDate>
      <guid isPermaLink="true">https://www.one.co.il/Article/25-26/1,1,3,0/478901.html</guid>
      <category>הפועל באר שבע</category>
      <category>חלון ההעברות</category>
    </item>
    <item>
      <title>מכה לנבחרת ישראל: מנור סולומון נפצע בקרסול וייעדר כחודש</title>
      <link>https://www.one.co.il/Article/25-26/1,1,3,0/478902.html</link>
      <description>הקשר עבר בדיקת MRI שאישרה את חומרת הפציעה. יחמיץ את שני המשחקים הקרובים בליגת האומות מול צרפת ואיטליה.</description>
      <pubDate>Sat, 29 Aug 2026 12:00:00 +0300</pubDate>
      <guid isPermaLink="true">https://www.one.co.il/Article/25-26/1,1,3,0/478902.html</guid>
      <category>נבחרת ישראל</category>
      <category>ליגת האומות</category>
    </item>
  </channel>
</rss>"""

WALLA_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>וואלה! ספורט</title>
    <link>https://sports.walla.co.il</link>
    <description>חדשות ספורט, כדורגל עולמי וישראלי, כדורסל וספורט אולימפי</description>
    <language>he</language>
    <item>
      <title>מדליית זהב היסטורית לנבחרת הג'ודו של ישראל באליפות אירופה</title>
      <link>https://sports.walla.co.il/item/369901</link>
      <description>הישג מופלא בטביליסי: פיטר פלצ'יק ורז הרשקו כיכבו בקרבות המכריעים והעניקו לישראל את המקום הראשון בפודיום.</description>
      <pubDate>Sat, 29 Aug 2026 11:00:00 +0300</pubDate>
      <guid isPermaLink="true">https://sports.walla.co.il/item/369901</guid>
      <category>ג'ודו</category>
      <category>ספורט אולימפי</category>
    </item>
  </channel>
</rss>"""

EMPTY_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Israeli Sports Feed</title>
    <link>https://www.example.co.il/sport</link>
    <description>Feed without active items</description>
  </channel>
</rss>"""

CORRUPTED_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Broken Feed</title>
    <item>
      <title>Unclosed tag test
      <link>https://broken.co.il/item/1
    </item>
"""

SAMPLE_RSS_FEEDS = {
    "sport5": SPORT5_RSS_XML,
    "ynet": YNET_RSS_XML,
    "one": ONE_RSS_XML,
    "walla": WALLA_RSS_XML,
    "empty": EMPTY_RSS_XML,
    "corrupted": CORRUPTED_RSS_XML,
}
