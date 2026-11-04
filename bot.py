# -*- coding: utf-8 -*-
"""
بوت تلجرام لاستماع وتحميل تلاوات القرآن الكريم.

يعتمد البوت على الواجهة الرسمية لموقع mp3quran.net (الإصدار الثالث)
لجلب قائمة القراء وقائمة السور، ثم إرسال ملف الصوت الخاص بكل سورة.

التثبيت:
    pip install -r requirements.txt

التشغيل:
    1. أنشئ ملف .env بجانب bot.py وضع فيه سطراً بالصيغة:
           BOT_TOKEN=توكن_البوت_الخاص_بك
       (يمكن نسخ القيمة من @BotFather، ويُفضّل عدم مشاركة الملف .env مع أي جهة).
    2. نفّذ الأمر: python bot.py
"""

import os
import sys

import requests
import telebot
from dotenv import load_dotenv
from flask import Flask, request
from telebot import types

# تحميل المتغيّرات من ملف .env (إن وُجد) دون كتابة التوكن داخل الكود
load_dotenv()

# قراءة التوكن من متغيّر البيئة وإيقاف التشغيل إن لم يكن مضبوطاً
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    sys.exit("خطأ: لم يتم ضبط BOT_TOKEN. أنشئ ملف .env وضع فيه BOT_TOKEN=...")

# إعدادات الواجهة
API_BASE_URL = "https://mp3quran.net/api/v3"
LANGUAGE = "ar"
RECITERS_PER_PAGE = 10
SURAHS_PER_PAGE = 12

bot = telebot.TeleBot(BOT_TOKEN)

# تخزين مؤقت لتقليل عدد الطلبات على الواجهة
_reciters_cache = None
_surahs_cache = None


def get_reciters():
    """جلب قائمة القراء من الواجهة مرّة واحدة وتخزينها مؤقتاً."""
    global _reciters_cache
    if _reciters_cache is None:
        response = requests.get(
            f"{API_BASE_URL}/reciters",
            params={"language": LANGUAGE},
            timeout=15,
        )
        response.raise_for_status()
        _reciters_cache = response.json().get("reciters", [])
    return _reciters_cache


def get_surahs():
    """جلب قائمة السور كقاموس {رقم السورة: اسم السورة} مع التخزين المؤقت."""
    global _surahs_cache
    if _surahs_cache is None:
        response = requests.get(
            f"{API_BASE_URL}/suwar",
            params={"language": LANGUAGE},
            timeout=15,
        )
        response.raise_for_status()
        _surahs_cache = {
            surah["id"]: surah["name"]
            for surah in response.json().get("suwar", [])
        }
    return _surahs_cache


def get_main_moshaf(reciter):
    """إرجاع المصحف الأول المتاح للقارئ (يحتوي على رابط السيرفر وقائمة السور)."""
    moshafs = reciter.get("moshaf", [])
    return moshafs[0] if moshafs else None


def build_reciters_keyboard(page):
    """بناء لوحة أزرار القراء مع أزرار التنقل بين الصفحات."""
    reciters = get_reciters()
    total_pages = max(1, (len(reciters) + RECITERS_PER_PAGE - 1) // RECITERS_PER_PAGE)
    start = page * RECITERS_PER_PAGE
    page_items = reciters[start:start + RECITERS_PER_PAGE]

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            text=reciter["name"],
            callback_data=f"rec|{start + index}|{page}",
        )
        for index, reciter in enumerate(page_items)
    ]
    if buttons:
        keyboard.add(*buttons)

    navigation = []
    if page > 0:
        navigation.append(
            types.InlineKeyboardButton(text="⬅️ السابق", callback_data=f"recpage|{page - 1}")
        )
    navigation.append(
        types.InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        navigation.append(
            types.InlineKeyboardButton(text="التالي ➡️", callback_data=f"recpage|{page + 1}")
        )
    keyboard.row(*navigation)
    return keyboard


def build_surahs_keyboard(reciter_index, page):
    """بناء لوحة أزرار سور قارئ محدّد مع التنقل بين الصفحات."""
    reciter = get_reciters()[reciter_index]
    moshaf = get_main_moshaf(reciter)
    surah_ids = [int(item) for item in moshaf["surah_list"].split(",") if item]
    surah_names = get_surahs()

    total_pages = max(1, (len(surah_ids) + SURAHS_PER_PAGE - 1) // SURAHS_PER_PAGE)
    start = page * SURAHS_PER_PAGE
    page_items = surah_ids[start:start + SURAHS_PER_PAGE]

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(
            text=surah_names.get(surah_id, f"سورة {surah_id}"),
            callback_data=f"surah|{reciter_index}|{surah_id}",
        )
        for surah_id in page_items
    ]
    if buttons:
        keyboard.add(*buttons)

    navigation = []
    if page > 0:
        navigation.append(
            types.InlineKeyboardButton(
                text="⬅️ السابق", callback_data=f"surpage|{reciter_index}|{page - 1}"
            )
        )
    navigation.append(
        types.InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        navigation.append(
            types.InlineKeyboardButton(
                text="التالي ➡️", callback_data=f"surpage|{reciter_index}|{page + 1}"
            )
        )
    keyboard.row(*navigation)
    keyboard.row(
        types.InlineKeyboardButton(text="🔙 قائمة القراء", callback_data="recpage|0")
    )
    return keyboard


@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    """الرد على الأمرين /start و /help بعرض قائمة القراء."""
    try:
        keyboard = build_reciters_keyboard(0)
        bot.send_message(
            message.chat.id,
            "أهلاً بك في بوت القرآن الكريم 🕌\n\n"
            "اختر القارئ الذي تريد الاستماع إليه:",
            reply_markup=keyboard,
        )
    except requests.RequestException:
        bot.send_message(message.chat.id, "تعذّر الاتصال بخدمة mp3quran.net، حاول لاحقاً.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("recpage|"))
def handle_reciters_page(call):
    """التنقل بين صفحات قائمة القراء."""
    page = int(call.data.split("|")[1])
    bot.edit_message_text(
        "اختر القارئ الذي تريد الاستماع إليه:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=build_reciters_keyboard(page),
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("rec|"))
def handle_reciter_selected(call):
    """عرض سور القارئ المختار."""
    _, reciter_index, _page = call.data.split("|")
    reciter_index = int(reciter_index)
    reciter = get_reciters()[reciter_index]

    bot.edit_message_text(
        f"القارئ: {reciter['name']}\n\nاختر السورة:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=build_surahs_keyboard(reciter_index, 0),
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("surpage|"))
def handle_surahs_page(call):
    """التنقل بين صفحات سور القارئ."""
    _, reciter_index, page = call.data.split("|")
    reciter_index = int(reciter_index)
    page = int(page)
    reciter = get_reciters()[reciter_index]

    bot.edit_message_text(
        f"القارئ: {reciter['name']}\n\nاختر السورة:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=build_surahs_keyboard(reciter_index, page),
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("surah|"))
def handle_surah_selected(call):
    """إرسال ملف الصوت الخاص بالسورة المختارة."""
    _, reciter_index, surah_id = call.data.split("|")
    reciter_index = int(reciter_index)
    surah_id = int(surah_id)

    reciter = get_reciters()[reciter_index]
    moshaf = get_main_moshaf(reciter)
    surah_name = get_surahs().get(surah_id, f"سورة {surah_id}")

    server = moshaf["server"]
    if not server.endswith("/"):
        server += "/"
    audio_url = f"{server}{surah_id:03d}.mp3"
    caption = f"{surah_name} - {reciter['name']}"

    bot.answer_callback_query(call.id, "جارٍ إرسال التلاوة...")
    bot.send_audio(
        call.message.chat.id,
        audio_url,
        caption=caption,
    )


@bot.callback_query_handler(func=lambda call: call.data == "noop")
def handle_noop(call):
    """زر عرض رقم الصفحة الحالية (بدون إجراء)."""
    bot.answer_callback_query(call.id)


# ---- تطبيق الويب (Webhook) الخاص باستضافة Vercel ----
app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def webhook():
    """نقطة استقبال تحديثات تلجرام القادمة من Vercel."""
    if request.method == "POST":
        if request.headers.get("content-type") == "application/json":
            update = telebot.types.Update.de_json(request.get_data(as_text=True))
            bot.process_new_updates([update])
            return "OK", 200
        return "Unsupported content type", 403
    return "Quran bot is running", 200


@app.route("/set_webhook", methods=["GET"])
def set_webhook():
    """ضبط الـ Webhook على رابط النشر (يُستدعى مرة واحدة بعد النشر)."""
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        return "الرجاء ضبط المتغيّر WEBHOOK_URL أولاً", 400
    bot.remove_webhook()
    bot.set_webhook(url=webhook_url)
    return f"تم ضبط الـ Webhook على: {webhook_url}", 200


@app.route("/webhook_info", methods=["GET"])
def webhook_info():
    """عرض حالة الـ Webhook الحالية المسجّلة لدى تلجرام لتسهيل تتبّع الأخطاء."""
    info = bot.get_webhook_info()
    return {
        "url": info.url,
        "pending_update_count": info.pending_update_count,
        "last_error_date": info.last_error_date,
        "last_error_message": info.last_error_message,
        "max_connections": info.max_connections,
        "ip_address": info.ip_address,
    }, 200


if __name__ == "__main__":
    # تشغيل محلي بنظام polling للتجربة فقط (على Vercel لا يُستخدم هذا المسار)
    print("Bot is running locally with polling...")
    bot.infinity_polling()
