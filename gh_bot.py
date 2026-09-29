# -*- coding: utf-8 -*-
"""
بوت أخبار الدهب والدولار — نسخة GitHub Actions ⚡ (مجاني 24/7)
==============================================================
إزاي بيشتغل؟
- جي هب بيصحّي البوت كل 5 دقايق (إعداد .github/workflows/bot.yml)
- في كل تشغيل البوت بيسوّي 3 حاجات بسرعة:
  1) يرد على أوامر الناس (/news /gold /calendar /price ...)
  2) يبعت تنبيهات التقويم الاقتصادي القريبة (قبل الخبر المهم بـ 30 دقيقة)
  3) لو عدّت 10 دقايق من آخر فحص: يجيب الأخبار الجديدة وينشرها مترجمة
- الحالة (الأخبار المشوفة + كاش الترجمة) بتتخزن في data/state.json
  وبتترفع على برانش اسمه bot-state في نفس الريبو — عشان الأخبار
  ماتتنشرش تاني من أول وجديد مع كل تشغيل.

التوكن والقناة بيجوا من Repo Secrets:
  TELEGRAM_TOKEN = توكن البوت من @BotFather
  CHANNEL_ID     = @اسم_القناة أو رقمها
"""
import html
import logging
import os
import subprocess
import sys
import time

import config
import calendar_module
import news_module
import prices_module
import state
import telegram_api

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                    level=logging.INFO)
log = logging.getLogger("gh-bot")

STATE_BRANCH = "bot-state"   # البرانش اللي فيه ملف الحالة (كوميت واحد بس بيتحدّث)
ON_GITHUB = os.environ.get("GITHUB_ACTIONS") == "true"

HELP_TEXT = (
    "أهلاً يا معلم 👋\n"
    "أنا بوت أخبار الاقتصاد والأسواق — متخصص في <b>الدهب 💛 والدولار 💵</b>\n\n"
    "<b>الأوامر:</b>\n"
    "/news — آخر الأخبار المهمة\n"
    "/gold — أخبار الدهب بس\n"
    "/calendar — الأخبار الاقتصادية الجاية\n"
    "/price — أسعار لحظية (دهب + DXY + دولار/جنيه)\n"
    "/id — رقم الشات ده\n\n"
    "📣 وبنشر تلقائي في القناة\n"
    "🚨 وتبنيه قبل الأخبار المهمة بـ " + str(config.ALERT_BEFORE_MINUTES) + " دقيقة\n\n"
    "ℹ️ أنا بشتغل بنظام \"شغلة كل 5 دقايق\" — يعني ردّي على أوامرك ممكن يتأخر شوية (لحد 5 دقايق)"
)


# ---------- حفظ واسترجاع الحالة من جي هب ----------
def _run(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def restore_state():
    """يجيب آخر حالة محفوظة من برانش bot-state (لو موجودة)"""
    if not ON_GITHUB:
        state.load()
        return
    ls = _run("git", "ls-remote", "--exit-code", "--heads", "origin", STATE_BRANCH)
    if ls.returncode != 0 or not ls.stdout.strip():
        log.info("أول تشغيل على الريبو — هبدأ بحالة جديدة")
        state.load()
        return
    _run("git", "fetch", "--depth=1", "origin", STATE_BRANCH)
    co = _run("git", "checkout", "FETCH_HEAD", "--", "data/state.json")
    if co.returncode == 0 and os.path.exists("data/state.json"):
        log.info("استرجعت الحالة المحفوظة من آخر تشغيل ✅")
    else:
        log.warning("مقدرتش أسترجع الحالة (%s) — هبدأ جديدة (ممكن يتكرر خبر قديم مرة واحدة)",
                    co.stderr.strip()[:80])
    state.load()


def commit_state():
    """يرفع ملف الحالة على برانش bot-state.
    استخدمت أوامر git الداخلية (hash-object/mktree/commit-tree) عشان أعمل
    كوميت واحد بيتحدّث (amend-style) من غير ما ألخبط ملفات الكود —
    الريبو يفضل نضيف وتاريخ البرانش سطر واحد بس."""
    if not ON_GITHUB:
        return
    state.save()
    if not os.path.exists("data/state.json"):
        log.warning("مفيش ملف حالة أرفعه")
        return

    env = dict(os.environ,
               GIT_AUTHOR_NAME="github-actions[bot]",
               GIT_AUTHOR_EMAIL="41898282+github-actions[bot]@users.noreply.github.com",
               GIT_COMMITTER_NAME="github-actions[bot]",
               GIT_COMMITTER_EMAIL="41898282+github-actions[bot]@users.noreply.github.com")

    def git(*args, **kw):
        return _run("git", *args, env=env, **kw)  # بيضيف كلمة git لوحده

    # 1) هل البرانش موجود؟ نجيب آخر كوميت فيه (هيبقى الأب للكوميت الجديد)
    ls = git("ls-remote", "--exit-code", "--heads", "origin", STATE_BRANCH)
    parent = None
    if ls.returncode == 0 and ls.stdout.strip():
        parent = ls.stdout.split()[0]
        git("fetch", "--depth=1", "origin", STATE_BRANCH)  # لازم الكوميت يكون موجود محلياً

    # 2) ابنِ الشجرة: كوميت فيه ملف واحد بس (data/state.json)
    blob = git("hash-object", "-w", "data/state.json")
    blob_sha = blob.stdout.strip()
    if not blob_sha:
        log.error("فشل hash-object: %s", blob.stderr[:120])
        return
    inner = git("mktree", input=f"100644 blob {blob_sha}\tstate.json\n").stdout.strip()
    outer = git("mktree", input=f"040000 tree {inner}\tdata\n").stdout.strip()

    # 3) اعمل الكوميت (لو فيه أب = تحديث للكوميت القديم بدل تكويم جديدة كل مرة)
    args = ["commit-tree", outer, "-m", "bot state update (auto)"]
    if parent:
        args += ["-p", parent]
    result = git(*args)
    commit_sha = result.stdout.strip()
    if not commit_sha:
        log.error("فشل commit-tree: %s", result.stderr[:120])
        return

    # 4) ارفع بقوة (البرانش بتاعنا احنا — الـ force آمن هنا)
    push = git("push", "--force", "origin", f"{commit_sha}:refs/heads/{STATE_BRANCH}")
    if push.returncode == 0:
        log.info("الحالة اتحفظت على برانش %s ✅", STATE_BRANCH)
    else:
        log.error("فشل رفع الحالة: %s", push.stderr[:200])


# ---------- أدوات ----------
def channel_target():
    """يرجّع القناة اللي هينشر فيها (نص @اسم أو رقم)"""
    cid = str(config.CHANNEL_ID).strip()
    if not cid:
        return None
    if cid.startswith("@"):
        return cid
    return int(cid) if cid.lstrip("-").isdigit() else cid


# ---------- رد على الأوامر ----------
def reply_news(tg, chat_id):
    tg.send_html(chat_id, "⏳ لحظة... بجيب آخر الأخبار وأترجمها")
    data = news_module.get_fresh_news()
    ready = data["ready"]
    if not ready:
        tg.send_html(chat_id, "مفيش أخبار مهمة جديدة دلوقتي ✅ أنا أصلاً بنشرها تلقائي في القناة")
        return
    for r in ready[:5]:
        tg.send_html(chat_id, r["message"])
        time.sleep(1)


def reply_gold(tg, chat_id):
    tg.send_html(chat_id, "⏳ بجيب أخبار الدهب...")
    all_items = news_module.fetch_all_sources()
    gold_items = [it for it in all_items if it["kind"] == "gold"][:5]
    if not gold_items:
        tg.send_html(chat_id, "مفيش أخبار دهب جديدة دلوقتي 🟡")
        return
    for it in gold_items:
        title = news_module.translate_to_arabic(it["title"])
        tg.send_html(chat_id, news_module.format_news_message(it, title, ""))
        time.sleep(1)


def reply_calendar(tg, chat_id):
    tg.send_html(chat_id, "⏳ بجيب التقويم الاقتصادي...")
    events = calendar_module.get_today_tomorrow_events()
    if events is None:
        tg.send_html(chat_id, "مقدرت أوصل للتقويم دلوقتي — المصدر مشغول، جرب بعد شوية 🙏")
        return
    if not events:
        tg.send_html(chat_id, "مفيش أخبار اقتصادية أمريكية مهمة النهاردة ولا بكرة ✅ استرح")
        return
    header = "📅 <b>الأخبار الاقتصادية الأمريكية الجاية</b>\n\n"
    body = "\n".join(calendar_module.format_event(e, show_day=True) for e in events[:10])
    tg.send_html(chat_id, header + body)


def reply_price(tg, chat_id):
    tg.send_html(chat_id, "⏳ بجيب الأسعار اللحظية...")
    tg.send_html(chat_id, prices_module.get_price_message())


def handle_commands(tg):
    """بيقرا رسايل الأوامر اللي وصلت من آخر تشغيل ويرد عليها"""
    updates = tg.get_updates(state.get_last_update_id() + 1)
    if not updates:
        return
    log.info("وصلت %d رسالة/أمر", len(updates))
    for update in updates:
        state.set_last_update_id(update.get("update_id"))
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        if chat_id is None or not text:
            continue
        command = text.split()[0].split("@")[0].lower()
        log.info("أمر جديد: %s (من %s)", command, chat_id)
        try:
            if command in ("/start", "/help"):
                tg.send_html(chat_id, HELP_TEXT)
            elif command == "/news":
                reply_news(tg, chat_id)
            elif command == "/gold":
                reply_gold(tg, chat_id)
            elif command == "/calendar":
                reply_calendar(tg, chat_id)
            elif command == "/price":
                reply_price(tg, chat_id)
            elif command == "/id":
                tg.send_html(
                    chat_id,
                    f"🆔 رقم الشات ده: <code>{chat_id}</code>\n\n"
                    "لو دي القناة بتاعتك: انسخ الرقم ده وحطه في Secret باسم CHANNEL_ID\n"
                    "(الرقم السالب ده عادي — ده رقم جروب/قناة)\n"
                    "⚠️ متنساش تضيف البوت أدمن في القناة عشان يقدر ينشر",
                )
            else:
                tg.send_html(chat_id, "مش فاهم الأمر ده 😅 جرب /help")
        except Exception as ex:
            log.warning("فشل تنفيذ أمر %s: %s", command, ex)
        time.sleep(0.5)


# ---------- النشر التلقائي ----------
def send_due_alerts(tg):
    """تنبيه قبل الأخبار الاقتصادية المهمة (بتوقيت القاهرة)"""
    target = channel_target()
    if not target:
        log.warning("مفيش CHANNEL_ID — مش هبعت تنبيهات")
        return
    due = calendar_module.get_due_alerts()
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
        if tg.send_html(target, msg):
            state.mark_alert_sent(key)
            log.info("بعت تنبيه: %s (بعد %d دقيقة)", ev["title"], minutes_left)
            time.sleep(config.SEND_DELAY_SECONDS)
        else:
            log.error("فشل إرسال تنبيه — اتأكد إن البوت أدمن في القناة")
            break


def broadcast_news_if_due(tg):
    """لو عدّت NEWS_CHECK_MINUTES من آخر فحص: يجيب الأخبار الجديدة وينشرها"""
    target = channel_target()
    if not target:
        log.warning("مفيش CHANNEL_ID — مش هينشر أخبار")
        return
    elapsed = time.time() - state.get_last_news_check()
    if elapsed < config.NEWS_CHECK_MINUTES * 60:
        log.info("لسه بدري على الأخبار (آخر فحص من %.0f دقيقة)", elapsed / 60)
        return
    state.set_last_news_check()  # سجّل الفحص قبل الجلب حتى لو حصل مشكلة متيجيش كل 5 دقايق
    data = news_module.get_fresh_news()
    ready = data["ready"]
    if not ready:
        # صمام منع السكوت: لو مفيش خبر اتنشر من SILENCE_VALVE_MINUTES،
        # ابعت أقوى خبر جديد موجود (له علاقة أساسية على الأقل score >= 1)
        best = data.get("best_below")
        idle = time.time() - state.get_last_post_time()
        if best and idle >= config.SILENCE_VALVE_MINUTES * 60:
            score, item = best
            log.info("صمام منع السكوت: مفيش نشر من %.0f دقيقة — هبعت أقوى خبر جديد (نقاط %d)",
                     idle / 60, score)
            title = news_module.translate_to_arabic(item["title"])
            summary = news_module.translate_to_arabic(item["summary"]) if item["summary"] else ""
            if tg.send_html(target, news_module.format_news_message(item, title, summary)):
                state.set_last_post_time()
                log.info("صمام السكوت بعت خبر: %s", item["title"][:60])
            return
        log.info("مفيش أخبار مهمة جديدة")
        return
    log.info("هينشر %d خبر", len(ready))
    for r in ready:
        if tg.send_html(target, r["message"]):
            state.set_last_post_time()
            time.sleep(config.SEND_DELAY_SECONDS)
        else:
            log.error("فشل النشر — اتأكد إن البوت أدمن في القناة")
            break


# ---------- التشغيل ----------
def main():
    if not config.BOT_TOKEN.strip():
        print("=" * 56)
        print("❌ مفيش توكن يا معلم!")
        print("على GitHub: حط Secret باسم TELEGRAM_TOKEN فيه توكن البوت")
        print("و Secret باسم CHANNEL_ID فيه @اسم القناة أو رقمها")
        print("(Repo → Settings → Secrets and variables → Actions → New repository secret)")
        print("=" * 56)
        sys.exit(1)

    log.info("=== دورة جديدة بادئة ===")
    restore_state()

    tg = telegram_api.TelegramClient(config.BOT_TOKEN)

    log.info("1/3 — رد على الأوامر...")
    handle_commands(tg)

    log.info("2/3 — فحص تنبيهات التقويم...")
    send_due_alerts(tg)

    log.info("3/3 — فحص الأخبار الجديدة...")
    broadcast_news_if_due(tg)

    state.cleanup()
    commit_state()
    log.info("الدورة خلصت ✅")


if __name__ == "__main__":
    main()
