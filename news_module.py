# -*- coding: utf-8 -*-
"""وحدة الأخبار: جلب من المصادر + ترشيح الدهب والدولار + ترجمة عربي كامل"""
import html
import logging
import re
import time
from datetime import datetime

import feedparser
import requests

import config
import state as db  # حفظ الحالة في JSON (شغال على Termux وعلى GitHub Actions)

log = logging.getLogger("news")

from zoneinfo import ZoneInfo
try:
    TZ = ZoneInfo(config.TIMEZONE)
except Exception:
    TZ = None


def _strip_html(text: str) -> str:
    """تشيل وسوم HTML من ملخص الخبر"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_all_sources():
    """يجيب كل الأخبار من كل المصادر — لو مصدر فشل بيكمل عادي"""
    items = []
    for name, url, kind in config.NEWS_SOURCES:
        try:
            resp = requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=20)
            feed = feedparser.parse(resp.content)
            count = 0
            for e in feed.entries[:15]:
                title = _strip_html(getattr(e, "title", ""))
                link = getattr(e, "link", "")
                if not title or not link:
                    continue
                summary = _strip_html(getattr(e, "summary", ""))[:400]
                items.append({
                    "title": title,
                    "link": link.split("?")[0],
                    "summary": summary,
                    "source": name,
                    "kind": kind,
                })
                count += 1
            log.info("المصدر %s: جبت %d خبر", name, count)
        except Exception as ex:
            log.warning("المصدر %s فشل: %s", name, ex)
    # إزالة المكرر بنفس اللينك
    seen, unique = set(), []
    for it in items:
        if it["link"] not in seen:
            seen.add(it["link"])
            unique.append(it)
    return unique


def relevance_score(item) -> int:
    """بيعطي الخبر درجة أهمية بناء على كلماته — الدهب والدولار الأول"""
    text = (item["title"] + " " + item["summary"]).lower()
    score = sum(w for kw, w in config.KEYWORDS.items() if kw in text)
    if item["kind"] == "gold":
        score += 3  # مصادر الدهب المخصصة لها أفضليّة
    return score


def _translate_chrome(text: str):
    """ترجمة عن طريق endpoint كروم في جوجل (clients5) — ده الرف اللي بيسمح بآيبيهات السيرفرات
    (المهم لنسخة GitHub Actions: endpoint التليفونات بيمنع آيبيهات السيرفرات بـ 429)"""
    try:
        resp = requests.get(
            "https://clients5.google.com/translate_a/t",
            params={"client": "dict-chrome-ex", "sl": "auto", "tl": "ar",
                    "q": text[:4500]},
            headers={"User-Agent": config.USER_AGENT},
            timeout=15)
        data = resp.json()
        parts = []
        if isinstance(data, list):
            for seg in data:
                if isinstance(seg, list) and seg and isinstance(seg[0], str):
                    parts.append(seg[0])
                elif isinstance(seg, str):
                    parts.append(seg)
        result = " ".join(p.strip() for p in parts if p and p.strip())
        return result or None
    except Exception as ex:
        log.warning("مترجم كروم فشل: %s", str(ex)[:100])
        return None


def translate_to_arabic(text: str) -> str:
    """ترجمة للعربي مع كاش + 3 مصادر مرتبة — لو كله فشل يرجع النص الأصلي"""
    text = text.strip()
    if not text:
        return text
    cached = db.get_cached_translation(text)
    if cached:
        return cached

    # المصدر 1: endpoint كروم (شغال من السيرفرات ومن الموبايل)
    result = _translate_chrome(text)

    # المصدر 2: جوجل ترانسليت العادي (بيشتغل من نت الموبايل — مفيد لنسخة Termux)
    if not result:
        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source="auto", target="ar")
            for attempt in range(2):
                try:
                    result = translator.translate(text[:4500])
                    if result:
                        break
                except Exception as ex:
                    log.warning("محاولة ترجمة %d فشلت: %s", attempt + 1, ex)
                    time.sleep(1.5 * (attempt + 1))
        except Exception as ex:
            log.warning("جوجل ترانسليت غير متاح: %s", ex)

    # المصدر 3: MyMemory (احتياطي أخير)
    if not result:
        try:
            from deep_translator import MyMemoryTranslator
            result = MyMemoryTranslator(source="en-US", target="ar-EG").translate(text[:4500])
        except Exception as ex:
            log.warning("الترجمة الاحتياطية فشلت: %s", ex)

    if result:
        db.cache_translation(text, result)
        time.sleep(0.4)  # نفَس بسيط بين الترجمات
        return result

    return text  # النص الأصلي لو كل المحاولات وقعت


def now_cairo() -> datetime:
    return datetime.now(TZ) if TZ else datetime.now()


DIV = "━━━━━━━━━━━━━━━━━━"


def format_news_message(item, arabic_title: str, arabic_summary: str) -> str:
    """صياغة رسالة الخبر بالعربي — شكل نشرة اقتصادية فخمة
    (لينك الخبر بيتحط كزر تحت الرسالة عن طريق send_html)"""
    t = now_cairo().strftime("%I:%M %p")
    chip = "🟡 <b>الدهب والمعادن</b>" if item["kind"] == "gold" else "💵 <b>الأسواق والدولار</b>"
    msg = f"{chip}\n{DIV}\n\n"
    msg += f"<b>{html.escape(arabic_title)}</b>\n"
    if arabic_summary and arabic_summary != item["summary"]:
        msg += f"\n{html.escape(arabic_summary[:350])}\n"
    elif item["summary"]:
        msg += f"\n{html.escape(item['summary'][:350])}\n"
    msg += f"\n{DIV}\n📌 {html.escape(item['source'])} | 🕐 {t} بتوقيت القاهرة"
    return msg


def get_fresh_news() -> dict:
    """الوظيفة الرئيسية: يجيب الجديد، يرشّح المهم، يترجمه
    بيرجّع dict فيه:
      ready      = الجاهز للنشر (عدّى حد الأهمية)
      best_below = أقوى خبر جديد تحت الحد (score, item) — يستخدمه صمام منع السكوت
    """
    all_items = fetch_all_sources()
    fresh = [it for it in all_items if not db.is_news_seen(it["link"])]
    log.info("أخبار جديدة: %d من إجمالي %d", len(fresh), len(all_items))

    # ترتيب بالأهمية ثم ترشيح
    scored = [(relevance_score(it), it) for it in fresh]
    scored.sort(key=lambda x: -x[0])
    selected = [(s, it) for s, it in scored if s >= config.RELEVANCE_THRESHOLD]
    selected = selected[:config.NEWS_MAX_PER_CYCLE]

    ready = []
    for score, item in selected:
        arabic_title = translate_to_arabic(item["title"])
        arabic_summary = translate_to_arabic(item["summary"]) if item["summary"] else ""
        ready.append({
            "item": item,
            "score": score,
            "message": format_news_message(item, arabic_title, arabic_summary),
        })

    # أقوى خبر جديد تحت الحد — لازم يكون له علاقة أساسية على الأقل (score >= 1)
    best_below = None
    if scored and scored[0][0] >= 1:
        best_below = (scored[0][0], scored[0][1])

    # علّم كل الأخبار الجديدة كمشوفة (حتى اللي مش مهمة) عشان متتراجعش تاني
    for it in fresh:
        db.mark_news_seen(it["link"])
    return {"ready": ready, "best_below": best_below}
