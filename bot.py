# -*- coding: utf-8 -*-
"""
بوت أخبار الدهب والدولار 💛💵
================================
بوت تليجرام بسيط:
- بينشر تلقائياً الأخبار المهمة في قناتك (مترجمة عربي)
- بينبهك قبل الأخبار الاقتصادية المهمة بـ 30 دقيقة
- أوامر: /news /gold /calendar /price /id

شغّله:  python bot.py
"""
import asyncio
import html
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (Application, CommandHandler, ContextTypes)

import config
import state as db  # حفظ الحالة في JSON (شغال على Termux وعلى GitHub Actions)
import calendar_module
import news_module
import prices_module

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")


# ---------- أدوات مساعدة ----------
def channel_target():
    """يرجّع القناة اللي هينشر فيها (نص @اسم أو رقم)"""
    cid = str(config.CHANNEL_ID).strip()
    if not cid:
        return None
    return cid if cid.startswith("@") else int(cid)


async def send_html(context, chat_id, text):
    await context.bot.send_message(
        chat_id=chat_id, text=text,
        parse_mode=ParseMode.HTML,
    )


async def broadcast_news(context: ContextTypes.DEFAULT_TYPE):
    """النشر التلقائي: يجيب الأخبار المهمة وينشرها في القناة"""
    target = channel_target()
    if not target:
        log.warning("مش هينشر: اكتب CHANNEL_ID في config.py الأول")
        return
    try:
        ready = await asyncio.to_thread(news_module.get_fresh_news)
        if not ready:
            return
        log.info("هينشر %d خبر", len(ready))
        for r in ready:
            try:
                await send_html(context, target, r["message"])
                await asyncio.sleep(config.SEND_DELAY_SECONDS)
            except (BadRequest, Forbidden) as ex:
                log.error("مشكلة نشر: %s — اتأكد إن البوت أدمن في القناة", ex)
                break
    except Exception as ex:
        log.error("غلط في دورة الأخبار: %s", ex)


async def broadcast_alerts(context: ContextTypes.DEFAULT_TYPE):
    """تنبيه قبل الأخبار الاقتصادية المهمة"""
    target = channel_target()
    if not target:
        return
    try:
        due = await asyncio.to_thread(calendar_module.get_due_alerts)
        for ev, minutes_left, key in due:
            name = html.escape(calendar_module.event_name_ar(ev["title"]))
            time_str = ev["dt"].strftime("%I:%M %p")
            forecast = html.escape(ev["forecast"]) if ev["forecast"] else "—"
            previous = html.escape(ev["previous"]) if ev["previous"] else "—"
            msg = (
                "🚨 <b>تنبيه: خبر اقتصادي مهم قرب!</b>\n\n"
                f"🔴 <b>{name}</b>\n"
                f"🕐 هيصدر بعد <b>{minutes_left} دقيقة</b> — {time_str} بتوقيت القاهرة\n"
                f"📊 التأثير: عالي على الدولار والدهب\n"
                f"📈 المتوقع: {forecast} | السابق: {previous}\n\n"
                "⚠️ السوق ممكن يتحرك عنيف — خد بالك من صفقاتك والستوبات!"
            )
            try:
                await send_html(context, target, msg)
                db.mark_alert_sent(key)
                await asyncio.sleep(config.SEND_DELAY_SECONDS)
            except (BadRequest, Forbidden) as ex:
                log.error("مشكلة إرسال تنبيه: %s", ex)
    except Exception as ex:
        log.error("غلط في دورة التنبيهات: %s", ex)


# ---------- الأوامر ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً يا معلم 👋\n"
        "أنا بوت أخبار الاقتصاد والأسواق — متخصص في <b>الدهب 💛 والدولار 💵</b>\n\n"
        "<b>الأوامر:</b>\n"
        "/news — آخر الأخبار المهمة\n"
        "/gold — أخبار الدهب بس\n"
        "/calendar — الأخبار الاقتصادية الجاية\n"
        "/price — أسعار لحظية (دهب + DXY + دولار/جنيه)\n"
        "/id — اعرف رقم الجروب/القناة ده\n\n"
        "📣 وبنشر تلقائي في القناة المضبوطة في config.py\n"
        "🚨 وبنبهك قبل الأخبار المهمة بـ " + str(config.ALERT_BEFORE_MINUTES) + " دقيقة",
        parse_mode=ParseMode.HTML,
    )


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ لحظة... بجيب آخر الأخبار وأترجمها")
    try:
        ready = await asyncio.to_thread(news_module.get_fresh_news)
        if not ready:
            await update.message.reply_text("مفيش أخبار مهمة جديدة دلوقتي ✅ أنا أصلاً بنشرها تلقائي في القناة")
            return
        for r in ready[:5]:
            await update.message.reply_html(r["message"])
            await asyncio.sleep(1)
    except Exception as ex:
        log.error("أمر news فشل: %s", ex)
        await update.message.reply_text("حصلت مشكلة في جلب الأخبار — جرب تاني بعد شوية 🙏")


async def cmd_gold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ بجيب أخبار الدهب...")
    try:
        all_items = await asyncio.to_thread(news_module.fetch_all_sources)
        gold_items = [it for it in all_items if it["kind"] == "gold"][:5]
        if not gold_items:
            await update.message.reply_text("مفيش أخبار دهب جديدة دلوقتي 🟡")
            return
        for it in gold_items:
            title = await asyncio.to_thread(news_module.translate_to_arabic, it["title"])
            msg = news_module.format_news_message(it, title, "")
            await update.message.reply_html(msg)
            await asyncio.sleep(1)
    except Exception as ex:
        log.error("أمر gold فشل: %s", ex)
        await update.message.reply_text("حصلت مشكلة — جرب تاني بعد شوية 🙏")


async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ بجيب التقويم الاقتصادي...")
    events = await asyncio.to_thread(calendar_module.get_today_tomorrow_events)
    if events is None:
        await update.message.reply_text("مقدرت أوصل للتقويم دلوقتي — المصدر مشغول، جرب بعد شوية 🙏")
        return
    if not events:
        await update.message.reply_text("مفيش أخبار اقتصادية أمريكية مهمة النهاردة ولا بكرة ✅ استرح")
        return
    header = "📅 <b>الأخبار الاقتصادية الأمريكية الجاية</b>\n\n"
    body = "\n".join(calendar_module.format_event(e, show_day=True) for e in events[:10])
    await update.message.reply_html(header + body)


async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ بجيب الأسعار اللحظية...")
    msg = await asyncio.to_thread(prices_module.get_price_message)
    await update.message.reply_html(msg)


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.message.reply_text(
        f"🆔 رقم الشات ده: <code>{chat.id}</code>\n\n"
        "انسخ الرقم ده وحطه في config.py في سطر CHANNEL_ID\n"
        "(لو جروب: الرقم بيبدأ بـ -100)\n\n"
        "⚠️ متنساش تضيف البوت أدمن في القناة/الجروب عشان يقدر ينشر",
        parse_mode=ParseMode.HTML,
    )


# ---------- التشغيل ----------
def main():
    if not config.BOT_TOKEN.strip():
        print("=" * 50)
        print("❌ لسه مفيش توكن يا معلم!")
        print("1) افتح تليجرام وكلم @BotFather")
        print("2) ابعت /newbot واتبع الخطوات")
        print("3) انسخ التوكن وحطه في config.py في سطر BOT_TOKEN")
        print("4) شغّل تاني: python bot.py")
        print("=" * 50)
        return

    db.cleanup()
    app = Application.builder().token(config.BOT_TOKEN.strip()).build()

    # الأوامر
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_start))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("gold", cmd_gold))
    app.add_handler(CommandHandler("calendar", cmd_calendar))
    app.add_handler(CommandHandler("price", cmd_price))
    app.add_handler(CommandHandler("id", cmd_id))

    # النشر التلقائي: أخبار كل NEWS_CHECK_MINUTES + فحص التنبيهات كل CALENDAR_CHECK_MINUTES
    app.job_queue.run_repeating(
        broadcast_news, interval=config.NEWS_CHECK_MINUTES * 60, first=15)
    app.job_queue.run_repeating(
        broadcast_alerts, interval=config.CALENDAR_CHECK_MINUTES * 60, first=30)

    log.info("البوت اشتغل ✅ — يستنى رسايل...")
    print("✅ البوت اشتغل! سيبه شغال عشان ينشر الأخبار (اضغط Ctrl+C للإيقاف)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
