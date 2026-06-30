# ─── ربات کمکی پنل ────────────────────────────────────────────────────────────
# سلف‌بات‌ها (اکانت شخصی تلگرام) نمی‌تونن مستقیم پیام دکمه‌دار بفرستن که
# callback query روش کار کنه — چون callbackQuery فقط برای پیام‌های ارسال‌شده
# از طرف یه بات فعاله.
#
# راه‌حل: یه ربات کمکی (مثل @selfnexo_helper_bot) داریم. وقتی کاربر «پنل»
# می‌نویسه، سلف پیامش رو پاک می‌کنه و از این ماژول می‌خواد که ربات کمکی
# مستقیم به همون چت پیام با بنر + دکمه بفرسته — بدون inline query.
# کلیک روی دکمه‌ها هم اینجا گرفته می‌شه و دستور روی سشن سلف کاربر اجرا می‌شه.
import os
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import config

_helper_client = None   # سینگلتون — یه بار در کل پروسس

BANNER_PATH = os.path.join(os.path.dirname(__file__), "static", "5888572687817314175.jpg")
PANEL_CAPTION = "**Self Vtr**"


def get_helper_client():
    return _helper_client


async def send_panel(chat_id: int, owner_id: int):
    """
    ربات کمکی پیام پنل رو به chat_id می‌فرسته:
      - اگه بنر وجود داشت: عکس + کپشن + دکمه‌ها
      - اگه نه: فقط متن + دکمه‌ها
    """
    if _helper_client is None or not _helper_client.is_connected():
        print("⚠️ ربات کمکی هنوز آماده نشده.")
        return

    from bot import PANEL_COMMANDS, PANEL_CAT_ROWS
    from telegram_bot import get_category_buttons

    buttons, _ = get_category_buttons(PANEL_COMMANDS, cat_rows=PANEL_CAT_ROWS)

    try:
        if os.path.exists(BANNER_PATH):
            await _helper_client.send_file(
                chat_id,
                BANNER_PATH,
                caption=PANEL_CAPTION,
                buttons=buttons,
            )
        else:
            await _helper_client.send_message(
                chat_id,
                PANEL_CAPTION,
                buttons=buttons,
            )
    except Exception as e:
        print(f"⚠️ خطا در ارسال پنل: {e}")


async def start_helper_bot():
    """راه‌اندازی ربات کمکی — فقط یک‌بار صدا زده بشه."""
    global _helper_client

    if not config.HELPER_BOT_TOKEN:
        print("⚠️ HELPER_BOT_TOKEN تنظیم نشده — ربات کمکی پنل غیرفعال.")
        return None

    if _helper_client is not None and _helper_client.is_connected():
        return _helper_client

    from bot import bot_manager, PANEL_COMMANDS, PANEL_CAT_ROWS, _execute_panel_command
    from telegram_bot import get_category_buttons, get_category_commands_buttons

    cl = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
    await cl.start(bot_token=config.HELPER_BOT_TOKEN)
    _helper_client = cl
    me = await cl.get_me()
    print(f"✅ ربات کمکی پنل آماده شد — @{me.username}")

    # ─── هندل کلیک دکمه‌ها ────────────────────────────────────────────────────
    @cl.on(events.CallbackQuery())
    async def on_callback(event):
        owner_id, entry = bot_manager.get_owner_by_tg_id(event.sender_id)
        if owner_id is None or not entry or not entry.get("client"):
            await event.answer("⛔ سلف فعالی پیدا نشد.", alert=True)
            return

        self_client = entry["client"]
        data = event.data.decode("utf-8")

        # ── noop (دکمه شماره صفحه) ─────────────────────────────────────────────
        if data == "panel_noop":
            await event.answer()
            return

        # ── برگشت به صفحه دسته‌ها ──────────────────────────────────────────────
        if data == "panel_categories":
            buttons, _ = get_category_buttons(PANEL_COMMANDS, cat_rows=PANEL_CAT_ROWS)
            await event.edit(PANEL_CAPTION, buttons=buttons)
            return

        # ── باز کردن یه دسته ───────────────────────────────────────────────────
        if data.startswith("panel_cat_"):
            idx = int(data.replace("panel_cat_", ""))
            cats = []
            for cat, _l, _c in PANEL_COMMANDS:
                if cat not in cats:
                    cats.append(cat)
            if 0 <= idx < len(cats):
                category = cats[idx]
                buttons = get_category_commands_buttons(PANEL_COMMANDS, category, page=0)
                await event.edit(f"**{category}**\nیکی از دستورات رو بزن 👇", buttons=buttons)
            else:
                await event.answer("❗ دسته نامعتبر.", alert=True)
            return

        # ── صفحه‌بندی داخل یه دسته ─────────────────────────────────────────────
        if data.startswith("panel_catpage_"):
            rest = data[len("panel_catpage_"):]
            category, _, page_str = rest.rpartition("_")
            try:
                page = int(page_str)
            except ValueError:
                page = 0
            buttons = get_category_commands_buttons(PANEL_COMMANDS, category, page=page)
            await event.edit(f"**{category}**\nیکی از دستورات رو بزن 👇", buttons=buttons)
            return

        # ── اجرای دستور ────────────────────────────────────────────────────────
        if data.startswith("panel_cmd_"):
            idx = int(data.replace("panel_cmd_", ""))
            if 0 <= idx < len(PANEL_COMMANDS):
                _, label, command_text = PANEL_COMMANDS[idx]
                await event.answer(f"⏳ {label}")
                await _execute_panel_command(self_client, owner_id, command_text)
            else:
                await event.answer("❗ دستور نامعتبر.", alert=True)
            return

    return cl
