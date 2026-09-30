# -*- coding: utf-8 -*-
"""
إعدادات بوت أخبار الدهب والدولار 💛💵
=====================================================
نسخة Termux (الموبايل):  افتح الملف ده وعدّل حاجتين:
1) BOT_TOKEN   → التوكن اللي خدته من @BotFather
2) CHANNEL_ID  → القناة اللي البوت بينشر فيها

نسخة GitHub Actions: مش محتاج تعدل حاجة هنا —
حط القيم في Repo Secrets باسم TELEGRAM_TOKEN و CHANNEL_ID
"""
import os

# ===== التوكن: بيقرأ من متغيرات البيئة الأول (لنسخة GitHub) أو القيمة هنا (لنسخة الموبايل) =====
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN") or ""

# ===== القناة: نفس الفكرة =====
CHANNEL_ID = os.environ.get("CHANNEL_ID") or ""

# ===== إعدادات النشر (ممكن تسيبها زي ما هي) =====
NEWS_CHECK_MINUTES = 10      # كل كام دقيقة يجيب أخبار جديدة
NEWS_MAX_PER_CYCLE = 8       # أقصى عدد أخبار تنشر في المرة الواحدة
RELEVANCE_THRESHOLD = 3      # الحد الأدنى لأهمية الخبر عشان يتنشر (3 = مفتوح شوية عشان الغرفة متسكتش)
SILENCE_VALVE_MINUTES = 120  # لو مفيش خبر اتنشر المدة دي، ابعت أقوى خبر جديد موجود مهما كانت نقاطه
CALENDAR_CHECK_MINUTES = 5   # كل كام دقيقة يفحص التقويم الاقتصادي
ALERT_BEFORE_MINUTES = 30    # ينبّهك قبل الخبر المهم بكام دقيقة
SEND_DELAY_SECONDS = 2       # فاصل بين كل رسالة (عشان حدود تليجرام)

# المنطقة الزمنية لعرض الأوقات
TIMEZONE = "Africa/Cairo"

# ===== مصادر الأخبار (لو مصدر وقع البوت يكمل الباقي عادي) =====
# النوع: gold = أخبار دهب/سلع مخصصة | markets = أخبار أسواق عامة
# ملاحظة: ياهو فاينانس بيحجب سيرفرات جي هب — استبدلناه بمصادر مجربة شغالة
NEWS_SOURCES = [
    ("WSJ - الأسواق", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "gold"),
    ("Investing - الكوموديتيز", "https://www.investing.com/rss/news_11.rss", "gold"),
    ("Investing - الاقتصاد", "https://www.investing.com/rss/news_14.rss", "markets"),
    ("CNBC - الاقتصاد", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258", "markets"),
    ("CNBC - أمريكا", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "markets"),
    ("Investing - الفوركس", "https://www.investing.com/rss/news_1.rss", "markets"),
    ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories", "markets"),
]

# ===== كلمات الترشيح ووزنها (كل ما الرقم أكبر = الخبر أهم) =====
KEYWORDS = {
    # الدهب
    "gold": 6, "xau": 6, "bullion": 6, "precious metal": 5, "safe haven": 6,
    # الفايدرالي والفائدة
    "fed": 4, "federal reserve": 5, "fomc": 6, "powell": 6,
    "interest rate": 5, "rate cut": 6, "rate hike": 6, "rate decision": 6,
    # الدولار
    "dollar": 4, "dxy": 6, "usd": 3, "greenback": 4, "currency market": 3,
    # بيانات التضخم والتوظيف
    "inflation": 4, "cpi": 6, "pce": 4, "ppi": 3, "payrolls": 6,
    "nfp": 6, "jobs report": 6, "unemployment": 4, "gdp": 3, "recession": 4,
    # العوائد والسندات
    "treasury": 3, "yield": 4, "bond": 2, "10-year": 3,
    # جيوسياسي (بيحرك الدهب كملاذ آمن)
    "tariff": 3, "war": 3, "sanctions": 3, "geopolit": 4,
    "central bank": 4, "ecb": 3, "boj": 3, "pboc": 3,
}

# ===== أسماء الأحداث الاقتصادية بالعربي (الأشهر) =====
# لو حدث مش موجود هنا بيظهر باسمه الأصلي
EVENT_NAMES_AR = {
    "cpi m/m": "التضخم الشهري (CPI)",
    "cpi y/y": "التضخم السنوي (CPI)",
    "core cpi m/m": "التضخم الأساسي الشهري (CPI)",
    "non-farm employment change": "تقرير الوظائف الأمريكية (NFP)",
    "unemployment rate": "معدل البطالة",
    "fomc statement": "بيان الفايدرالي بشأن الفائدة",
    "fomc meeting minutes": "محضر اجتماع الفايدرالي",
    "federal funds rate": "قرار الفائدة الأمريكي",
    "fomc press conference": "مؤتمر صحفي لرئيس الفايدرالي",
    "adp non-farm employment change": "تقرير الوظائف (ADP)",
    "core pce price index m/m": "التضخم الأساسي (PCE) - المقياس المفضل للفايدرالي",
    "retail sales m/m": "المبيعات التجزئة",
    "ism manufacturing pmi": "مؤشر قطاع التصنيع (PMI)",
    "ism services pmi": "مؤشر قطاع الخدمات (PMI)",
    "gdp q/q": "الناتج المحلي الإجمالي",
    "crude oil inventories": "مخزونات النفط الأمريكية",
    "preliminary uom consumer sentiment": "ثقة المستهلك",
    "jobless claims": "طلبات إعانة البطالة الأسبوعية",
    "jolts job openings": "الوظائف الشاغرة (JOLTS)",
    "average hourly earnings m/m": "متوسط الأجور بالساعة",
    "powell speaks": "تصريحات باول - رئيس الفايدرالي",
    "monetary policy meeting minutes": "محضر اجتماع السياسة النقدية",
    "monetary policy statement": "بيان السياسة النقدية",
}

# أسماء العملات بالعربي (بتظهر في التقويم)
CURRENCY_AR = {
    "USD": "🇺🇸 أمريكي", "EUR": "🇪🇺 أوروبي", "GBP": "🇬🇧 بريطاني",
    "JPY": "🇯🇵 ياباني", "CNY": "🇨🇳 صيني", "CAD": "🇨🇦 كندي",
    "AUD": "🇦🇺 أسترالي", "CHF": "🇨🇭 سويسري", "ALL": "🌍 عالمي",
}

# مفتاح User-Agent (عشان المواقع ماتحجبش البوت)
USER_AGENT = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36")

# ياهو فاينانس بيرفض UA الموبايل من سيرفرات (429) — لAPI الأسعار بنستخدم UA ديسكتوب
DESKTOP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
