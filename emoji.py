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
ID_World_Cup    = 5292279335154136992
ID_USERS        = 5193150897256936958
ID_DAY_GAME     = 5854750459851445043
ID_Transition   = 5269491346783099131
ID_SET_CARD     = 6111771632240433101
ID_Pending      = 5262838597060422237
ID_MESSAGE_ALL  = 5938311423712039050
ID_MISSION      = 6298649503285118920
ID_GIFT_DIAMOND = 4965219701572503640
ID_UESRS_WC     = 5193150897256936958
ID_GIFT         = 5264710902153767489
ID_ADMINE        = 5949327894567195412
ID_HELP         = 5827738598778080268
ID_WELCOME      = 5436203513149404753
ID_BET          = 6105002016457625114
ID_CONNECT      = 6001099232784683975
ID_SELF_EDIT    = 6001136607590096242
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
EMOJI_World_Cup   = pe(ID_World_Cup,   "🤖")
EMOJI_USERS       = pe(ID_USERS,       "🤖")
EMOJI_DAY_GAME    = pe(ID_DAY_GAME,    "🤖")
EMOJI_Transition  = pe(ID_Transition,  "🤖")
EMOJI_SET_CARD    = pe(ID_SET_CARD,    "🤖")
EMOJI_Pending     = pe(ID_Pending,     "🤖")
EMOJI_MESSAGE_ALL = pe(ID_MESSAGE_ALL, "🤖")
EMOJI_MISSION     = pe(ID_MISSION,     "🤖")
EMOJI_GIFT_DIAMOND = pe(ID_GIFT_DIAMOND, "🤖")
EMOJI_UESRS_WC    = pe(ID_UESRS_WC,    "🤖")
EMOJI_GIFT        = pe(ID_GIFT,        "🤖")
EMOJI_ADMINE      = pe(ID_ADMINE,      "🤖")
EMOJI_HELP        = pe(ID_HELP,        "🤖")
EMOJI_WELCOME     = pe(ID_WELCOME,     "🤖")
EMOJI_BET         = pe(ID_BET,         "🤖")
EMOJI_SELF_EDIT   = pe(ID_SELF_EDIT,   "🤖")

# ─────────────────────────────────────────
#  ایموجی‌های جدید (Placeholder ID - باید با شناسه واقعی پریمیوم جایگزین شوند)
# ─────────────────────────────────────────

ID_BACK         = 5000000000000000000   # 🔙 (placeholder - replace with real premium emoji id)
ID_WARNING      = 5000000000000000001   # ⚠️ (placeholder - replace with real premium emoji id)
ID_LIST         = 5000000000000000002   # 📋 (placeholder - replace with real premium emoji id)
ID_MONEY        = 5000000000000000003   # 💰 (placeholder - replace with real premium emoji id)
ID_EDIT         = 5000000000000000004   # 📝 (placeholder - replace with real premium emoji id)
ID_USER         = 5000000000000000005   # 👤 (placeholder - replace with real premium emoji id)
ID_TROPHY       = 5000000000000000006   # 🏆 (placeholder - replace with real premium emoji id)
ID_MEDAL        = 5000000000000000007   # 🏅 (placeholder - replace with real premium emoji id)
ID_CALENDAR     = 5000000000000000008   # 📅 (placeholder - replace with real premium emoji id)
ID_BLUE_CIRCLE  = 5000000000000000009   # 🔵 (placeholder - replace with real premium emoji id)
ID_ADD          = 5000000000000000010   # ➕ (placeholder - replace with real premium emoji id)
ID_BOOKS        = 5000000000000000011   # 📚 (placeholder - replace with real premium emoji id)
ID_ARROW_RIGHT  = 5000000000000000012   # → (placeholder - replace with real premium emoji id)
ID_PHOTO        = 5000000000000000013   # 🖼 (placeholder - replace with real premium emoji id)
ID_PARTY        = 5000000000000000014   # 🎉 (placeholder - replace with real premium emoji id)
ID_FOOTBALL     = 5000000000000000015   # ⚽️ (placeholder - replace with real premium emoji id)
ID_POINT_DOWN   = 5000000000000000016   # 👇 (placeholder - replace with real premium emoji id)
ID_CHART        = 5000000000000000017   # 📊 (placeholder - replace with real premium emoji id)
ID_USERS_GROUP  = 5000000000000000018   # 👥 (placeholder - replace with real premium emoji id)
ID_VIDEO        = 5000000000000000019   # 🎥 (placeholder - replace with real premium emoji id)
ID_SLOT_MACHINE = 5000000000000000020   # 🎰 (placeholder - replace with real premium emoji id)
ID_KEY          = 5000000000000000021   # 🔑 (placeholder - replace with real premium emoji id)
ID_EXCLAMATION  = 5000000000000000022   # ❗ (placeholder - replace with real premium emoji id)
ID_ARROW_LEFT   = 5000000000000000023   # ← (placeholder - replace with real premium emoji id)
ID_CARD         = 5000000000000000024   # 💳 (placeholder - replace with real premium emoji id)
ID_CONFETTI     = 5000000000000000025   # 🎊 (placeholder - replace with real premium emoji id)
ID_GOLD_MEDAL   = 5000000000000000026   # 🥇 (placeholder - replace with real premium emoji id)
ID_GAME         = 5000000000000000027   # 🎮 (placeholder - replace with real premium emoji id)
ID_TAX          = 5000000000000000028   # 🏛 (placeholder - replace with real premium emoji id)
ID_HANDSHAKE    = 5000000000000000029   # 🤝 (placeholder - replace with real premium emoji id)
ID_FINISH       = 5000000000000000030   # 🏁 (placeholder - replace with real premium emoji id)
ID_WEBSITE      = 5000000000000000031   # 🌐 (placeholder - replace with real premium emoji id)
ID_PACKAGE      = 5000000000000000032   # 📦 (placeholder - replace with real premium emoji id)
ID_WAVE         = 5000000000000000033   # 👋 (placeholder - replace with real premium emoji id)
ID_SHOPPING     = 5000000000000000034   # 🛍 (placeholder - replace with real premium emoji id)
ID_PAPER        = 5000000000000000035   # 📄 (placeholder - replace with real premium emoji id)
ID_EMPTY_MAILBOX= 5000000000000000036   # 📭 (placeholder - replace with real premium emoji id)
ID_EYE          = 5000000000000000037   # 👁 (placeholder - replace with real premium emoji id)
ID_CLOCK        = 5000000000000000038   # 🕐 (placeholder - replace with real premium emoji id)
ID_PHONE        = 5000000000000000039   # 📱 (placeholder - replace with real premium emoji id)
ID_LOCK         = 5000000000000000040   # 🔒 (placeholder - replace with real premium emoji id)
ID_CROWN        = 5000000000000000041   # 👑 (placeholder - replace with real premium emoji id)
ID_PIN          = 5000000000000000042   # 📌 (placeholder - replace with real premium emoji id)
ID_NUMBERS      = 5000000000000000043   # 🔢 (placeholder - replace with real premium emoji id)
ID_SEND_OUT     = 5000000000000000044   # 📤 (placeholder - replace with real premium emoji id)
ID_MEGAPHONE    = 5000000000000000045   # 📣 (placeholder - replace with real premium emoji id)
ID_PENCIL       = 5000000000000000046   # ✏️ (placeholder - replace with real premium emoji id)
ID_WHITE_SQUARE = 5000000000000000047   # ⬜️ (placeholder - replace with real premium emoji id)
ID_HEART_SUIT   = 5000000000000000048   # ♥️ (placeholder - replace with real premium emoji id)
ID_SPADE_SUIT   = 5000000000000000049   # ♠️ (placeholder - replace with real premium emoji id)
ID_DIAMOND_SUIT = 5000000000000000050   # ♦️ (placeholder - replace with real premium emoji id)
ID_CLUB_SUIT    = 5000000000000000051   # ♣️ (placeholder - replace with real premium emoji id)
ID_ROCK         = 5000000000000000052   # 🪨 (placeholder - replace with real premium emoji id)
ID_SCISSORS     = 5000000000000000053   # ✂️ (placeholder - replace with real premium emoji id)
ID_NO_ENTRY     = 5000000000000000054   # ⛔️ (placeholder - replace with real premium emoji id)
ID_DICE         = 5000000000000000055   # 🎲 (placeholder - replace with real premium emoji id)
ID_SAD          = 5000000000000000056   # 😔 (placeholder - replace with real premium emoji id)
ID_MOBILE_SEND  = 5000000000000000057   # 📲 (placeholder - replace with real premium emoji id)
ID_QUESTION     = 5000000000000000058   # ❓ (placeholder - replace with real premium emoji id)
ID_BANKNOTE     = 5000000000000000059   # 💵 (placeholder - replace with real premium emoji id)
ID_RECEIPT      = 5000000000000000060   # 🧾 (placeholder - replace with real premium emoji id)
ID_INCOMING_MSG = 5000000000000000061   # 📨 (placeholder - replace with real premium emoji id)
ID_ARROW_DOWN   = 5000000000000000062   # ⬇️ (placeholder - replace with real premium emoji id)
ID_SILVER_MEDAL = 5000000000000000063   # 🥈 (placeholder - replace with real premium emoji id)
ID_BRONZE_MEDAL = 5000000000000000064   # 🥉 (placeholder - replace with real premium emoji id)
ID_LOCKED_KEY   = 5000000000000000065   # 🔐 (placeholder - replace with real premium emoji id)
ID_ARROW_LEFT_FULL= 5000000000000000066   # ⬅️ (placeholder - replace with real premium emoji id)
ID_CHECK_MARK   = 5000000000000000067   # ✔️ (placeholder - replace with real premium emoji id)
ID_PROHIBITED   = 5000000000000000068   # 🚫 (placeholder - replace with real premium emoji id)
ID_BLACK_CIRCLE = 5000000000000000069   # ⚫️ (placeholder - replace with real premium emoji id)
ID_YELLOW_CIRCLE= 5000000000000000070   # 🟡 (placeholder - replace with real premium emoji id)
ID_SUPPORT_RING = 5000000000000000071   # 🛟 (placeholder - replace with real premium emoji id)
ID_IDEA         = 5000000000000000072   # 💡 (placeholder - replace with real premium emoji id)
ID_REFRESH      = 5000000000000000073   # 🔄 (placeholder - replace with real premium emoji id)
ID_TRIDENT      = 5000000000000000074   # 🔱 (placeholder - replace with real premium emoji id)
ID_ENVELOPE     = 5000000000000000075   # 📩 (placeholder - replace with real premium emoji id)
ID_BLUE_SQUARE  = 5000000000000000076   # 🟦 (placeholder - replace with real premium emoji id)
ID_RED_SQUARE   = 5000000000000000077   # 🟥 (placeholder - replace with real premium emoji id)
ID_RETURN_ARROW = 5000000000000000078   # ↩️ (placeholder - replace with real premium emoji id)

EMOJI_BACK        = pe(ID_BACK, "🔙")
EMOJI_WARNING     = pe(ID_WARNING, "⚠️")
EMOJI_LIST        = pe(ID_LIST, "📋")
EMOJI_MONEY       = pe(ID_MONEY, "💰")
EMOJI_EDIT        = pe(ID_EDIT, "📝")
EMOJI_USER        = pe(ID_USER, "👤")
EMOJI_TROPHY      = pe(ID_TROPHY, "🏆")
EMOJI_MEDAL       = pe(ID_MEDAL, "🏅")
EMOJI_CALENDAR    = pe(ID_CALENDAR, "📅")
EMOJI_BLUE_CIRCLE = pe(ID_BLUE_CIRCLE, "🔵")
EMOJI_ADD         = pe(ID_ADD, "➕")
EMOJI_BOOKS       = pe(ID_BOOKS, "📚")
EMOJI_ARROW_RIGHT = pe(ID_ARROW_RIGHT, "→")
EMOJI_PHOTO       = pe(ID_PHOTO, "🖼")
EMOJI_PARTY       = pe(ID_PARTY, "🎉")
EMOJI_FOOTBALL    = pe(ID_FOOTBALL, "⚽️")
EMOJI_POINT_DOWN  = pe(ID_POINT_DOWN, "👇")
EMOJI_CHART       = pe(ID_CHART, "📊")
EMOJI_USERS_GROUP = pe(ID_USERS_GROUP, "👥")
EMOJI_VIDEO       = pe(ID_VIDEO, "🎥")
EMOJI_SLOT_MACHINE= pe(ID_SLOT_MACHINE, "🎰")
EMOJI_KEY         = pe(ID_KEY, "🔑")
EMOJI_EXCLAMATION = pe(ID_EXCLAMATION, "❗")
EMOJI_ARROW_LEFT  = pe(ID_ARROW_LEFT, "←")
EMOJI_CARD        = pe(ID_CARD, "💳")
EMOJI_CONFETTI    = pe(ID_CONFETTI, "🎊")
EMOJI_GOLD_MEDAL  = pe(ID_GOLD_MEDAL, "🥇")
EMOJI_GAME        = pe(ID_GAME, "🎮")
EMOJI_TAX         = pe(ID_TAX, "🏛")
EMOJI_HANDSHAKE   = pe(ID_HANDSHAKE, "🤝")
EMOJI_FINISH      = pe(ID_FINISH, "🏁")
EMOJI_WEBSITE     = pe(ID_WEBSITE, "🌐")
EMOJI_PACKAGE     = pe(ID_PACKAGE, "📦")
EMOJI_WAVE        = pe(ID_WAVE, "👋")
EMOJI_SHOPPING    = pe(ID_SHOPPING, "🛍")
EMOJI_PAPER       = pe(ID_PAPER, "📄")
EMOJI_EMPTY_MAILBOX= pe(ID_EMPTY_MAILBOX, "📭")
EMOJI_EYE         = pe(ID_EYE, "👁")
EMOJI_CLOCK       = pe(ID_CLOCK, "🕐")
EMOJI_PHONE       = pe(ID_PHONE, "📱")
EMOJI_LOCK        = pe(ID_LOCK, "🔒")
EMOJI_CROWN       = pe(ID_CROWN, "👑")
EMOJI_PIN         = pe(ID_PIN, "📌")
EMOJI_NUMBERS     = pe(ID_NUMBERS, "🔢")
EMOJI_SEND_OUT    = pe(ID_SEND_OUT, "📤")
EMOJI_MEGAPHONE   = pe(ID_MEGAPHONE, "📣")
EMOJI_PENCIL      = pe(ID_PENCIL, "✏️")
EMOJI_WHITE_SQUARE= pe(ID_WHITE_SQUARE, "⬜️")
EMOJI_HEART_SUIT  = pe(ID_HEART_SUIT, "♥️")
EMOJI_SPADE_SUIT  = pe(ID_SPADE_SUIT, "♠️")
EMOJI_DIAMOND_SUIT= pe(ID_DIAMOND_SUIT, "♦️")
EMOJI_CLUB_SUIT   = pe(ID_CLUB_SUIT, "♣️")
EMOJI_ROCK        = pe(ID_ROCK, "🪨")
EMOJI_SCISSORS    = pe(ID_SCISSORS, "✂️")
EMOJI_NO_ENTRY    = pe(ID_NO_ENTRY, "⛔️")
EMOJI_DICE        = pe(ID_DICE, "🎲")
EMOJI_SAD         = pe(ID_SAD, "😔")
EMOJI_MOBILE_SEND = pe(ID_MOBILE_SEND, "📲")
EMOJI_QUESTION    = pe(ID_QUESTION, "❓")
EMOJI_BANKNOTE    = pe(ID_BANKNOTE, "💵")
EMOJI_RECEIPT     = pe(ID_RECEIPT, "🧾")
EMOJI_INCOMING_MSG= pe(ID_INCOMING_MSG, "📨")
EMOJI_ARROW_DOWN  = pe(ID_ARROW_DOWN, "⬇️")
EMOJI_SILVER_MEDAL= pe(ID_SILVER_MEDAL, "🥈")
EMOJI_BRONZE_MEDAL= pe(ID_BRONZE_MEDAL, "🥉")
EMOJI_LOCKED_KEY  = pe(ID_LOCKED_KEY, "🔐")
EMOJI_ARROW_LEFT_FULL= pe(ID_ARROW_LEFT_FULL, "⬅️")
EMOJI_CHECK_MARK  = pe(ID_CHECK_MARK, "✔️")
EMOJI_PROHIBITED  = pe(ID_PROHIBITED, "🚫")
EMOJI_BLACK_CIRCLE= pe(ID_BLACK_CIRCLE, "⚫️")
EMOJI_YELLOW_CIRCLE= pe(ID_YELLOW_CIRCLE, "🟡")
EMOJI_SUPPORT_RING= pe(ID_SUPPORT_RING, "🛟")
EMOJI_IDEA        = pe(ID_IDEA, "💡")
EMOJI_REFRESH     = pe(ID_REFRESH, "🔄")
EMOJI_TRIDENT     = pe(ID_TRIDENT, "🔱")
EMOJI_ENVELOPE    = pe(ID_ENVELOPE, "📩")
EMOJI_BLUE_SQUARE = pe(ID_BLUE_SQUARE, "🟦")
EMOJI_RED_SQUARE  = pe(ID_RED_SQUARE, "🟥")
EMOJI_RETURN_ARROW= pe(ID_RETURN_ARROW, "↩️")
