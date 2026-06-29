# ══════════════════════════════════════════════════════════════════════════════
# 🧪 مثال عملی استفاده از سیستم ایموجی‌های پرمیوم
# این فایل فقط برای نمونه است؛ نشون می‌ده چطور emoji_system.py رو توی یه ربات
# واقعی (pyTelegramBotAPI / telebot) به کار ببرید.
# اجرا: python3 emoji_usage_example.py
# ══════════════════════════════════════════════════════════════════════════════

import telebot

from emoji_system import (
    e,                  # ایموجی با نام دوستانه: e("fire")
    tg_emoji,            # ایموجی مستقیم با ID: tg_emoji("123...")
    build_message,       # چسباندن چند تکه متن/ایموجی به هم
    bullet_line,         # یک خط با بولت ایموجی
    emoji_list,          # لیست چند خطی با ایموجی
    format_template,      # جایگزینی :name: داخل یک متن آزاد
    send_emoji_message,   # ارسال مستقیم پیام با parse_mode=HTML
    EMOJIS,
)

BOT_TOKEN = "123456:YOUR_BOT_TOKEN_HERE"   # توکن واقعی ربات‌تون رو اینجا بگذارید
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


# ── ۱) تابع ساده برای گرفتن emoji_id و ارسالش ──────────────────────────────
def send_single_emoji(chat_id: int, emoji_id: str, fallback: str = "🔥"):
    """فقط یک ایموجی پرمیوم با گرفتن emoji_id ارسال می‌کنه."""
    text = tg_emoji(emoji_id, fallback)
    return send_emoji_message(bot, chat_id, text)


# ── ۲) استفاده از ایموجی داخل یک متن داینامیک ───────────────────────────────
def send_welcome(chat_id: int, username: str, diamonds: int):
    text = (
        f"{e('crown')} سلام <b>{username}</b>!\n"
        f"{e('diamond')} موجودی فعلی شما: <b>{diamonds}</b> الماس\n"
        f"{e('fire')} امیدواریم روز خوبی داشته باشید."
    )
    return send_emoji_message(bot, chat_id, text)


# همین کار رو می‌شه با یک تمپلیت آزاد (مثلاً از دیتابیس خوانده‌شده) هم انجام داد:
def send_welcome_via_template(chat_id: int, username: str, diamonds: int):
    raw_template = (
        ":crown: سلام <b>{username}</b>!\n"
        ":diamond: موجودی فعلی شما: <b>{diamonds}</b> الماس\n"
        ":fire: امیدواریم روز خوبی داشته باشید."
    ).format(username=username, diamonds=diamonds)
    text = format_template(raw_template)   # همه‌ی :name: ها رو تبدیل به tg-emoji می‌کنه
    return send_emoji_message(bot, chat_id, text)


# ── ۳) دیکشنری/لیست ایموجی‌ها برای استفاده‌ی راحت ───────────────────────────
def send_main_menu(chat_id: int):
    text = emoji_list(
        header=f"{e('fire')} <b>منوی اصلی</b>\n",
        items=[
            ("diamond",          "موجودی الماس"),
            ("trophy",           "جدول رتبه‌بندی"),
            ("gift",             "دریافت هدیه روزانه"),
            ("crown",            "پلن‌های ویژه"),
            ("checkmark_green",  "تاریخچه تراکنش‌ها"),
        ],
    )
    return send_emoji_message(bot, chat_id, text)


# ── ۴) چند ایموجی توی یک پیام (به‌صورت دستی، بدون emoji_list) ──────────────
def send_transaction_result(chat_id: int, sender: str, receiver: str, amount: int):
    text = build_message(
        bullet_line("checkmark_green", "<b>انتقال با موفقیت انجام شد</b>"), "\n\n",
        bullet_line("arrow_blue", f"از: <b>{sender}</b>"), "\n",
        bullet_line("gift", f"به: <b>{receiver}</b>"), "\n",
        bullet_line("diamond", f"مقدار: <b>{amount}</b> الماس"),
    )
    return send_emoji_message(bot, chat_id, text)


# ── ۵) دستور تستی برای دیدن همه‌ی نمونه‌ها روی تلگرام واقعی ─────────────────
@bot.message_handler(commands=["emoji_demo"])
def cmd_emoji_demo(message):
    chat_id = message.chat.id
    send_welcome(chat_id, message.from_user.first_name, diamonds=120)
    send_main_menu(chat_id)
    send_transaction_result(chat_id, "علی", "رضا", amount=50)
    print(f"✅ تعداد کل ایموجی‌های موجود در دیکشنری: {len(EMOJIS)}")


if __name__ == "__main__":
    print("نمونه‌ی خروجی (بدون ارسال واقعی به تلگرام):\n")
    print(build_message(e("crown"), " نمونه‌ی ساخت پیام بدون ارسال"))
    print()
    print(format_template(":diamond: این یک تست :fire: است"))
    print()
    print("برای تست واقعی روی تلگرام، BOT_TOKEN را تنظیم کرده و bot.polling() را اجرا کنید:")
    print("    bot.polling()")
