# -*- coding: utf-8 -*-
"""حفظ حالة البوت في ملف JSON بسيط — بديل SQLite
====================================================
ليه؟ عشان نسخة GitHub Actions مفيش فيها قرص دائم:
كل تشغيل بيفتح، والحالة بتترجع تتحفظ في الريبو نفسه (برانش bot-state).

بنحفظ:
- seen_news:      الأخبار اللي اتشافت (عشان ماتتنشرش مرتين)
- seen_alerts:    التنبيهات اللي اتبعتت (عشان التنبيه ميتكررش)
- translations:   كاش الترجمة (عشان ماتترجمش نفس الخبر مرتين)
- last_news_check: آخر مرة جبنا أخبار (للتحكم في فترة الفحص)
- last_update_id:  آخر رسالة أتمر اتقرات (لرد على الأوامر)
"""
import hashlib
import json
import logging
import os
import tempfile
import time

log = logging.getLogger("state")

os.makedirs("data", exist_ok=True)
STATE_PATH = os.path.join("data", "state.json")

NEWS_TTL_DAYS = 3        # مدة تذكر الأخبار والتنبيهات
TRANS_TTL_DAYS = 7       # مدة الاحتفاظ بترجمة في الكاش
TRANS_MAX_ENTRIES = 400  # أقصى عدد ترجمات محفوظة (عشان الملف يفضل صغير)

_state = None


def _empty() -> dict:
    return {
        "seen_news": {},      # لينك الخبر -> وقت النشر (epoch)
        "seen_alerts": {},    # مفتاح التنبيه -> وقت الإرسال (epoch)
        "translations": {},   # md5 -> [الترجمة, وقت الحفظ (epoch)]
        "last_news_check": 0,
        "last_update_id": 0,
    }


def load() -> dict:
    """تحميل الحالة من الملف (مرة واحدة) — لو الملف مش موجود يبدأ من صفحة بيضاء"""
    global _state
    if _state is not None:
        return _state
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            _state = json.load(f)
        # تأمين: اتأكد إن كل المفاتيح موجودة حتى لو الملف قديم
        for key, value in _empty().items():
            _state.setdefault(key, value)
        log.info("حملت الحالة: %d خبر مشوف، %d ترجمة، %d تنبيه",
                 len(_state["seen_news"]), len(_state["translations"]),
                 len(_state["seen_alerts"]))
    except Exception:
        _state = _empty()
    return _state


def save():
    """حفظ الحالة في الملف (كتابة آمنة: ملف مؤقت وبعدين استبدال)"""
    if _state is None:
        return
    os.makedirs("data", exist_ok=True)
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir="data", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, STATE_PATH)
        tmp = None
    except Exception as ex:
        log.warning("الحفظ الآمن فشل (%s) — هجرب الطريقة العادية", ex)
        try:
            with open(STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(_state, f, ensure_ascii=False)
        except Exception as ex2:
            log.error("مقدرتش أحفظ الحالة خالص: %s", ex2)
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def text_hash(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode("utf-8")).hexdigest()


# ---------- الأخبار ----------
def is_news_seen(link: str) -> bool:
    return link in load()["seen_news"]


def mark_news_seen(link: str):
    load()["seen_news"][link] = time.time()


# ---------- الترجمات (كاش) ----------
def get_cached_translation(text: str):
    entry = load()["translations"].get(text_hash(text))
    return entry[0] if entry else None


def cache_translation(original: str, arabic: str):
    translations = load()["translations"]
    translations[text_hash(original)] = [arabic, time.time()]
    # لو الكاش كبر أوي شيل الأقدم (LRU بسيط)
    if len(translations) > TRANS_MAX_ENTRIES:
        oldest = sorted(translations.items(), key=lambda kv: kv[1][1])
        for key, _ in oldest[:len(translations) - TRANS_MAX_ENTRIES]:
            translations.pop(key, None)


# ---------- تنبيهات التقويم ----------
def is_alert_sent(alert_key: str) -> bool:
    return alert_key in load()["seen_alerts"]


def mark_alert_sent(alert_key: str):
    load()["seen_alerts"][alert_key] = time.time()


# ---------- فحص الأخبار (عشان نحترم فترة الفحص على كرون الـ 5 دقايق) ----------
def get_last_news_check() -> float:
    return load().get("last_news_check", 0)


def set_last_news_check(ts: float = None):
    load()["last_news_check"] = ts if ts is not None else time.time()


# ---------- رسايل الأوامر ----------
def get_last_update_id() -> int:
    return load().get("last_update_id", 0)


def set_last_update_id(update_id):
    try:
        update_id = int(update_id)
        if update_id > load().get("last_update_id", 0):
            load()["last_update_id"] = update_id
    except (TypeError, ValueError):
        pass


# ---------- تنظيف القديم ----------
def cleanup():
    now = time.time()
    s = load()
    news_limit = now - NEWS_TTL_DAYS * 86400
    trans_limit = now - TRANS_TTL_DAYS * 86400
    s["seen_news"] = {k: v for k, v in s["seen_news"].items() if v > news_limit}
    s["seen_alerts"] = {k: v for k, v in s["seen_alerts"].items() if v > news_limit}
    s["translations"] = {k: v for k, v in s["translations"].items()
                         if isinstance(v, (list, tuple)) and len(v) >= 2 and v[1] > trans_limit}
