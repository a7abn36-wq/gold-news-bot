# -*- coding: utf-8 -*-
"""وحدة التقويم الاقتصادي: ForexFactory + تنبيه قبل الأخبار المهمة + أسماء بالعربي"""
import html
import logging
import re
from datetime import datetime, timedelta
from xml.etree import ElementTree

import requests

import config
import state as db  # حفظ الحالة في JSON (شغال على Termux وعلى GitHub Actions)

log = logging.getLogger("calendar")

try:
    from zoneinfo import ZoneInfo
    TZ_ET = ZoneInfo("America/New_York")   # توقيت مصدر التقويم (نيويورك)
    TZ_CAIRO = ZoneInfo(config.TIMEZONE)
except Exception:
    TZ_ET = TZ_CAIRO = None

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

IMPACT_AR = {
    "High": "🔴 عالي جداً", "Medium": "🟡 متوسط",
    "Low": "🟢 منخفض", "Holiday": "🏖️ عطلة",
}


def _parse_event_time(date_str: str, time_str: str):
    """يحوّل وقت التقويم (بتوقيت نيويورك) لتوقيت القاهرة"""
    try:
        dt = datetime.strptime(date_str.strip(), "%m-%d-%Y")
        t = (time_str or "").strip().lower()
        if t in ("", "all day", "tentative", "holiday"):
            return dt.replace(tzinfo=TZ_ET) if TZ_ET else dt, t in ("all day", "tentative", "holiday", "")
        m = re.match(r"(\d{1,2}):(\d{2})(am|pm)", t)
        if not m:
            return dt.replace(tzinfo=TZ_ET) if TZ_ET else dt, True
        hh, mm, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        if ampm == "pm" and hh != 12:
            hh += 12
        if ampm == "am" and hh == 12:
            hh = 0
        dt = dt.replace(hour=hh, minute=mm, tzinfo=TZ_ET)
        return dt, False
    except Exception as ex:
        log.warning("مشكلة في تحليل وقت الحدث %s: %s", date_str, ex)
        return None, True


def fetch_calendar():
    """يجيب أحداث الأسبوع من ForexFactory"""
    resp = requests.get(CALENDAR_URL, headers={"User-Agent": config.USER_AGENT}, timeout=25)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.content)
    events = []
    for ev in root.iter("event"):
        title = (ev.findtext("title") or "").strip()
        country = (ev.findtext("country") or "").strip()
        date_str = (ev.findtext("date") or "").strip()
        time_str = (ev.findtext("time") or "").strip()
        impact = (ev.findtext("impact") or "").strip()
        forecast = (ev.findtext("forecast") or "").strip()
        previous = (ev.findtext("previous") or "").strip()
        dt_et, vague = _parse_event_time(date_str, time_str)
        if dt_et is None:
            continue
        dt_cairo = dt_et.astimezone(TZ_CAIRO) if (TZ_CAIRO and dt_et.tzinfo) else dt_et
        events.append({
            "title": title, "country": country, "impact": impact,
            "forecast": forecast, "previous": previous,
            "dt": dt_cairo, "vague": vague,
        })
    log.info("التقويم: جبت %d حدث", len(events))
    return events


def event_name_ar(title: str) -> str:
    """اسم الحدث بالعربي لو موجود"""
    key = title.strip().lower()
    for en, ar in config.EVENT_NAMES_AR.items():
        if en in key:
            return ar
    return title


def format_event(ev, show_day=False) -> str:
    """صياغة رسالة الحدث"""
    name = html.escape(event_name_ar(ev["title"]))
    impact = IMPACT_AR.get(ev["impact"], "⚪️ " + ev["impact"])
    cur = config.CURRENCY_AR.get(ev["country"], ev["country"])
    time_str = ev["dt"].strftime("%I:%M %p") if not ev["vague"] else "وقت غير محدد"
    day = ev["dt"].strftime("%A")
    day_ar = {"Saturday": "السبت", "Sunday": "الأحد", "Monday": "الاتنين",
              "Tuesday": "التلات", "Wednesday": "الأربع", "Thursday": "الخميس",
              "Friday": "الجمعة"}.get(day, day)
    msg = f"{impact.split(' ')[0]} <b>{name}</b>\n"
    msg += f"🕐 {day_ar} {time_str} بتوقيت القاهرة | التأثير: {impact.split(' ')[1]}\n"
    if show_day:
        msg += f"📅 {ev['dt'].strftime('%d/%m')} | {cur}\n"
    if ev["forecast"]:
        msg += f"📈 المتوقع: {html.escape(ev['forecast'])}"
        if ev["previous"]:
            msg += f" | السابق: {html.escape(ev['previous'])}"
        msg += "\n"
    return msg


def get_today_tomorrow_events():
    """أحداث النهاردة وبكرة (أمريكي + مهمة) للعرض في أمر /calendar"""
    try:
        events = fetch_calendar()
    except Exception as ex:
        log.warning("فشل جلب التقويم: %s", ex)
        return None
    now = datetime.now(TZ_CAIRO) if TZ_CAIRO else datetime.now()
    end = now + timedelta(days=2)
    picked = [e for e in events
              if e["country"] == "USD"
              and e["impact"] in ("High", "Medium")
              and not e["vague"]
              and now <= e["dt"] <= end]
    picked.sort(key=lambda e: e["dt"])
    return picked


def get_due_alerts():
    """الأحداث المهمة اللي قربت ولسه منبهناش (قبلها ALERT_BEFORE_MINUTES دقيقة)"""
    try:
        events = fetch_calendar()
    except Exception as ex:
        log.warning("فشل جلب التقويم للتنبيهات: %s", ex)
        return []
    now = datetime.now(TZ_CAIRO) if TZ_CAIRO else datetime.now()
    window_end = now + timedelta(minutes=config.ALERT_BEFORE_MINUTES)
    due = []
    for e in events:
        if e["country"] != "USD" or e["impact"] != "High" or e["vague"]:
            continue
        if not (now <= e["dt"] <= window_end):
            continue
        key = f"{e['title']}|{e['dt'].strftime('%Y%m%d%H%M')}"
        if db.is_alert_sent(key):
            continue
        minutes_left = int((e["dt"] - now).total_seconds() // 60)
        due.append((e, minutes_left, key))
    return due
