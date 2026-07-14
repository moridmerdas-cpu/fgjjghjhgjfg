# meowie_game.py
# ─────────────────────────────────────────────────────────────────────────────
# ماژول مدیریت خودکار بازی Meowie (@MeowieeeQBot) برای سلف‌بات.
#
# این فایل عمداً مستقل و ماژولار نوشته شده تا با کمترین تغییر توی bot.py
# قابل قلاب‌شدن (wire) باشه. سه چیز به بیرون می‌ده:
#
#   1) SETTING_DEFAULTS_EXTRA   → باید با SETTING_DEFAULTS توی
#      database_supabase.py مرج بشه (کلیدهای پیش‌فرض تنظیمات این ماژول).
#
#   2) register_handlers(cl, owner_id)  → داخل _register_handlers() در
#      bot.py صدا زده می‌شه؛ دو هندلر روی کلاینت سلف ثبت می‌کنه:
#        - رصد پیام دستیِ «میو» خودِ کاربر برای بایند کردن گروه بازی
#        - رصد پیام‌های ورودی از @MeowieeeQBot برای پارس امتیاز/کول‌داون
#          و کلیک خودکار دکمه‌ی «بده پیشی بخوره»
#
#   3) meowie_loop(cl, owner_id)  → یک تسک پس‌زمینه (asyncio) که باید کنار
#      بقیه‌ی حلقه‌ها (_clock_loop, _scheduler_loop, ...) با
#      asyncio.ensure_future(...) استارت و در پایان cancel بشه. این حلقه
#      طبق next_meow_ts/next_fish_ts ذخیره‌شده، دوباره «میو»/«ماهی» می‌فرسته.
#
#   4) handle_panel_command(text, owner_id, ss, edit) -> bool  → برای قلاب
#      شدن به دیسپچرِ متنیِ _handle_command؛ اگه True برگردوند یعنی دستور
#      مربوط به این ماژول بود و پردازش شد.
#
#   5) PANEL_CATEGORY  → دیکشنری آماده برای اضافه‌کردن به PANEL_CATEGORIES
#      (پنل دکمه‌ای) با کلید "meowie_game".
#
# نکته‌ی مهم درباره‌ی محدودیت‌های اخلاقی: این ماژول فقط پیام‌های متنیِ
# ساده (میو/ماهی) رو طبق تایمر اعلام‌شده توسط خودِ ربات بازی ارسال می‌کنه؛
# هیچ تلاشی برای اسپم بیشتر از چیزی که ربات بازی اجازه می‌ده، دور زدن
# کول‌داون، یا حمله/سوءاستفاده از حساب‌های دیگه انجام نمی‌ده.
# ─────────────────────────────────────────────────────────────────────────────

import re
import time
import asyncio

from telethon import events

# ─── تنظیمات ثابت ───────────────────────────────────────────────────────────
MEOWIE_BOT_USERNAME = "MeowieeeQBot"   # بدون @

# فاصله‌ی امن پیش‌فرض بین دو ارسال، وقتی هنوز پاسخی از ربات نرسیده
# (صرفاً یک شبکه‌ی ایمنی در برابر لوپ سریع، نه دور زدن کول‌داون واقعی)
_FALLBACK_RETRY_SECONDS = 20

# کلیدهای تنظیمات این ماژول + مقدار پیش‌فرض؛ توی database_supabase.py
# باید با SETTING_DEFAULTS مرج بشه (init_user_settings خودکار این‌ها رو
# هم برای کاربر تازه مقداردهی می‌کنه).
SETTING_DEFAULTS_EXTRA = {
    "meowie_game_active": "0",       # وضعیت روشن/خاموش کلی قابلیت
    "meowie_game_group_id": "",      # آیدی عددی گروه بازی (بعد از بایند شدن)
    "meowie_next_meow_ts": "0",      # یونیکس‌تایمِ زمان مجاز بعدی برای «میو»
    "meowie_next_fish_ts": "0",      # یونیکس‌تایمِ زمان مجاز بعدی برای «ماهی»
}

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

# کاراکترهای نامرئیِ جهت‌دهی (LRM/RLM/LRE/RLE/PDF/isolates/ZWSP) که تلگرام یا
# کیبورد گوشی گاهی بین رقم‌های انگلیسیِ زمان (مثل «5:00») و متن فارسی اطراف‌شون
# درج می‌کنه. اگه حذف نشن، رجکس (\d+):(\d+) به‌خاطر همین کاراکترهای نامرئی
# بین رقم و «:» شکست می‌خوره و زمان اصلاً پارس نمی‌شه — این شایع‌ترین دلیلِ
# «تشخیص داد ولی دوباره خودکار انجام نشد» هست.
_INVISIBLE_RE = re.compile("[\u200b\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def _clean(s: str) -> str:
    s = (s or "").translate(_PERSIAN_DIGITS)
    s = _INVISIBLE_RE.sub("", s)
    return s


def _normalize_digits(s: str) -> str:
    return _clean(s)


# ─── پنل دکمه‌ای ─────────────────────────────────────────────────────────────
PANEL_CATEGORY = {
    "title": "مدیریت بازی میویی",
    "menu_style": "primary",
    "toggles": [
        ("meowie_game_active", "بازی میویی", "بازی میویی روشن", "بازی میویی خاموش"),
    ],
    "actions": [
        (
            "📖 راهنما",
            "INFO::🐾 دکمه‌ی بالا رو روشن کن. بعد داخل گروه بازی یک‌بار دستی "
            "بنویس «میو» تا گروه ذخیره بشه. از اون به بعد میو/ماهی خودکاره. "
            "برای عوض کردن گروه، «ریست گروه بازی میویی» رو بفرست.",
        ),
        ("🗑 حذف گروه میویی", "حذف گروه میویی"),
    ],
}


# ─── دیسپچر دستورهای متنی (برای _handle_command) ────────────────────────────
def handle_panel_command(text: str, owner_id: int, ss, gs, edit_coro_factory) -> bool:
    """
    اگه text یکی از دستورهای متنیِ این ماژول بود، پردازشش می‌کنه و True
    برمی‌گردونه. edit_coro_factory یک تابعِ async(t) هست (همون `edit` محلیِ
    _handle_command) که پیام نتیجه رو نمایش می‌ده. فراخوان باید نتیجه رو
    await کنه اگه True برگشت و coroutine ای برگردونده شده باشه.
    این تابع خودش async نیست تا قلاب‌کردنش ساده باشه؛ کالر باید به این شکل
    صدا بزنه:

        handled, coro = meowie_game.handle_panel_command(text, owner_id, ss, gs, edit)
        if handled:
            await coro
            return  (در بدنه‌ی _handle_command به شکل elif ادامه پیدا می‌کنه)
    """
    if text == "بازی میویی روشن":
        ss("meowie_game_active", "1")
        if not gs("meowie_game_group_id", ""):
            msg = (
                "🐱 بازی میویی روشن شد.\n"
                "📍 حالا داخل گروهی که می‌خوای بازی توش انجام بشه، یک‌بار دستی "
                "بنویس «میو» تا همون گروه به‌عنوان گروه بازی ثبت بشه."
            )
        else:
            msg = "🐱 بازی میویی روشن شد و روی گروه قبلاً ثبت‌شده ادامه پیدا می‌کنه."
        return True, edit_coro_factory(msg)

    if text == "بازی میویی خاموش":
        ss("meowie_game_active", "0")
        return True, edit_coro_factory("🐱 بازی میویی خاموش شد.")

    if text in ("ریست گروه بازی میویی", "حذف گروه میویی"):
        ss("meowie_game_group_id", "")
        return True, edit_coro_factory(
            "🗑 گروه بازی میویی حذف شد. دفعه‌ی بعد که «میو» رو داخل هر "
            "گروهی (دستی) بنویسی، همون گروه به‌عنوان گروه جدید ثبت می‌شه."
        )

    return False, None


# ─── هندلرهای Telethon (برای _register_handlers) ────────────────────────────
def register_handlers(cl, owner_id: int, db):
    """
    دو هندلر روی کلاینت سلفِ owner_id ثبت می‌کنه. db همون ماژول database
    (یا database_supabase) پروژه‌ست که get_setting/set_setting داره.
    """

    def gs(key, default=None):
        return db.get_setting(owner_id, key, default)

    def ss(key, value):
        db.set_setting(owner_id, key, value)

    # 1) پیام دستیِ «میو» خودِ کاربر → بایند کردن گروه بازی (فقط یک‌بار)
    @cl.on(events.NewMessage(outgoing=True, pattern=r"^\s*میو\s*$"))
    async def _meowie_bind_group(event):
        try:
            if gs("meowie_game_active", "0") != "1":
                return
            if gs("meowie_game_group_id", ""):
                return  # قبلاً بایند شده
            if not event.is_group:
                return
            ss("meowie_game_group_id", str(event.chat_id))
            # ⏳ به‌جای صفر، یه فاصله‌ی کوتاه (grace) می‌ذاریم؛ چون همین «میو»یی
            # که کاربر الان دستی فرستاد قبلاً کول‌داون رو مصرف کرده و بات
            # میویی چند لحظه دیگه با زمان واقعی جواب می‌ده. اگه این‌جا صفر
            # می‌ذاشتیم، حلقه‌ی پس‌زمینه ممکن بود قبل از رسیدن همون جواب،
            # یه «میو»ی تکراری و زودهنگام بفرسته.
            ss("meowie_next_meow_ts", str(time.time() + 15))
            ss("meowie_next_fish_ts", str(time.time() + 15))
            try:
                await event.reply(
                    "🐾 این گروه به‌عنوان گروه بازی میویی ثبت شد. از این به بعد "
                    "میو/ماهی به‌صورت خودکار مدیریت می‌شه."
                )
            except Exception:
                pass
        except Exception as e:
            print(f"❌ [{owner_id}] خطا در بایند گروه بازی میویی: {e}")

    # 2) پیام‌های ورودی از @MeowieeeQBot داخل گروه ثبت‌شده — هم پیام‌های
    # تازه (NewMessage) و هم پیام‌هایی که ادیت می‌شن (MessageEdited).
    #
    # چرا MessageEdited هم لازمه؟ چون ربات بازی معمولاً اول پیام رو بدون
    # دکمه می‌فرسته (مثلاً حالت «در حال گرفتن ماهی...») و چند ثانیه بعد
    # (طبق مشاهده‌ی شما ۱۰ تا ۱۵ ثانیه) همون پیام رو ادیت می‌کنه و دکمه‌ی
    # «بده پیشی بخوره» رو بهش اضافه می‌کنه. اگه فقط NewMessage گوش بدیم،
    # دکمه‌ای که بعداً با ادیت اضافه شده رو اصلاً نمی‌بینیم.
    async def _process(event):
        try:
            if gs("meowie_game_active", "0") != "1":
                return

            group_id_raw = gs("meowie_game_group_id", "")
            if not group_id_raw:
                return
            try:
                if event.chat_id != int(group_id_raw):
                    return
            except (TypeError, ValueError):
                return

            sender = await event.get_sender()
            sender_username = (getattr(sender, "username", "") or "").lower()
            if sender_username != MEOWIE_BOT_USERNAME.lower():
                return

            text = event.raw_text or ""
            clean_text = _clean(text)
            now = time.time()

            print(f"🐾 [{owner_id}] پیام از {MEOWIE_BOT_USERNAME} ({'edit' if isinstance(event, events.MessageEdited.Event) else 'new'}): {text[:200]!r}")

            # (الف) پیام صید ماهی که نیاز به تصمیم داره — دکمه‌ی
            # «بده پیشی بخوره» رو پیدا و کلیک کن. این چک باید همیشه اول
            # از همه باشه، چون دکمه معمولاً با یه ادیت دیرتر ظاهر می‌شه.
            buttons = getattr(event.message, "buttons", None)
            if buttons:
                for row in buttons:
                    for btn in row:
                        btn_text = getattr(btn, "text", "") or ""
                        if "بده پیشی بخوره" in btn_text:
                            print(f"🎣 [{owner_id}] دکمه‌ی «{btn_text}» پیدا شد — در حال کلیک...")
                            try:
                                await event.message.click(text=btn_text)
                                print(f"✅ [{owner_id}] کلیک دکمه‌ی ماهی موفق بود.")
                            except Exception as e:
                                print(f"❌ [{owner_id}] خطا در کلیک دکمه‌ی ماهی: {e}")
                            return

            # (ب) تایید خورده‌شدن ماهی توسط پیشی → دوباره «ماهی» بفرست
            if "پیشی خوردش" in clean_text:
                ss("meowie_next_fish_ts", "0")
                print(f"🐟 [{owner_id}] پیشی ماهی رو خورد — دوباره «ماهی» فرستاده می‌شه.")
                try:
                    await cl.send_message(event.chat_id, "ماهی")
                except Exception as e:
                    print(f"❌ [{owner_id}] خطا در ارسال مجدد ماهی: {e}")
                return

            # (ج) پیام‌های کول‌داون/امتیاز میو یا ماهی — به‌جای تکیه به
            # حرف‌اضافه‌ی «بعد از»/«باید» (که جهتش وابسته به نسخه‌ی ربات و
            # می‌تونه برعکس باشه)، فقط MM:SS رو پیدا می‌کنیم و بر اساس
            # اسم موضوع («ماهی» در برابر «میو») تصمیم می‌گیریم که این زمان
            # مال کدوم تایمره. «ماهی» رو اول چک می‌کنیم چون احتمالاً «میو»
            # به‌عنوان برندینگ ربات (Meowie) توی خیلی از پیام‌ها هست، ولی
            # «ماهی» فقط توی پیام‌های واقعاً مربوط به ماهی میاد.
            #
            # نکته: این تشخیص کاملاً مستقل از اینه که چه چیزی باعث این پاسخ
            # شده — چه حلقه‌ی خودکار «میو»/«ماهی» فرستاده باشه، چه خودِ
            # کاربر دستی نوشته باشه. یعنی اگه کاربر خودش وسط کار «میو» یا
            # «ماهی» بنویسه و ربات یه زمانِ متفاوت از چیزی که قبلاً ذخیره
            # کرده بودیم برگردونه، همین‌جا مقدار ذخیره‌شده رو با مقدار
            # واقعیِ جدید عوض می‌کنیم (فقط اگه واقعاً فرق داشته باشه).
            m = re.search(r"(\d+):(\d+)", clean_text)
            if m:
                secs = int(m.group(1)) * 60 + int(m.group(2))
                new_ts = now + secs
                if "ماهی" in clean_text:
                    old_ts = float(gs("meowie_next_fish_ts", "0") or "0")
                    if abs(new_ts - old_ts) >= 1:
                        ss("meowie_next_fish_ts", str(new_ts))
                        print(f"⏱️ [{owner_id}] (تشخیص: ماهی) تایمر عوض شد: {old_ts:.0f} → {new_ts:.0f} (+{secs}s)")
                    else:
                        print(f"⏱️ [{owner_id}] (تشخیص: ماهی) تایمر فرقی نکرده، عوض نشد.")
                elif "میو" in clean_text:
                    old_ts = float(gs("meowie_next_meow_ts", "0") or "0")
                    if abs(new_ts - old_ts) >= 1:
                        ss("meowie_next_meow_ts", str(new_ts))
                        print(f"⏱️ [{owner_id}] (تشخیص: میو) تایمر عوض شد: {old_ts:.0f} → {new_ts:.0f} (+{secs}s)")
                    else:
                        print(f"⏱️ [{owner_id}] (تشخیص: میو) تایمر فرقی نکرده، عوض نشد.")
                else:
                    print(f"❔ [{owner_id}] زمان {secs} ثانیه پیدا شد ولی معلوم نشد میو مال میو هست یا ماهی — پیام رو بالا ببین.")
                return

            print(f"❔ [{owner_id}] پیام از {MEOWIE_BOT_USERNAME} با هیچ الگویی مچ نشد (بالا رو ببین).")

        except Exception as e:
            print(f"❌ [{owner_id}] خطا در پردازش پیام بازی میویی: {e}")

    @cl.on(events.NewMessage(incoming=True))
    async def _meowie_incoming(event):
        await _process(event)

    @cl.on(events.MessageEdited(incoming=True))
    async def _meowie_edited(event):
        await _process(event)


# ─── حلقه‌ی پس‌زمینه (برای asyncio.ensure_future کنار بقیه‌ی لوپ‌ها) ─────────
async def meowie_loop(cl, owner_id: int, db):
    """
    هر چند ثانیه چک می‌کنه که آیا وقتِ ارسال دوباره‌ی «میو» یا «ماهی» رسیده؛
    اگه رسیده باشه می‌فرسته. زمان‌بندی واقعی از روی پاسخ خودِ ربات بازی
    (توسط register_handlers) به‌روزرسانی می‌شه، این حلقه فقط trigger می‌کنه.
    """
    while True:
        try:
            if db.get_setting(owner_id, "meowie_game_active", "0") != "1":
                await asyncio.sleep(5)
                continue

            group_id_raw = db.get_setting(owner_id, "meowie_game_group_id", "")
            if not group_id_raw:
                await asyncio.sleep(5)
                continue

            try:
                group_id = int(group_id_raw)
            except ValueError:
                await asyncio.sleep(5)
                continue

            now = time.time()

            next_meow = float(db.get_setting(owner_id, "meowie_next_meow_ts", "0") or "0")
            if now >= next_meow:
                print(f"🐾 [{owner_id}] زمان میو رسید ({now:.0f} >= {next_meow:.0f}) — ارسال «میو».")
                try:
                    await cl.send_message(group_id, "میو")
                except Exception as e:
                    print(f"❌ [{owner_id}] خطا در ارسال میو: {e}")
                db.set_setting(owner_id, "meowie_next_meow_ts", str(now + _FALLBACK_RETRY_SECONDS))

            next_fish = float(db.get_setting(owner_id, "meowie_next_fish_ts", "0") or "0")
            if now >= next_fish:
                print(f"🐟 [{owner_id}] زمان ماهی رسید ({now:.0f} >= {next_fish:.0f}) — ارسال «ماهی».")
                try:
                    await cl.send_message(group_id, "ماهی")
                except Exception as e:
                    print(f"❌ [{owner_id}] خطا در ارسال ماهی: {e}")
                db.set_setting(owner_id, "meowie_next_fish_ts", str(now + _FALLBACK_RETRY_SECONDS))

            await asyncio.sleep(5)
        except Exception as e:
            print(f"خطا در meowie_loop ({owner_id}): {e}")
            await asyncio.sleep(15)
