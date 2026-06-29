# ══════════════════════════════════════════════════════════════════════════════
# 💎 سیستم ایموجی‌های پرمیوم تلگرام
# فایل: emoji_system.py
# ══════════════════════════════════════════════════════════════════════════════

import re
from typing import Optional, Union


# ──────────────────────────────────────────────────────────────────────────────
# 📦 دیکشنری ایموجی‌ها (استخراج‌شده از تصاویر ارسالی)
# ──────────────────────────────────────────────────────────────────────────────

EMOJIS: dict[str, str] = {
    # ── جواهرات و جوایز ───────────────────────────────────────────────────────
    "diamond":          "5814670671153730702",
    "diamond_pink":     "5834605246462039136",
    "diamond_blue":     "5834534611429889319",
    "crown":            "5834643712189141114",

    # ── سوشال مدیا و اپ‌ها ────────────────────────────────────────────────────
    "tiktok":           "5814441697857245324",
    "youtube":          "5816897547272196350",
    "telegram_check":   "5814320153753334246",  # تیک آبی

    # ── وضعیت‌ها ─────────────────────────────────────────────────────────────
    "checkmark_green":  "5830326445422940546",
    "cross_red":        "5832353674281620438",
    "warning":          "5830451652309553634",
    "exclamation_red":  "5830204369567485741",
    "eyes":             "5830223696920318502",

    # ── گیفت و هدیه ───────────────────────────────────────────────────────────
    "gift":             "5834422787661369616",
    "gift_box2":        "5834806972485996935",
    "gift_box3":        "5834677646725747863",
    "trophy":           "5830404222985704156",

    # ── طبیعت و آتش ──────────────────────────────────────────────────────────
    "fire":             "5830221171479548287",
    "fleur":            "5830275644549764382",

    # ── ابزار و نمادها ────────────────────────────────────────────────────────
    "arrow_blue":       "5830348293921576631",
    "microphone":       "5830389143355528677",
    "megaphone":        "5830203935775789535",
    "flag_red":         "5830256132513338127",
    "ban":              "5830424611195458038",
    "chain":            "5828033658736349867",

    # ── ایموجی‌های بدون آیکون واضح (plain bullet) ────────────────────────────
    "bullet_01":        "5834720991535698405",
    "bullet_02":        "5834958945608799480",
    "bullet_03":        "5836969794662627375",  # تقریبی از تصویر ۲
    "bullet_04":        "5834891742255517576",
    "bullet_05":        "5834471698748937179",
    "bullet_06":        "5834655325780710284",
    "bullet_07":        "5834734348884075863",
    "bullet_08":        "5836753004987945428",
    "bullet_09":        "5834676658883269110",
    "bullet_10":        "5836674604654924227",
    "bullet_11":        "5834965877686015045",
    "bullet_12":        "5837175543870525260",
    "bullet_13":        "5834453569691980186",
    "bullet_14":        "5836922797930058251",
    "bullet_15":        "5834830405827563615",
    "bullet_16":        "5834459002825611060",

    # ── ایموجی‌های Custom Emoji channel (از تصاویر ۴–۷) ─────────────────────
    "apps_grid":        "5226513232549664618",
    "photo_edit":       "5258050709252743821",
    "person_star":      "5258362837411045098",
    "star_outline":     "5258185631355378853",
    "download_arrow":   "5258514780469075716",
    "calendar":         "5258389041006518073",
    "timer_10d":        "5258226313285607065",
    "timer_1h":         "5260280853841321805",
    "timer_1m":         "5258071638628377037",
    "timer_1w":         "5258123337149717894",
    "scissors":         "5258318620722733379",
    "robot":            "5258169263235013408",
    "robot2":           "5258145898612924124",
    "lines":            "5257965174979042426",
    "bitcoin":          "5258368777350816286",
    "lightning":        "5258152182150077732",
    "book":             "5258323838183396223",
    "lock_box":         "5258093637450866522",
    "briefcase":        "5258260149037965799",
    "key":              "5258450450448915742",
    "inbox":            "5258105663359294787",
    "phone":            "5258337316715373336",
    "camera":           "5258205968025525531",
    "pencil":           "5258215635996908355",
    "speaker":          "5260268501515377807",
    "checkmark":        "5260726538302660868",
    "circle_x":         "5260342697075416641",
    "link_chain":       "5260730055880876557",
    "file_thumb":       "5257974976094412956",
    "file_thumb2":      "5258477707035885832",
    "copyright":        "5258507474729704350",
    "group_add":        "5258513401784573443",
    "trash":            "5258130763148172425",
    "edit_box":         "5258331647358540449",
    "arrow_up_right":   "5260233433107407649",
    "shield":           "5258430848218176413",
    "file_doc":         "5257965810634202885",
    "file_doc2":        "5257969839313526622",
    "share":            "5260450573768990626",
    "game_controller":  "5258508428212445001",
    "graduation":       "5258334872878980409",
    "heart":            "5258179403652801593",
    "house":            "5257963315258204021",
    "gift_tag":         "5258084656674250503",
    "bulb":             "5258216851472654189",
    "location":         "5258509201306557640",
    "padlock":          "5258476306152038031",
    "heart2":           "5258215846450305872",
    "person_check":     "5260535596941582167",
    "moon":             "5258011861273551368",
}


# ──────────────────────────────────────────────────────────────────────────────
# ✅ توابع اصلی
# ──────────────────────────────────────────────────────────────────────────────

def get_emoji_id(name: str) -> Optional[str]:
    """
    شناسه‌ی خام (بدون تگ HTML) یک ایموجی رو برمی‌گردونه — برای جاهایی که به
    خودِ ID نیاز دارید، نه تگ <tg-emoji>. مهم‌ترین مصرفش پارامتر
    icon_custom_emoji_id روی InlineKeyboardButton / KeyboardButton است،
    چون اون پارامتر متن HTML قبول نمی‌کنه، فقط ID خام می‌خواد.

    پارامتر:
        name : کلید دیکشنری EMOJIS (مثلاً "diamond")

    مثال:
        types.InlineKeyboardButton(
            "موجودی", callback_data="menu_balance",
            icon_custom_emoji_id=get_emoji_id("diamond"),
        )

    اگه نام پیدا نشه None برمی‌گردونه (یعنی دکمه بدون آیکون ساخته می‌شه،
    بدون اینکه خطا بدهد).
    """
    return EMOJIS.get(name)


def tg_emoji(emoji_id: Union[str, int], fallback: str = "•") -> str:
    """
    یک ایموجی پرمیوم با فرمت HTML برمی‌گردونه.

    پارامترها:
        emoji_id : شناسه عددی ایموجی (string یا int)
        fallback : متن جایگزین برای کلاینت‌هایی که پشتیبانی نمی‌کنن

    مثال:
        tg_emoji("5814670671153730702")
        → '<tg-emoji emoji-id="5814670671153730702">💎</tg-emoji>'
    """
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def e(name: str, fallback: str = "•") -> str:
    """
    ایموجی را با نام دوستانه برمی‌گردونه.

    پارامترها:
        name    : کلید دیکشنری EMOJIS (مثلاً "diamond")
        fallback: متن جایگزین

    مثال:
        e("fire")   → '<tg-emoji emoji-id="5830221171479548287">🔥</tg-emoji>'
    """
    emoji_id = EMOJIS.get(name)
    if emoji_id is None:
        return fallback
    return tg_emoji(emoji_id, fallback)


def build_message(*parts: str, sep: str = "") -> str:
    """
    چند قطعه متن/ایموجی را کنار هم می‌چینه.

    مثال:
        build_message(e("diamond"), " الماس‌های شما: ", "<b>50</b>")
    """
    return sep.join(str(p) for p in parts)


def send_emoji_message(
    bot,
    chat_id: Union[int, str],
    text: str,
    reply_to_message_id: Optional[int] = None,
    **kwargs,
) -> object:
    """
    یه پیام (که می‌تونه شامل tg-emoji باشه) رو با parse_mode=HTML ارسال می‌کنه.
    این تابع همون چیزیه که موقع «ارسال ایموجی با گرفتن emoji_id» باید صدا بزنید —
    دیگه لازم نیست هر جا parse_mode="HTML" رو دستی پاس بدید.

    پارامترها:
        bot      : نمونه‌ی telebot.TeleBot (یا هر کلاینتی که send_message دارد)
        chat_id  : آیدی چت مقصد
        text     : متنی که می‌تونه شامل e(...) / tg_emoji(...) باشه
        reply_to_message_id : اختیاری، برای ریپلای روی پیام خاص
        **kwargs : هر آرگومان دیگه‌ای که send_message قبول می‌کنه (reply_markup و ...)

    مثال:
        send_emoji_message(bot, chat_id, f"{e('fire')} آپدیت جدید رسید!")
    """
    if reply_to_message_id is not None:
        kwargs["reply_to_message_id"] = reply_to_message_id
    return bot.send_message(chat_id, text, parse_mode="HTML", **kwargs)


# الگوی :emoji_name: داخل متن، مثلاً ":fire: شارژ شد :diamond:"
_TEMPLATE_PATTERN = re.compile(r":([a-zA-Z0-9_]+):")


def format_template(template: str) -> str:
    """
    یک متن داینامیک که شامل ':emoji_name:' هست رو می‌گیره و همه‌ی این الگوها
    رو با ایموجی پرمیوم متناظرشون (از دیکشنری EMOJIS) جایگزین می‌کنه.
    این یعنی می‌تونید متن رو از جای دیگه (دیتابیس، فایل ترجمه و ...) بسازید
    و فقط در آخر یک‌بار format_template صداش کنید — مناسب برای چند ایموجی
    توی یک پیام بدون نیاز به ()e تکراری.

    مثال:
        format_template(":diamond: موجودی شما :crown: VIP است")
        → '<tg-emoji emoji-id="...">💎</tg-emoji> موجودی شما <tg-emoji emoji-id="...">👑</tg-emoji> VIP است'

    اگه نام ایموجی توی دیکشنری نباشه، همون ':name:' بدون تغییر باقی می‌مونه
    (تا متوجه‌ی غلط تایپی بشید).
    """
    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name in EMOJIS:
            return e(name)
        return match.group(0)

    return _TEMPLATE_PATTERN.sub(_replace, template)


def bullet_line(emoji_name: str, text: str, fallback: str = "•") -> str:
    """
    یک خط با ایموجی bullet می‌سازه.

    مثال:
        bullet_line("checkmark_green", "خرید انجام شد")
        → '<tg-emoji ...>•</tg-emoji> خرید انجام شد'
    """
    return f"{e(emoji_name, fallback)} {text}"


def emoji_list(items: list[tuple[str, str]], header: str = "") -> str:
    """
    یک لیست چند خطی از آیتم‌ها می‌سازه.

    پارامتر:
        items  : لیستی از (emoji_name, text)
        header : عنوان اختیاری بالای لیست

    مثال:
        emoji_list([("diamond","۱۰ الماس"), ("crown","مقام اول")])
    """
    lines = []
    if header:
        lines.append(header)
    for emoji_name, text in items:
        lines.append(bullet_line(emoji_name, text))
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 🧪 مثال‌های عملی (برای تست مستقیم)
# ──────────────────────────────────────────────────────────────────────────────

def example_profile_message(username: str, diamonds: int, rank: int) -> str:
    """پیام پروفایل کاربر با ایموجی‌های پرمیوم"""
    return (
        f"{e('diamond')} <b>پروفایل کاربر</b>\n\n"
        f"{e('telegram_check')} نام: <b>{username}</b>\n"
        f"{e('diamond', '💎')} الماس‌ها: <b>{diamonds}</b>\n"
        f"{e('crown', '👑')} رتبه: <b>{rank}</b>\n\n"
        f"{e('fire', '🔥')} به بازی ادامه بده!"
    )


def example_transaction_message(amount: int, sender: str, receiver: str) -> str:
    """پیام تراکنش موفق"""
    return (
        f"{e('checkmark_green', '✅')} <b>انتقال موفق</b>\n\n"
        f"{e('arrow_blue', '➡️')} از: <b>{sender}</b>\n"
        f"{e('gift', '🎁')} به: <b>{receiver}</b>\n"
        f"{e('diamond', '💎')} مقدار: <b>{amount} الماس</b>"
    )


def example_warning_message(text: str) -> str:
    """پیام هشدار"""
    return f"{e('warning', '⚠️')} <b>هشدار:</b> {text}"


def example_menu_message() -> str:
    """پیام منو با لیست گزینه‌ها"""
    return emoji_list(
        header=f"{e('fire')} <b>منوی اصلی</b>\n",
        items=[
            ("diamond",         "موجودی الماس"),
            ("trophy",          "جدول رتبه‌بندی"),
            ("gift",            "دریافت هدیه"),
            ("crown",           "پلن‌های ویژه"),
            ("checkmark_green", "تاریخچه تراکنش‌ها"),
            ("cross_red",       "خروج"),
        ]
    )


# ──────────────────────────────────────────────────────────────────────────────
# ▶️  اجرای مستقیم برای تست
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== تست ایموجی‌های پرمیوم ===\n")

    print("--- پروفایل ---")
    print(example_profile_message("علی", 150, 3))

    print("\n--- تراکنش ---")
    print(example_transaction_message(50, "علی", "رضا"))

    print("\n--- هشدار ---")
    print(example_warning_message("موجودی کافی نیست"))

    print("\n--- منو ---")
    print(example_menu_message())

    print("\n--- استفاده مستقیم از ID ---")
    custom_id = "4960766907113276588"   # از تصویر ۸
    print(tg_emoji(custom_id, "🍀"))

    print(f"\n✅ تعداد کل ایموجی‌های تعریف‌شده: {len(EMOJIS)}")
