# emoji.py - پریمیوم ایموجی‌های تلگرام
# ─────────────────────────────────────────
#  دو نوع استفاده:
#
#  ۱) در متن پیام‌ها (parse_mode="HTML"):
#       f"{EM.EMOJI_BALANCE} موجودی شما..."
#     → کاربران پریمیوم: ایموجی انیمیشنی
#     → بقیه: ایموجی معمولی (fallback)
#
#  ۲) در دکمه‌های InlineKeyboard:
#       types.InlineKeyboardButton(
#           "موجودی",
#           callback_data="menu_balance",
#           icon_custom_emoji_id=str(EM.ID_BALANCE)
#       )
#     → نیاز به pyTelegramBotAPI >= 4.14
# ─────────────────────────────────────────


# ─────────────────────────────────────────
#  شناسه‌های عددی ایموجی‌ها
# ─────────────────────────────────────────

ID_DAILY_GIFT   = 5834422787661369616   # 🎁 هدیه روزانه
ID_BALANCE      = 6001287064589439895   # 💎 موجودی
ID_CONFIRM      = 5830326445422940546   # ✅ تایید
ID_CANCEL       = 5832353674281620438   # ❌ لغو
ID_DIAMONDS     = 5814670671153730702   # 💎 الماس‌ها
ID_BUY_DIAMOND  = 4960766907113276588   # 🛒 خرید الماس
ID_REFERRAL     = 5260730055880876557   # 🔗 رفرال
ID_MISSION      = 5352629724516458059   # 🎯 ماموریت
ID_GUIDE        = 5814171260946485530   # 📖 راهنما
ID_SELF_MANAGE  = 6219810752887262728   # 🤖 مدیریت سلف
ID_ADMIN        = 6298670698948724690   # 👮 مدیریت
ID_SELF_ON      = 5260726538302660868   # 🟢 روشن کردن سلف
ID_SELF_OFF     = 5260342697075416641   # 🔴 خاموش کردن سلف
ID_SELF_DELETE  = 5258130763148172425   # 🗑 حذف سلف
ID_BET_JOIN     = 6001567998400273892   # ⚔️ ورود به شرط‌بندی
ID_FORCED_JOIN  = 6255593645848660539
ID_CONNECT      = 6001099232784683975
ID_SET_CARD     = 6111771632240433101

# ─────────────────────────────────────────
#  تابع کمکی برای متن پیام (HTML tag)
# ─────────────────────────────────────────

def pe(emoji_id: int, fallback: str = "⭐") -> str:
    """
    رشته ایموجی پریمیوم برای استفاده در متن پیام‌ها.
    حتماً parse_mode='HTML' باشه.
    """
    return f"<tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji>"


# ─────────────────────────────────────────
#  ایموجی‌های HTML برای پیام‌ها
# ─────────────────────────────────────────

EMOJI_DAILY_GIFT  = pe(ID_DAILY_GIFT,  "🎁")
EMOJI_BALANCE     = pe(ID_BALANCE,     "💎")
EMOJI_CONFIRM     = pe(ID_CONFIRM,     "✅")
EMOJI_CANCEL      = pe(ID_CANCEL,      "❌")
EMOJI_DIAMONDS    = pe(ID_DIAMONDS,    "💎")
EMOJI_BUY_DIAMOND = pe(ID_BUY_DIAMOND, "🛒")
EMOJI_REFERRAL    = pe(ID_REFERRAL,    "🔗")
EMOJI_MISSION     = pe(ID_MISSION,     "🎯")
EMOJI_GUIDE       = pe(ID_GUIDE,       "📖")
EMOJI_SELF_MANAGE = pe(ID_SELF_MANAGE, "🤖")
EMOJI_ADMIN       = pe(ID_ADMIN,       "👮")
EMOJI_SELF_ON     = pe(ID_SELF_ON,     "🟢")
EMOJI_SELF_OFF    = pe(ID_SELF_OFF,    "🔴")
EMOJI_SELF_DELETE = pe(ID_SELF_DELETE, "🗑")
EMOJI_BET_JOIN    = pe(ID_BET_JOIN,    "⚔️")
EMOJI_FORCED_JOIN = pe(ID_FORCED_JOIN, "📢")
EMOJI_CONNECT     = pe(ID_CONNECT,     "🤖")
EMOJI_SET_CARD    = pe(ID_SET_CARD,    "💳")
