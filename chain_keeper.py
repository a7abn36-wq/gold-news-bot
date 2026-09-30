#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
حارس السلسلة الذكي ⚙️ — القلب النابض لتشغيل البوت 24/7
========================================================
مهمته: يضمن إن الدورة الجاية تحصل مهما حصل، ويعرف يعالج نفسه لوحده.

المشاكل اللي كانت ممكن تقتل النظام القديم (وده سبب السكوت اللي حصل):
  1) لو نداء الديسباتش فشل مرة واحدة (نت أو ظرف عابر) → السلسلة كانت بتموت
     للأبد لأن محاولة واحدة بس بدون أي إعادة محاولة.
  2) لو تشغيل اتعلق في حالته queued/in_progress → الحارس القديم كان بيحسبه
     "شغال" للأبد والدورة الجديدة عمرها ما بتبدأ (Deadlock كامل).

الحل الجذري — منطق "آخر واحد ياخد العصا" (تسليم تتابعي):
  - بنبص على الوقت مش على الحالة: أي تشغيل اتولد بعد تشغيلنا يعتبر هو
    المسؤول عن تسييق الدورة الجاية، واحنا نسلمه ونخرج.
  - التشغيل المتعلق القديم مش بيقفل حاجة خالص — لأنه مش "أحدث" مننا.
  - لو مفيش حد أحدث مننا = إحنا آخر واحد في السلسلة = نستنى الاستراحة
    وبعدين ندوّر الدورة الجاية بإعادة محاولة 5 مرات متباعدة.
  - لو فشل فحص الـ API نفسه: بنحاول ندوّر برضه (group الـ concurrency
    بيفضل السلسلة واحدة، فمفيش خطر من محاولة زيادة على الحاجة).
"""
import os
import sys
import time
from datetime import datetime, timezone
from urllib import request as urlreq
from urllib.error import HTTPError, URLError

GH_PAT = os.environ.get("GH_PAT", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
RUN_ID = int(os.environ.get("GITHUB_RUN_ID", "0") or 0)

API_RUNS = f"https://api.github.com/repos/{REPO}/actions/runs?per_page=40"
API_DISPATCH = f"https://api.github.com/repos/{REPO}/actions/workflows/bot.yml/dispatches"

REST_SECONDS = 240          # الاستراحة قبل الدورة الجاية (إجمالي الكادن ~4.5-5 دقايق)
TOLERANCE_SECONDS = 45      # تسامح مقارنة الأوقات (تشغيلين في نفس اللحظة)
ATTEMPTS = 5                # عدد محاولات الديسباتش
BACKOFF = [20, 30, 45, 60]  # الانتظار بين المحاولات


def _gh(url: str, method: str = "GET"):
    """نداء GitHub API — بيرجع (status, body_bytes) من غير ما يرمي استثناء"""
    req = urlreq.Request(url, method=method, headers={
        "Authorization": f"token {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "gold-news-bot-chain",
    })
    if method == "POST":
        req.add_header("Content-Type", "application/json")
        req.data = b'{"ref":"main"}'
    try:
        with urlreq.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except HTTPError as ex:
        return ex.code, ex.read() if ex.fp else b""
    except (URLError, OSError) as ex:
        print(f"⚠️ مشكلة شبكة في {method} {url}: {ex}")
        return 0, b""


def _parse_ts(value: str):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def who_is_newest():
    """يرجّع (أنا أحدث؟, عدد التشغيلات الأحدث) — أو None لو الفحص فشل"""
    status, body = _gh(API_RUNS)
    if status != 200:
        print(f"⚠️ فشل جلب قائمة التشغيلات (HTTP {status})")
        return None
    try:
        runs = __import__("json").loads(body.decode("utf-8")).get("workflow_runs", [])
    except Exception as ex:
        print(f"⚠️ فشل تحليل استجابة التشغيلات: {ex}")
        return None

    my_ts = 0.0
    newer = 0
    for r in runs:
        if int(r.get("id", 0)) == RUN_ID:
            my_ts = _parse_ts(r.get("created_at", ""))
            break
    if not my_ts:
        # مش لاقي نفسنا في القائمة (نادر) — نفترض إنا الأحدث
        print("ℹ️ مش لاقي تشغيلي في القائمة — هعتبر نفسي الأحدث")
        return True, 0

    for r in runs:
        rid = int(r.get("id", 0))
        if rid == RUN_ID:
            continue
        rts = _parse_ts(r.get("created_at", ""))
        if not rts:
            continue
        if rts > my_ts + TOLERANCE_SECONDS or (
                abs(rts - my_ts) <= TOLERANCE_SECONDS and rid > RUN_ID):
            newer += 1
    return newer == 0, newer


def dispatch_once() -> bool:
    """محاولة واحدة لتسييق الدورة الجاية"""
    status, body = _gh(API_DISPATCH, method="POST")
    detail = body.decode("utf-8", errors="replace")[:200] if body else ""
    if status in (200, 202, 204):
        return True
    if status in (401, 403):
        print(f"❌ الديسباتش اترفض (HTTP {status}) — التوكن GH_PAT مرفوض أو خلصت صلاحيته!")
        print("   الحل: حدّث التوكن من صفحة GitHub → Settings → Developer settings")
        print("   (Update token يفضل نفس القيمة — أو ابعت توكن جديد لتحديث السِكرت)")
    elif status == 422:
        print(f"❌ الديسباتش اترفض (HTTP 422) — تفاصيل: {detail}")
    else:
        print(f"⚠️ الديسباتش فشل (HTTP {status}) {detail}")
    return False


def main():
    if not GH_PAT or not REPO:
        print("❌ مفيش GH_PAT أو GITHUB_REPOSITORY — الحارس مش هيقدر يسييق السلسلة")
        sys.exit(1)

    print(f"⚙️ حارس السلسلة اشتغل (تشغيل #{RUN_ID})")

    # 1) مين آخر واحد؟ لو فيه تشغيل أحدث منا فهو اللي هياخد العصا
    newest = who_is_newest()
    if newest is None:
        # الفحص فشل — بنميل لأمان الشغل (نحاول ندوّر) والـ concurrency بيحمينا
        print("🔄 الفحص فشل — هكمل كمسؤول عن الدورة الجاية (ناحية الأمان)")
        newest = (True, 0)
    am_newest, newer_count = newest
    if not am_newest:
        print(f"✅ فيه {newer_count} تشغيل أحدث منا — هو اللي هيسيق الدورة الجاية. سلام!")
        sys.exit(0)

    # 2) إحنا آخر واحد — استراحة وبعدين نسييق
    print(f"😴 إحنا آخر واحد في السلسلة — استراحة {REST_SECONDS} ثانية...")
    time.sleep(REST_SECONDS)

    # 3) إعادة فحص بعد الاستراحة (ممكن حد أحدث ظهر أثناء النوم)
    newest = who_is_newest()
    if newest and not newest[0]:
        print(f"✅ ظهر {newest[1]} تشغيل أحدث أثناء الاستراحة — هيسيق الدورة بدالنا. سلام!")
        sys.exit(0)

    # 4) تسييق الدورة الجاية بمحاولات متباعدة
    for attempt in range(1, ATTEMPTS + 1):
        print(f"🔁 محاولة تسييق الدورة {attempt}/{ATTEMPTS}...")
        if dispatch_once():
            print(f"✅ الدورة الجاية انطلقت (نجحت من المحاولة {attempt})")
            sys.exit(0)
        if attempt < ATTEMPTS:
            wait = BACKOFF[min(attempt - 1, len(BACKOFF) - 1)]
            print(f"⏳ هجرب تاني بعد {wait} ثانية...")
            time.sleep(wait)

    print("❌ كل المحاولات فشلت — السلسلة وقفت ومحتاجة تدخل يدوي (Actions → Run workflow)")
    sys.exit(1)


if __name__ == "__main__":
    main()
