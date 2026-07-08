# ─── ربات کمکی پنل (Helper Bot) ──────────────────────────────────────────────
# سلف‌بات‌ها (اکانت‌های شخصی تلگرام) نمی‌تونن مستقیم پیام با دکمه‌ی شیشه‌ای
# (inline keyboard / callback) بفرستن و کلیک روش کار کنه — چون callback query
# فقط برای پیام‌هایی که از طرف یک بات ارسال شدن فعال می‌شه.
#
# راه‌حل: یک بات کمکی (مثل @selfnexo_helper_bot) می‌سازیم. وقتی کاربر توی
# سلف خودش می‌نویسه «پنل»، سلف یک inline query به این بات می‌زنه و نتیجه رو
# توی همون چت کلیک می‌کنه؛ پیام به‌صورت «via @selfnexo_helper_bot» ارسال
# می‌شه ولی روی دکمه‌هاش واقعاً کار می‌کنه، چون بات فرستنده‌ی واقعیشه.
#
# قفل مالکیت پنل:
# هر پیام inline که ساخته می‌شه، آیدی تلگرام کسی که inline query رو زده
# (یعنی صاحب پنل) به‌صورت پسوند در callback_data تمام دکمه‌ها ذخیره می‌شه.
# وقتی هرکسی (حتی در گروه) روی یکی از دکمه‌ها کلیک می‌کنه، اول چک می‌شه که
# event.sender_id (کسی که واقعاً کلیک کرده) دقیقاً همون آیدیِ ذخیره‌شده باشه؛
# اگه نبود، با یک alert رد می‌شه و هیچ دستوری اجرا نمی‌شه. یعنی پنلِ هرکس
# فقط برای خودش کار می‌کنه، حتی اگه در یک گروه مشترک ارسال شده باشه.
#
# ساختار پنل چند سطحیه:
#   سطح ۱: منوی اصلی (ساعت، حالت متن، قفل‌ها، منشی، عضویت اجباری، اتوماسیون،
#           دوست و دشمن، ابزار، هوش مصنوعی، ایموجی پرمیوم)
#   سطح ۲: آیتم‌های همون دسته (سوییچ‌های رنگی روشن/خاموش + دکمه‌های اکشن ساده)
#           و/یا دکمه‌هایی به زیرمنوهای دیگه (مثل «فونت ساعت» یا «دوست»/«دشمن»)

import io
import asyncio
import time

from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.sessions import StringSession
import config

_helper_client = None  # سینگلتون - فقط یک بار در کل پروسس بالا میاد

MAIN_TEXT = "پنل مدیریت سلف\nیک دسته را انتخاب کن"
DENIED_TEXT = "این پنل مخصوص کسی است که آن را باز کرده. دکمه‌ها برای شما فعال نیست."

# ─── بستن خودکار پنل بعد از بیکار موندن ──────────────────────────────────────
PANEL_IDLE_SECONDS = 180  # ۳ دقیقه
IDLE_CLOSED_TEXT = "پنل بعد از ۳ دقیقه بیکار موندن بسته شد."
_panel_timers = {}  # {(chat_id, message_id): asyncio.Task}
_schedule_panel_timeout_impl = None  # موقع start_helper_bot ست میشه

# ─── کش بنر پنل (عکس پروفایل + بنر) ─────────────────────────────────────────
# دانلود عکس پروفایل + ساخت بنر هر بار طول می‌کشه و اگه معطل بشه، تلگرام با خطای
# "did not answer to the callback query in time" ریکوئست اینلاین رو fail می‌کنه.
# پس نتیجه رو برای هر owner چند دقیقه کش می‌کنیم و فقط گاهی رفرش می‌کنیم.
_panel_banner_cache = {}  # {owner_id: (timestamp, raw_png_bytes, display_name, username_line)}
PANEL_BANNER_TTL = 600  # ۱۰ دقیقه


def schedule_panel_timeout(chat_id: int, message_id: int):
    """از بیرون (مثلاً bot.py، وقتی پنل تازه باز میشه) یا از داخل on_callback
    (وقتی پنل باز می‌مونه ولی داره استفاده می‌شه) صدا زده می‌شه تا تایمر
    ۳ دقیقه‌ایِ بستن خودکار reset بشه."""
    if _schedule_panel_timeout_impl is not None:
        _schedule_panel_timeout_impl(chat_id, message_id)


def _category_text(title):
    return f"{title}\nیکی از دکمه‌ها رو بزن تا روشن/خاموش بشه یا اجرا شه"


def get_helper_client():
    return _helper_client


def _split_owner_tag(data: str):
    """
    آیدی تلگرامِ صاحبِ پنل رو که به‌صورت "..._{tg_id}" ته callback_data چسبیده
    جدا می‌کنه. اگه فرمت نامعتبر بود (مثل panel_noop) None برمی‌گردونه.
    """
    body, _, tail = data.rpartition("_")
    if tail.isdigit():
        return body, int(tail)
    return data, None


async def start_helper_bot():
    """بات کمکی رو راه‌اندازی می‌کنه. فقط یک‌بار صدا زده بشه (مثلاً موقع بالا اومدن سرور)."""
    global _helper_client

    if not config.HELPER_BOT_TOKEN:
        print("⚠️ HELPER_BOT_TOKEN تنظیم نشده — پنل دکمه‌ای سلف غیرفعال است.")
        return None

    if _helper_client is not None and _helper_client.is_connected():
        return _helper_client

    # import داخل تابع تا از circular import با bot.py جلوگیری بشه
    from bot import (
        bot_manager,
        PANEL_CATEGORIES,
        build_category_menu,
        build_category_commands,
        _execute_panel_command,
    )
    from telegram_bot import get_all_commands_buttons

    cl = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
    await cl.start(bot_token=config.HELPER_BOT_TOKEN)
    _helper_client = cl
    me = await cl.get_me()
    print(f"✅ ربات کمکی پنل راه‌اندازی شد — @{me.username}")

    async def _close_panel_after_idle(chat_id, message_id):
        try:
            await asyncio.sleep(PANEL_IDLE_SECONDS)
            try:
                await cl.edit_message(chat_id, message_id, IDLE_CLOSED_TEXT, buttons=[])
            except Exception:
                try:
                    await cl.delete_messages(chat_id, message_id)
                except Exception:
                    pass
        finally:
            _panel_timers.pop((chat_id, message_id), None)

    def _do_schedule(chat_id, message_id):
        key = (chat_id, message_id)
        old = _panel_timers.get(key)
        if old and not old.done():
            old.cancel()
        _panel_timers[key] = asyncio.ensure_future(_close_panel_after_idle(chat_id, message_id))

    global _schedule_panel_timeout_impl
    _schedule_panel_timeout_impl = _do_schedule

    def _menu_buttons(owner_tg_id):
        """دکمه‌های سطح ۱ به‌صورت شبکه‌ای (۳ ستونه)، رنگی از طریق style واقعی،
        بدون ایموجی، + یک دکمه «بستن» در انتها."""
        rows = []
        row = []
        for key, title, style in build_category_menu():
            row.append(Button.inline(title, data=f"panel_cat_{key}_{owner_tg_id}", style=style or "primary"))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([Button.inline("بستن", data=f"panel_close_{owner_tg_id}", style="danger")])
        return rows

    def _back_target(category_key, owner_tg_id):
        """دکمه‌ی بازگشتِ یک دسته: اگه دسته یک parent داشته باشه به همون
        دسته‌ی والد برمی‌گرده، وگرنه به منوی اصلی."""
        cat = PANEL_CATEGORIES.get(category_key, {})
        parent = cat.get("parent")
        if parent:
            return f"panel_cat_{parent}_{owner_tg_id}"
        return f"panel_menu_{owner_tg_id}"

    def _category_buttons(owner_id, owner_tg_id, category_key, page=0):
        """دکمه‌های سطح ۲ (آیتم‌های داخل یک دسته) + دکمه‌های زیرمنو (children)
        + بازگشت، همه با پسوند مالک."""
        cat = PANEL_CATEGORIES.get(category_key, {})
        items = build_category_commands(owner_id, category_key)
        buttons = get_all_commands_buttons(
            items,
            page=page,
            prefix=f"panel_item_{category_key}_",
            page_prefix=f"panel_item_page_{category_key}_",
            owner_suffix=f"_{owner_tg_id}",
        )
        for label, child_key in cat.get("children", []):
            buttons.append([Button.inline(label, data=f"panel_cat_{child_key}_{owner_tg_id}", style="primary")])
        buttons.append([Button.inline("بازگشت", data=_back_target(category_key, owner_tg_id), style="primary")])
        return buttons

    # ─── پاسخ به inline query (وقتی سلف داره نتیجه رو می‌گیره تا کلیک کنه) ───
    @cl.on(events.InlineQuery())
    async def on_inline(event):
        try:
            await _handle_inline_query(event)
        except Exception as e:
            # ‼️ هر خطای پیش‌بینی‌نشده‌ای که اینجا رخ بده، اگه answer نشه، سلف با
            # خطای "did not answer to the callback query in time" مواجه میشه.
            # پس در هر شرایطی، حتی موقع خطا، یه جواب حداقلی و فوری می‌فرستیم.
            print(f"❌ خطای پیش‌بینی‌نشده در on_inline: {e}")
            try:
                await event.answer(
                    [event.builder.article(
                        title="خطا در بارگذاری پنل",
                        description="لطفاً دوباره تلاش کنید",
                        text="⚠️ خطایی رخ داد. لطفاً دوباره «پنل» را بفرستید.",
                    )],
                    cache_time=0,
                )
            except Exception:
                pass

    async def _handle_inline_query(event):
        owner_id, entry = bot_manager.get_owner_by_tg_id(event.query.user_id)
        if owner_id is None:
            await event.answer(
                [event.builder.article(
                    title="غیرمجاز",
                    description="این اکانت به هیچ سلف فعالی متصل نیست.",
                    text="این پنل فقط برای سلف‌های فعال نکسو سلف در دسترسه.",
                )],
                cache_time=0,
            )
            return

        owner_tg_id = event.query.user_id  # همون کسی که inline query زده = صاحب پنل

        # ─── پیام «جوین اجباری پیوی» با دکمه‌ی لینک کانال ──────────────────────
        # سلف با فرستادن این کوئری اینلاین (به‌جای send_message مستقیم که دکمه
        # نداره چون اکانتِ کاربر عادیه نه بات)، از خودِ بات کمکی می‌خواد پیام
        # آماده با دکمه بسازه؛ بعد سلف فقط نتیجه رو توی پیوی هدف کلیک می‌کنه.
        if event.query.text.startswith("forcejoin"):
            import database as _db
            join_msg = _db.get_setting(owner_id, "force_join_message",
                "⛔ برای ارسال پیام ابتدا باید در کانال‌های زیر عضو شوید.")
            channels = _db.get_force_join_channels(owner_id) if hasattr(_db, "get_force_join_channels") else []
            if not channels:
                # سازگاری با نسخه‌ی قدیمی (تک‌کاناله)
                legacy_link = _db.get_setting(owner_id, "force_join_link", "")
                if legacy_link:
                    channels = [{"title": "کانال", "link": legacy_link}]
            fj_buttons = None
            if channels:
                fj_buttons = [[Button.url(f"📢 عضویت در {c.get('title') or 'کانال'} ✅", c.get("link"))]
                              for c in channels if c.get("link")]
                if not fj_buttons:
                    fj_buttons = None
            result = event.builder.article(
                title="پیام جوین اجباری",
                description="ارسال پیام جوین اجباری با دکمه‌ی کانال‌ها",
                text=join_msg,
                buttons=fj_buttons,
            )
            await event.answer([result], cache_time=0)
            return

        buttons = _menu_buttons(owner_tg_id)

        # ─── ساخت متن مشخصات (اسم + آیدی عددی + یوزرنیم) از روی خودِ سلف ───
        self_client = entry.get("client") if entry else None
        display_name = "کاربر"
        username_line = ""
        photo_bytes = None

        cached = _panel_banner_cache.get(owner_id)
        now_ts = time.time()
        if cached and (now_ts - cached[0]) < PANEL_BANNER_TTL:
            _, raw_png, display_name, username_line = cached
            buf = io.BytesIO(raw_png)
            buf.name = "panel.png"
            photo_bytes = buf
        elif self_client is not None:
            try:
                me = await self_client.get_me()
                full_name = " ".join(p for p in [me.first_name, me.last_name] if p)
                display_name = full_name or "بدون نام"
                if me.username:
                    username_line = f"یوزرنیم: @{me.username}\n"
                try:
                    raw_buf = io.BytesIO()
                    photo = await self_client.download_profile_photo(me, file=raw_buf)
                    if photo:
                        raw_buf.seek(0)
                        from banner import generate_banner
                        banner_bytes = generate_banner(raw_buf.read(), bottom_text="self panel", bottom_sub=f"@{me.username}" if me.username else "")
                        _panel_banner_cache[owner_id] = (now_ts, banner_bytes, display_name, username_line)
                        buf = io.BytesIO(banner_bytes)
                        buf.name = "panel.png"
                        photo_bytes = buf
                except Exception:
                    photo_bytes = None
            except Exception:
                pass

        caption = (
            f"نام: {display_name}\n"
            f"آیدی عددی: {owner_tg_id}\n"
            f"{username_line}"
            f"\n{MAIN_TEXT}"
        )

        if photo_bytes is not None:
            try:
                result = await event.builder.photo(
                    file=photo_bytes,
                    text=caption,
                    buttons=buttons,
                )
            except Exception:
                result = event.builder.article(
                    title="پنل مدیریت سلف",
                    description="برای نمایش پنل دکمه‌ای لمس کن",
                    text=caption,
                    buttons=buttons,
                )
        else:
            result = event.builder.article(
                title="پنل مدیریت سلف",
                description="برای نمایش پنل دکمه‌ای لمس کن",
                text=caption,
                buttons=buttons,
            )
        # cache_time=0 تا این پنل هیچ‌وقت به‌جای کاربر دیگه از کش تلگرام serve نشه
        await event.answer([result], cache_time=0)

    # ─── کلیک روی دکمه‌های پنل ────────────────────────────────────────────────
    @cl.on(events.CallbackQuery())
    async def on_callback(event):
        data = event.data.decode("utf-8")

        if data == "panel_noop":
            await event.answer()
            return

        body, owner_tg_id = _split_owner_tag(data)
        if owner_tg_id is None:
            await event.answer("دکمه نامعتبر است.", alert=True)
            return

        # 🔒 قفل مالکیت: فقط همون کسی که پنل رو باز کرده اجازه‌ی کلیک داره
        if event.sender_id != owner_tg_id:
            await event.answer(DENIED_TEXT, alert=True)
            return

        owner_id, entry = bot_manager.get_owner_by_tg_id(event.sender_id)
        if owner_id is None or not entry or not entry.get("client"):
            await event.answer("سلف فعالی برای این اکانت پیدا نشد.", alert=True)
            return

        self_client = entry["client"]

        # هر تعاملی با پنل (باز شدن دسته، صفحه‌بندی، اجرای آیتم) تایمر ۳ دقیقه‌ای
        # بستن خودکار رو ریست می‌کنه
        schedule_panel_timeout(event.chat_id, event.message_id)

        # ─── بازگشت به منوی اصلی (لیست دسته‌ها) ────────────────────────────
        if body == "panel_menu":
            await event.edit(MAIN_TEXT, buttons=_menu_buttons(owner_tg_id))
            return

        # ─── بستن پنل ───────────────────────────────────────────────────────
        if body == "panel_close":
            old = _panel_timers.pop((event.chat_id, event.message_id), None)
            if old and not old.done():
                old.cancel()
            try:
                await event.delete()
            except Exception:
                await event.answer("پنل بسته شد.")
            return

        # ─── انتخاب یک دسته از منوی اصلی ───────────────────────────────────
        if body.startswith("panel_cat_"):
            category_key = body.replace("panel_cat_", "")
            cat = PANEL_CATEGORIES.get(category_key)
            if not cat:
                await event.answer("دسته نامعتبر است.", alert=True)
                return
            if cat.get("stub_message"):
                await event.answer(cat["stub_message"], alert=True)
                return
            # دکمه‌های تک‌عملی که مستقیم اجرا می‌شن (زیرمنو ندارن)
            direct = cat.get("direct_command")
            if direct is not None:
                if direct.startswith("INFO::"):
                    await event.answer(direct[len("INFO::"):], alert=True)
                else:
                    await event.answer(f"در حال اجرا: {cat['title']}")
                    await _execute_panel_command(self_client, owner_id, direct)
                return
            await event.edit(
                _category_text(cat["title"]),
                buttons=_category_buttons(owner_id, owner_tg_id, category_key, page=0),
            )
            return

        # ─── ورق‌زدن صفحه‌های داخل یک دسته ─────────────────────────────────
        if body.startswith("panel_item_page_"):
            # فرمت بدنه: panel_item_page_{category_key}_{page}
            rest = body.replace("panel_item_page_", "")
            category_key, _, page_str = rest.rpartition("_")
            cat = PANEL_CATEGORIES.get(category_key)
            if not cat:
                await event.answer("دسته نامعتبر است.", alert=True)
                return
            await event.edit(
                _category_text(cat["title"]),
                buttons=_category_buttons(owner_id, owner_tg_id, category_key, page=int(page_str)),
            )
            return

        # ─── کلیک روی یک آیتم داخل دسته (toggle یا action) ─────────────────
        if body.startswith("panel_item_"):
            # فرمت بدنه: panel_item_{category_key}_{idx}
            rest = body.replace("panel_item_", "")
            category_key, _, idx_str = rest.rpartition("_")
            cat = PANEL_CATEGORIES.get(category_key)
            if not cat:
                await event.answer("دسته نامعتبر است.", alert=True)
                return

            items = build_category_commands(owner_id, category_key)
            idx = int(idx_str)
            if not (0 <= idx < len(items)):
                await event.answer("دستور نامعتبر است.", alert=True)
                return

            _, label, command_text, _style = items[idx]

            # ─── دکمه‌های فقط-اطلاع‌رسانی (مثل ماشین‌حساب/ترجمه) ────────────
            # این‌ها نیاز به ورودی متنی دارن، پس به‌جای اجرا روی سلف، فقط یک
            # توضیح کوتاه (toast) نشون داده می‌شه.
            if command_text.startswith("INFO::"):
                await event.answer(command_text[len("INFO::"):], alert=True)
                return

            await event.answer(f"در حال اجرا: {label}")
            await _execute_panel_command(self_client, owner_id, command_text)

            # بعد از اجرا، همون دسته رو با وضعیت/رنگ تازه دوباره رسم می‌کنیم
            page = idx // 8  # باید هم‌راستا با PANEL_PAGE_SIZE در telegram_bot.py باشه
            try:
                await event.edit(
                    _category_text(cat["title"]),
                    buttons=_category_buttons(owner_id, owner_tg_id, category_key, page=page),
                )
            except Exception:
                pass
            return

        await event.answer("دکمه نامعتبر است.", alert=True)

    return cl
