# -*- coding: utf-8 -*-
"""اتصال مباشر بـ Telegram Bot API عن طريق requests — من غير مكتبات خارجية
==========================================================================
مخصص لنسخة GitHub Actions: البوت بيفتح، ينفذ شغلته، ويقفل في نفس الدقيقة،
فمش محتاجين polling مستمر ولا مكتبة python-telegram-bot.
"""
import logging
import re

import requests

log = logging.getLogger("tg")

API_BASE = "https://api.telegram.org/bot{token}/{method}"


def strip_html(text: str) -> str:
    """يشيل وسوم HTML من الرسالة (نسخة احتياطية لو الترميز اترد)"""
    text = re.sub(r"</?(b|i|u|s|code|pre|a)[^>]*>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text)


class TelegramClient:
    def __init__(self, token: str):
        self.token = token.strip()
        self.session = requests.Session()

    def call(self, method: str, **params):
        """نداء API واحد — يرجّع النتيجة أو None لو فشل (من غير ما يقفل البرنامج)"""
        url = API_BASE.format(token=self.token, method=method)
        try:
            resp = self.session.post(url, json=params, timeout=25)
            data = resp.json()
            if data.get("ok"):
                return data.get("result")
            log.warning("تليجرام رد بخطأ في %s: %s", method, data.get("description"))
            return None
        except Exception as ex:
            log.warning("فشل نداء %s: %s", method, ex)
            return None

    @staticmethod
    def _keyboard(button=None, buttons=None):
        """بناء inline keyboard من زر واحد أو صفوف أزرار
        button  = dict {"text", "url" أو "callback_data"}
        buttons = list من الصفوف، كل صف list من الأزرار"""
        if buttons:
            return {"inline_keyboard": buttons}
        if button:
            return {"inline_keyboard": [[button]]}
        return None

    def send_html(self, chat_id, text: str, button=None, buttons=None) -> bool:
        """إرسال رسالة HTML (مع أزرار اختيارية) — لو الترميز اترفض يحاول نسخة نص عادي"""
        markup = self._keyboard(button, buttons)
        params = dict(chat_id=chat_id, text=text[:4096], parse_mode="HTML",
                      disable_web_page_preview=True)
        if markup:
            params["reply_markup"] = markup
        result = self.call("sendMessage", **params)
        if result is not None:
            return True
        # محاولة أخيرة: من غير أي تنسيق (لو الخبر فيه حروف غريبة كسرت HTML)
        fallback = dict(chat_id=chat_id, text=strip_html(text)[:4096],
                        disable_web_page_preview=True)
        if markup:
            fallback["reply_markup"] = markup
        return self.call("sendMessage", **fallback) is not None

    def answer_callback(self, callback_query_id, text: str = "") -> bool:
        """رد على ضغطة الزر (يشيل علامة التحميل من فوق الزر)"""
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text[:190]
        return self.call("answerCallbackQuery", **params) is not None

    def get_updates(self, offset: int):
        """جلب الرسايل وضغطات الأزرار الجديدة اللي وصلت من آخر مرة"""
        return self.call("getUpdates", offset=offset, limit=20, timeout=0,
                         allowed_updates=["message", "callback_query"]) or []
