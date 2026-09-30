# -*- coding: utf-8 -*-
"""وحدة الأسعار الشاملة 💰
=========================
الدهب + الفضة + النفط WTI/برنت + بيتكوين + مؤشر الدولار DXY
+ يورو/دولار + استرليني/دولار + الدولار/الجنيه + جرام الدهب والفضة في مصر

كل المصادر مجانية ومن غير مفاتيح، ولو واحد وقع البوت يكمل بالباقي عادي:
- الدهب والفضة: api.gold-api.com
- بيتكوين: Coinbase (واحتياطي CoinGecko)
- النفط: Yahoo Finance chart API (query2 — اللي بيسمح بآيبيهات السيرفرات)
- العملات: open.er-api.com
"""
import html
import logging
from datetime import datetime

import requests

import config

log = logging.getLogger("prices")

GOLD_API = "https://api.gold-api.com/price/XAU"
SILVER_API = "https://api.gold-api.com/price/XAG"
RATES_API = "https://open.er-api.com/v6/latest/USD"
BTC_API = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
BTC_API_FALLBACK = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
OIL_WTI_URL = "https://query2.finance.yahoo.com/v8/finance/chart/CL=F?interval=1d&range=5d"
OIL_BRENT_URL = "https://query2.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=5d"

# معادلة حساب مؤشر الدولار من أسعار العملات (أوزان السلة الرسمية)
DXY_CONST = 50.14348112

# فاصل التنسيق الفخم للنشرات
DIV = "━━━━━━━━━━━━━━━━━━"


def _get(url: str, timeout: int = 15):
    return requests.get(url, headers={"User-Agent": config.USER_AGENT}, timeout=timeout)


# ---------- الجلب ----------
def get_gold():
    """سعر أونصة الدهب لحظياً"""
    try:
        data = _get(GOLD_API).json()
        return float(data["price"]), data.get("updatedAtReadable", "")
    except Exception as ex:
        log.warning("فشل جلب سعر الدهب: %s", ex)
        return None, None


def get_silver():
    """سعر أونصة الفضة لحظياً"""
    try:
        data = _get(SILVER_API).json()
        return float(data["price"])
    except Exception as ex:
        log.warning("فشل جلب سعر الفضة: %s", ex)
        return None


def get_btc():
    """سعر البيتكوين بالدولار (Coinbase ولو وقعت CoinGecko)"""
    try:
        data = _get(BTC_API).json()
        return float(data["data"]["amount"])
    except Exception as ex:
        log.warning("كوين بيس فشلت: %s — هجرب كوين جيكو", ex)
    try:
        data = _get(BTC_API_FALLBACK).json()
        return float(data["bitcoin"]["usd"])
    except Exception as ex:
        log.warning("فشل جلب سعر البيتكوين: %s", ex)
        return None


def get_oil(url: str = OIL_WTI_URL):
    """سعر النفط من ياهو — بيرجع (السعر، نسبة التغير %) أو (None, None)
    ملاحظة: ياهو بيرفض UA الموبايل من سيرفرات (429) فلازم UA ديسكتوب"""
    try:
        r = requests.get(url, headers={"User-Agent": config.DESKTOP_UA}, timeout=20)
        meta = r.json()["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        change = meta.get("regularMarketChangePercent")
        change = float(change) if change is not None else None
        return price, change
    except Exception as ex:
        log.warning("فشل جلب سعر النفط: %s", ex)
        return None, None


def get_rates():
    """أسعار العملات مقابل الدولار"""
    try:
        return _get(RATES_API).json().get("rates", {})
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


def _now_cairo() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(config.TIMEZONE)).strftime("%I:%M %p")
    except Exception:
        return datetime.now().strftime("%I:%M %p")


def _arrow(change: float) -> str:
    """سهم الاتجاه من نسبة التغير"""
    if change is None:
        return ""
    if change > 0:
        return f" 📈 <i>+{change:.2f}%</i>"
    if change < 0:
        return f" 📉 <i>{change:.2f}%</i>"
    return " ⚖️"


# ---------- لوحة الأسعار الكاملة ----------
def get_price_message() -> str:
    """النشرة الكاملة الفخمة لأمر /price — شكل نشرة اقتصادية محترفة"""
    gold, _gold_time = get_gold()
    silver = get_silver()
    btc = get_btc()
    wti, wti_ch = get_oil(OIL_WTI_URL)
    brent, brent_ch = get_oil(OIL_BRENT_URL)
    rates = get_rates()
    dxy = compute_dxy(rates)
    usdegp = rates.get("EGP")

    lines = [f"💰 <b>نشرة الأسعار اللحظية</b>", DIV]

    if gold:
        lines.append(f"🟡 الدهب (الأونصة): <b>{gold:,.2f}$</b>")
    else:
        lines.append("🟡 الدهب: مؤقتاً غير متاح")
    if silver:
        lines.append(f"🥈 الفضة (الأونصة): <b>{silver:,.2f}$</b>")
    if wti:
        lines.append(f"🛢️ النفط الأمريكي WTI: <b>{wti:,.2f}$</b>{_arrow(wti_ch)}")
    if brent:
        lines.append(f"🛢️ نفط برنت: <b>{brent:,.2f}$</b>{_arrow(brent_ch)}")
    if btc:
        lines.append(f"₿ بيتكوين: <b>{btc:,.0f}$</b>")

    if dxy:
        lines.append(DIV)
        lines.append(f"💵 مؤشر الدولار DXY: <b>{dxy}</b> (تقريبي)")
    if rates.get("EUR"):
        lines.append(f"💶 يورو/دولار: <b>{1 / rates['EUR']:.4f}</b>")
    if rates.get("GBP"):
        lines.append(f"💷 استرليني/دولار: <b>{1 / rates['GBP']:.4f}</b>")
    if usdegp:
        lines.append(f"🇪🇬 الدولار/الجنيه: <b>{usdegp:.2f}</b>")

    if gold and usdegp:
        gram_egp = (gold / 31.1035) * usdegp
        lines.append(f"⚖️ جرام دهب 24 في مصر: <b>~{gram_egp:,.0f} جنيه</b>")
    if silver and usdegp:
        sg_egp = (silver / 31.1035) * usdegp
        lines.append(f"⚪️ جرام فضة في مصر: <b>~{sg_egp:,.0f} جنيه</b>")

    lines.append(DIV)
    lines.append(f"🕐 {_now_cairo()} بتوقيت القاهرة")
    lines.append("⚠️ للمعرفة فقط — اتأكد من منصتك قبل صفقة")
    return "\n".join(lines)


# ---------- كروت الأسعار المفردة ----------
def _card(header: str, rows: list, note: str = "") -> str:
    """قالب الكارت الفخم لأمر سعر واحد"""
    out = [header, DIV]
    out += rows
    if note:
        out.append("")
        out.append(f"💡 {note}")
    out.append(DIV)
    out.append(f"🕐 {_now_cairo()} بتوقيت القاهرة")
    return "\n".join(out)


def get_silver_message() -> str:
    silver = get_silver()
    if not silver:
        return "🥈 الفضة: مش قادر أجيب السعر دلوقتي — جرب بعد شوية 🙏"
    rows = [f"🥈 الفضة (الأونصة): <b>{silver:,.2f}$</b>"]
    note = ""
    rates = get_rates()
    usdegp = rates.get("EGP")
    if usdegp:
        sg_egp = (silver / 31.1035) * usdegp
        rows.append(f"🇪🇬 جرام الفضة في مصر: <b>~{sg_egp:,.0f} جنيه</b>")
        note = "الفضة بتتحرك مع الدهب — لو الدهب طار هيطير معاه"
    return _card("🥈 <b>سعر الفضة اللحظي</b>", rows, note)


def get_oil_message() -> str:
    wti, wti_ch = get_oil(OIL_WTI_URL)
    brent, brent_ch = get_oil(OIL_BRENT_URL)
    if not wti and not brent:
        return "🛢️ النفط: مش قادر أجيب السعر دلوقتي — جرب بعد شوية 🙏"
    rows = []
    if wti:
        rows.append(f"🛢️ النفط الأمريكي WTI: <b>{wti:,.2f}$</b>{_arrow(wti_ch)}")
    if brent:
        rows.append(f"🛢️ نفط برنت: <b>{brent:,.2f}$</b>{_arrow(brent_ch)}")
    return _card("⛽ <b>أسعار النفط اللحظية</b>", rows,
                 "النفط بيحرك الدولار والتضخم — وده بيرجع يتحرك الدهب")


def get_btc_message() -> str:
    btc = get_btc()
    if not btc:
        return "₿ بيتكوين: مش قادر أجيب السعر دلوقتي — جرب بعد شوية 🙏"
    rows = [f"₿ بيتكوين: <b>{btc:,.0f}$</b>"]
    rates = get_rates()
    usdegp = rates.get("EGP")
    if usdegp:
        rows.append(f"🇪🇬 بالجنيه المصري: <b>~{btc * usdegp / 1_000_000:,.2f} مليون جنيه</b>")
    return _card("🪙 <b>سعر البيتكوين</b>", rows,
                 "العملات الرقمية عالية التقلب — خد بالك يا صديقي")


def get_eur_message() -> str:
    rates = get_rates()
    if not rates.get("EUR"):
        return "💶 العملات: مش قادر أجيب الأسعار دلوقتي — جرب بعد شوية 🙏"
    rows = [f"💶 يورو/دولار: <b>{1 / rates['EUR']:.4f}</b>"]
    if rates.get("GBP"):
        rows.append(f"💷 استرليني/دولار: <b>{1 / rates['GBP']:.4f}</b>")
    usdegp = rates.get("EGP")
    if usdegp:
        rows.append(f"🇪🇬 الدولار/الجنيه: <b>{usdegp:.2f}</b>")
    return _card("💱 <b>أزواج العملات الرئيسية</b>", rows,
                 "قوة الدولار هي اللي بتحرك الدهب عكسياً في الغالب")
