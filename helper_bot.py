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
# ساختار پنل دو سطحیه:
#   سطح ۱: منوی دسته‌ها (اتوماسیون، فونت و قالب‌بندی، اصلی، لیست‌ها، منشی،
#           امنیت، جوین اجباری، ابزار، اسپم، پیام)
#   سطح ۲: آیتم‌های همون دسته (سوییچ‌های رنگی روشن/خاموش + دکمه‌های اکشن ساده)

import io

from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.sessions import StringSession
import config

_helper_client = None  # سینگلتون - فقط یک بار در کل پروسس بالا میاد

MAIN_TEXT = "پنل مدیریت سلف\nیک دسته را انتخاب کن"
DENIED_TEXT = "این پنل مخصوص کسی است که آن را باز کرده. دکمه‌ها برای شما فعال نیست."


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

    def _menu_buttons(owner_tg_id):
        """دکمه‌های سطح ۱ (لیست دسته‌ها)، رنگی از طریق style واقعی، بدون ایموجی."""
        rows = []
        for key, title, _ in build_category_menu():
            rows.append([Button.inline(title, data=f"panel_cat_{key}_{owner_tg_id}", style="primary")])
        return rows

    def _category_buttons(owner_id, owner_tg_id, category_key, page=0):
        """دکمه‌های سطح ۲ (آیتم‌های داخل یک دسته) + بازگشت به منو، همه با پسوند مالک."""
        items = build_category_commands(owner_id, category_key)
        buttons = get_all_commands_buttons(
            items,
            page=page,
            prefix=f"panel_item_{category_key}_",
            page_prefix=f"panel_item_page_{category_key}_",
            owner_suffix=f"_{owner_tg_id}",
        )
        buttons.append([Button.inline("بازگشت به منو", data=f"panel_menu_{owner_tg_id}", style="primary")])
        return buttons

    # ─── پاسخ به inline query (وقتی سلف داره نتیجه رو می‌گیره تا کلیک کنه) ───
    @cl.on(events.InlineQuery())
    async def on_inline(event):
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
        buttons = _menu_buttons(owner_tg_id)

        # ─── ساخت متن مشخصات (اسم + آیدی عددی + یوزرنیم) از روی خودِ سلف ───
        self_client = entry.get("client") if entry else None
        display_name = "کاربر"
        username_line = ""
        photo_bytes = None

        if self_client is not None:
            try:
                me = await self_client.get_me()
                full_name = " ".join(p for p in [me.first_name, me.last_name] if p)
                display_name = full_name or "بدون نام"
                if me.username:
                    username_line = f"یوزرنیم: @{me.username}\n"
                try:
                    buf = io.BytesIO()
                    photo = await self_client.download_profile_photo(me, file=buf)
                    if photo:
                        buf.seek(0)
                        buf.name = "profile.jpg"
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
            result = await event.builder.photo(
                file=photo_bytes,
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

        # ─── بازگشت به منوی اصلی (لیست دسته‌ها) ────────────────────────────
        if body == "panel_menu":
            await event.edit(MAIN_TEXT, buttons=_menu_buttons(owner_tg_id))
            return

        # ─── انتخاب یک دسته از منوی اصلی ───────────────────────────────────
        if body.startswith("panel_cat_"):
            category_key = body.replace("panel_cat_", "")
            cat = PANEL_CATEGORIES.get(category_key)
            if not cat:
                await event.answer("دسته نامعتبر است.", alert=True)
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

            _, label, command_text = items[idx]
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
