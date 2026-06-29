# emoji.py - پریمیوم ایموجی‌های تلگرام
# ─────────────────────────────────────────
#  دو نوع استفاده:
#
#  ۱) در متن پیام‌ها (parse_mode="HTML"):
#       f"{EM.EMOJI_BALANCE} موجودی شما..."
#
#  ۲) در دکمه‌های InlineKeyboard:
#       types.InlineKeyboardButton(
#           "موجودی",
#           callback_data="menu_balance",
#           icon_custom_emoji_id=str(EM.ID_BALANCE)
#       )
#     → نیاز به pyTelegramBotAPI >= 4.14
#
#  نکته فنی: تگ <tg-emoji> در تلگرام به یک کاراکتر داخلی (fallback)
#  نیاز دارد تا در کلاینت‌هایی که ایموجی پریمیوم را نمایش نمی‌دهند
#  جایگزین نشان داده شود. اینجا به‌جای ایموجی واقعی، یک کاراکتر خنثی
#  (•) استفاده شده تا ایموجی معمولی در کد نمایش داده نشود.
# ─────────────────────────────────────────


# ─────────────────────────────────────────
#  شناسه‌های عددی ایموجی‌ها (مجموعه اول)
# ─────────────────────────────────────────

ID_DAILY_GIFT   = 5834422787661369616   # هدیه روزانه
ID_BALANCE      = 6001287064589439895   # موجودی
ID_CONFIRM      = 5830326445422940546   # تایید
ID_CANCEL       = 5832353674281620438   # لغو
ID_DIAMONDS     = 5814670671153730702   # الماس‌ها
ID_BUY_DIAMOND  = 4960766907113276588   # خرید الماس
ID_REFERRAL     = 5260730055880876557   # رفرال
ID_MISSION      = 5352629724516458059   # ماموریت
ID_GUIDE        = 5814171260946485530   # راهنما
ID_SELF_MANAGE  = 6219810752887262728   # مدیریت سلف
ID_ADMIN        = 6298670698948724690   # مدیریت
ID_SELF_ON      = 5260726538302660868   # روشن کردن سلف
ID_SELF_OFF     = 5260342697075416641   # خاموش کردن سلف
ID_SELF_DELETE  = 5258130763148172425   # حذف سلف
ID_BET_JOIN     = 6001567998400273892   # ورود به شرط‌بندی


# ─────────────────────────────────────────
#  شناسه‌های عددی ایموجی‌ها (مجموعه دوم - جدید)
# ─────────────────────────────────────────

ID_CHECK_GREEN        = 6003670290402384022   # دکمه تایید (تیک سبز)
ID_CROSS_RED          = 6001100778972910576   # دکمه لغو (ضربدر قرمز) / ضربدر قرمز کوچک
ID_ARROW_GREEN_RIGHT  = 6001506245360490383   # فلش سبز به راست
ID_DOT_RED            = 6001084363607905493   # دایره/نقطه قرمز
ID_DOT_YELLOW         = 6001590297870472559   # دایره/نقطه زرد
ID_DOT_BLUE           = 6001662506257858338   # دایره/نقطه آبی
ID_STAR_SPARKLE       = 5951810621887484519   # ستاره/جرقه
ID_DIAMOND_ALT        = 5814670671153703702   # الماس
ID_HEART_FIRE         = 5920085137285979410   # قلب آتشین
ID_FIRE               = 5920300405342720405   # آتش
ID_WARNING            = 586845122943027806    # اخطار/هشدار
ID_ARROW_RED_LEFT     = 6001233526376146830   # پیکان/فلش قرمز به چپ / دایره بنفش
ID_NUM_1              = 6001401813230688310   # دکمه ۱ (عدد یک) / مثلث قرمز رو به پایین
ID_NUM_2              = 6001215342935056066   # دکمه ۲ (عدد دو)
ID_NUM_3              = 6001397359349601254   # دکمه ۳ (عدد سه)
ID_NUM_4              = 6001174729719152127   # دکمه ۴ (عدد چهار)
ID_NUM_5              = 6001325388582621920   # دکمه ۵ (عدد پنج)
ID_CHECK_DOUBLE       = 6003585858606360178   # تیک سبز دوتایی
ID_QUESTION_BLUE      = 5814566814911772402   # علامت سوال منور/آبی
ID_GLOBE              = 5814174821474374918   # کره زمین آبی
ID_YOUTUBE            = 5816897547272196350   # آیکون یوتیوب
ID_VERIFIED           = 5814329697995067221   # تیک تلگرام (وریفای آبی)
ID_TIKTOK             = 5814441697857245324   # آیکون تیک‌تاک
ID_EXCLAMATION_RED    = 6003387299302216925   # علامت تعجب قرمز
ID_LOCK               = 5868654512294302780   # آیکون قفل / آیکون روح
ID_KEY                = 586851847878392496    # آیکون کلید
ID_TROPHY             = 595194020545907793    # کاپ/جام قهرمانی
ID_CROWN              = 5951863819135241266   # تاج طلایی
ID_BOMB               = 5920106044850970363   # بمب
ID_MONEY_BAG          = 5814515033177530408   # کیسه پول/دلار
ID_CHECK_SMALL        = 6003655373936905033   # تیک سبز کوچک
ID_SQUARE_RED         = 600143555286709303    # مربع قرمز
ID_CROSS_GRAY         = 6001323614761128817   # دکمه ضربدر طوسی
ID_TRIANGLE_GREEN_UP  = 6001570163063788981   # مثلث سبز رو به بالا
ID_INSTAGRAM          = 5814168693572827593   # آیکون اینستاگرام
ID_TWITTER_X          = 5814391451034850508   # آیکون توییتر (X)
ID_YOUTUBE_ANIM       = 5816941935759200153   # آیکون یوتیوب متحرک
ID_SKULL              = 586856847878392496    # آیکون جمجمه
ID_EYE_ANIM           = 5830223696920318502   # ایموجی چشم متحرک
ID_CLAP               = 5830240436956748574   # ایموجی دست زدن
ID_GAMEPAD            = 5830404222985704156   # کنترلر بازی (گیم‌پد)
ID_STAR_SMALL_ANIM    = 595393157917465240    # ستاره متحرک کوچک
ID_TROPHY_ANIM        = 5954135079662916434   # کاپ قهرمانی متحرک

# توجه: چند آیدی در لیستی که فرستادی برای دو توضیح متفاوت تکرار شده‌اند
# (مثلاً ضربدر قرمز / ضربدر قرمز کوچک هر دو 6001100778972910576 هستند،
# و قفل / روح هر دو 5868654512294302780 هستند). همان مقادیر را که دادی
# عیناً گذاشتم، فقط دو اسم ثابت به یک شناسه اشاره می‌کنند.
# پیشنهاد می‌کنم بعد از جایگذاری، هر کدوم رو یک‌بار توی بات تست کنی
# که مطمئن شی ایموجی درستی نمایش داده می‌شه.


# ─────────────────────────────────────────
#  تابع کمکی برای متن پیام (HTML tag)
# ─────────────────────────────────────────

def pe(emoji_id: int, fallback: str = "•") -> str:
    """
    رشته ایموجی پریمیوم برای استفاده در متن پیام‌ها.
    حتماً parse_mode='HTML' باشه.
    """
    return f"<tg-emoji emoji-id='{emoji_id}'>{fallback}</tg-emoji>"


# ─────────────────────────────────────────
#  ایموجی‌های HTML برای پیام‌ها (مجموعه اول)
# ─────────────────────────────────────────

EMOJI_DAILY_GIFT  = pe(ID_DAILY_GIFT)
EMOJI_BALANCE     = pe(ID_BALANCE)
EMOJI_CONFIRM     = pe(ID_CONFIRM)
EMOJI_CANCEL      = pe(ID_CANCEL)
EMOJI_DIAMONDS    = pe(ID_DIAMONDS)
EMOJI_BUY_DIAMOND = pe(ID_BUY_DIAMOND)
EMOJI_REFERRAL    = pe(ID_REFERRAL)
EMOJI_MISSION     = pe(ID_MISSION)
EMOJI_GUIDE       = pe(ID_GUIDE)
EMOJI_SELF_MANAGE = pe(ID_SELF_MANAGE)
EMOJI_ADMIN       = pe(ID_ADMIN)
EMOJI_SELF_ON     = pe(ID_SELF_ON)
EMOJI_SELF_OFF    = pe(ID_SELF_OFF)
EMOJI_SELF_DELETE = pe(ID_SELF_DELETE)
EMOJI_BET_JOIN    = pe(ID_BET_JOIN)


# ─────────────────────────────────────────
#  ایموجی‌های HTML برای پیام‌ها (مجموعه دوم - جدید)
# ─────────────────────────────────────────

EMOJI_CHECK_GREEN       = pe(ID_CHECK_GREEN)
EMOJI_CROSS_RED         = pe(ID_CROSS_RED)
EMOJI_ARROW_GREEN_RIGHT = pe(ID_ARROW_GREEN_RIGHT)
EMOJI_DOT_RED           = pe(ID_DOT_RED)
EMOJI_DOT_YELLOW        = pe(ID_DOT_YELLOW)
EMOJI_DOT_BLUE          = pe(ID_DOT_BLUE)
EMOJI_STAR_SPARKLE      = pe(ID_STAR_SPARKLE)
EMOJI_DIAMOND_ALT       = pe(ID_DIAMOND_ALT)
EMOJI_HEART_FIRE        = pe(ID_HEART_FIRE)
EMOJI_FIRE              = pe(ID_FIRE)
EMOJI_WARNING           = pe(ID_WARNING)
EMOJI_ARROW_RED_LEFT    = pe(ID_ARROW_RED_LEFT)
EMOJI_NUM_1             = pe(ID_NUM_1)
EMOJI_NUM_2             = pe(ID_NUM_2)
EMOJI_NUM_3             = pe(ID_NUM_3)
EMOJI_NUM_4             = pe(ID_NUM_4)
EMOJI_NUM_5             = pe(ID_NUM_5)
EMOJI_CHECK_DOUBLE      = pe(ID_CHECK_DOUBLE)
EMOJI_QUESTION_BLUE     = pe(ID_QUESTION_BLUE)
EMOJI_GLOBE             = pe(ID_GLOBE)
EMOJI_YOUTUBE           = pe(ID_YOUTUBE)
EMOJI_VERIFIED          = pe(ID_VERIFIED)
EMOJI_TIKTOK            = pe(ID_TIKTOK)
EMOJI_EXCLAMATION_RED   = pe(ID_EXCLAMATION_RED)
EMOJI_LOCK              = pe(ID_LOCK)
EMOJI_KEY               = pe(ID_KEY)
EMOJI_TROPHY            = pe(ID_TROPHY)
EMOJI_CROWN             = pe(ID_CROWN)
EMOJI_BOMB              = pe(ID_BOMB)
EMOJI_MONEY_BAG         = pe(ID_MONEY_BAG)
EMOJI_CHECK_SMALL       = pe(ID_CHECK_SMALL)
EMOJI_SQUARE_RED        = pe(ID_SQUARE_RED)
EMOJI_CROSS_GRAY        = pe(ID_CROSS_GRAY)
EMOJI_TRIANGLE_GREEN_UP = pe(ID_TRIANGLE_GREEN_UP)
EMOJI_INSTAGRAM         = pe(ID_INSTAGRAM)
EMOJI_TWITTER_X         = pe(ID_TWITTER_X)
EMOJI_YOUTUBE_ANIM      = pe(ID_YOUTUBE_ANIM)
EMOJI_SKULL             = pe(ID_SKULL)
EMOJI_EYE_ANIM          = pe(ID_EYE_ANIM)
EMOJI_CLAP              = pe(ID_CLAP)
EMOJI_GAMEPAD           = pe(ID_GAMEPAD)
EMOJI_STAR_SMALL_ANIM   = pe(ID_STAR_SMALL_ANIM)
EMOJI_TROPHY_ANIM       = pe(ID_TROPHY_ANIM)
