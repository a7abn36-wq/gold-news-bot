# -*- coding: utf-8 -*-
"""وحدة الأسعار: الدهب لحظياً + الدولار DXY + الدولار/الجنيه + جرام الدهب في مصر"""
import html
import logging
from datetime import datetime

import requests

import config

log = logging.getLogger("prices")

GOLD_API = "https://api.gold-api.com/price/XAU"
RATES_API = "https://open.er-api.com/v6/latest/USD"

# معادلة حساب مؤشر الدولار من أسعار العملات (أوزان السلة الرسمية)
DXY_CONST = 50.14348112


def get_gold():
    """سعر أونصة الدهب لحظياً"""
    try:
        r = requests.get(GOLD_API, headers={"User-Agent": config.USER_AGENT}, timeout=15)
        data = r.json()
        return float(data["price"]), data.get("updatedAtReadable", "")
    except Exception as ex:
        log.warning("فشل جلب سعر الدهب: %s", ex)
        return None, None


def get_rates():
    """أسعار العملات مقابل الدولار"""
    try:
        r = requests.get(RATES_API, headers={"User-Agent": config.USER_AGENT}, timeout=15)
        return r.json().get("rates", {})
    except Exception as ex:
        log.warning("فشل جلب أسعار العملات: %s", ex)
        return {}


def compute_dxy(rates: dict):
    """حساب مؤشر الدولار تقريبي من سلة العملات"""
    try:
        eurusd = 1 / rates["EUR"]
        usdjpy = rates["JPY"]
        gbpusd = 1 / rates["GBP"]
        usdcad = rates["CAD"]
        usdsek = rates["SEK"]
        usdchf = rates["CHF"]
        dxy = (DXY_CONST
               * (eurusd ** -0.576)
               * (usdjpy ** 0.136)
               * (gbpusd ** -0.119)
               * (usdcad ** 0.091)
               * (usdsek ** 0.042)
               * (usdchf ** 0.036))
        return round(dxy, 2)
    except (KeyError, ZeroDivisionError, TypeError) as ex:
        log.warning("فشل حساب DXY: %s", ex)
        return None


def get_price_message():
    """الرسالة الكاملة لأمر /price"""
    gold, gold_time = get_gold()
    rates = get_rates()
    dxy = compute_dxy(rates)
    usdegp = rates.get("EGP")

    lines = ["💰 <b>الأسعار اللحظية</b>\n"]

    if gold:
        lines.append(f"🟡 الدهب (الأونصة): <b>{gold:,.2f}$</b>")
        if usdegp:
            gram_usd = gold / 31.1035
            gram_egp = gram_usd * usdegp
            lines.append(f"⚖️ جرام الدهب 24 في مصر: <b>~{gram_egp:,.0f} جنيه</b> (تقريبي بدون مصنعية)")
    else:
        lines.append("🟡 الدهب: مش قادر أجيبه دلوقتي — جرب تاني بعد شوية")

    if dxy:
        lines.append(f"💵 مؤشر الدولار DXY: <b>{dxy}</b> (تقريبي)")
    if usdegp:
        lines.append(f"🇪🇬 الدولار مقابل الجنيه: <b>{usdegp:.2f}</b>")

    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%I:%M %p")
    except Exception:
        now = datetime.now().strftime("%I:%M %p")
    lines.append(f"\n🕐 {now} بتوقيت القاهرة")
    lines.append("⚠️ الأسعار للمعرفة فقط — اتأكد من منصتك قبل ما تعتمد عليها في صفقة")

    return "\n".join(lines)
