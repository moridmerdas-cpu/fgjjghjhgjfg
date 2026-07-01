# ─── ربات کمکی پنل (Helper Bot) ──────────────────────────────────────────────
# سلف‌بات‌ها (اکانت‌های شخصی تلگرام) نمی‌تونن مستقیم پیام با دکمه‌ی شیشه‌ای
# (inline keyboard / callback) بفرستن و کلیک روش کار کنه — چون callback query
# فقط برای پیام‌هایی که از طرف یک بات ارسال شدن فعال می‌شه.
#
# راه‌حل: یک بات کمکی (مثل @selfnexo_helper_bot) می‌سازیم. وقتی کاربر توی
# سلف خودش می‌نویسه «پنل»، سلف یک inline query به این بات می‌زنه و نتیجه رو
# توی همون چت کلیک می‌کنه؛ پیام به‌صورت «via @selfnexo_helper_bot» ارسال
# می‌شه ولی روی دکمه‌هاش واقعاً کار می‌کنه، چون بات فرستنده‌ی واقعیشه.
# کلیک روی دکمه‌ها هم میاد سراغ همین بات (نه سشن سلف)، پس این فایل
# CallbackQuery رو می‌گیره و دستور مربوطه رو روی همون کلاینت سلف کاربر اجرا
# می‌کنه (بک‌اند هر دو تو یک پروسس/event loop هستن پس مستقیم صدا می‌زنیم،
# نیازی به IPC جدا نیست).

from telethon import TelegramClient, events
from telethon.sessions import StringSession
import config

_helper_client = None  # سینگلتون - فقط یک بار در کل پروسس بالا میاد


def get_helper_client():
    return _helper_client


async def start_helper_bot():
    """بات کمکی رو راه‌اندازی می‌کنه. فقط یک‌بار صدا زده بشه (مثلاً موقع بالا اومدن سرور)."""
    global _helper_client

    if not config.HELPER_BOT_TOKEN:
        print("⚠️ HELPER_BOT_TOKEN تنظیم نشده — پنل دکمه‌ای سلف غیرفعال است.")
        return None

    if _helper_client is not None and _helper_client.is_connected():
        return _helper_client

    # import داخل تابع تا از circular import با bot.py جلوگیری بشه
    from bot import bot_manager, PANEL_COMMANDS, _execute_panel_command
    from telegram_bot import get_all_commands_buttons

    cl = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
    await cl.start(bot_token=config.HELPER_BOT_TOKEN)
    _helper_client = cl
    me = await cl.get_me()
    print(f"✅ ربات کمکی پنل راه‌اندازی شد — @{me.username}")

    # ─── پاسخ به inline query (وقتی سلف داره نتیجه رو می‌گیره تا کلیک کنه) ───
    @cl.on(events.InlineQuery())
    async def on_inline(event):
        owner_id, entry = bot_manager.get_owner_by_tg_id(event.query.user_id)
        if owner_id is None:
            await event.answer(
                [event.builder.article(
                    title="⛔ غیرمجاز",
                    description="این اکانت به هیچ سلف فعالی متصل نیست.",
                    text="⛔ این پنل فقط برای سلف‌های فعال نکسو سلف در دسترسه.",
                )],
                cache_time=0,
            )
            return

        buttons = get_all_commands_buttons(PANEL_COMMANDS, page=0)
        result = event.builder.article(
            title="🎛️ پنل مدیریت دستورات",
            description="برای نمایش پنل دکمه‌ای لمس کن",
            text="🎛️ **پنل مدیریت دستورات**\nیکی از دکمه‌ها رو بزن تا دستور اجرا بشه 👇",
            buttons=buttons,
        )
        await event.answer([result], cache_time=0)

    # ─── کلیک روی دکمه‌های پنل ────────────────────────────────────────────────
    @cl.on(events.CallbackQuery())
    async def on_callback(event):
        owner_id, entry = bot_manager.get_owner_by_tg_id(event.sender_id)
        if owner_id is None or not entry or not entry.get("client"):
            await event.answer("⛔ سلف فعالی برای این اکانت پیدا نشد.", alert=True)
            return

        self_client = entry["client"]
        data = event.data.decode("utf-8")

        if data == "panel_noop":
            await event.answer()
            return

        if data == "panel_back":
            buttons = get_all_commands_buttons(PANEL_COMMANDS, page=0)
            await event.edit(
                "🎛️ **پنل مدیریت دستورات**\nیکی از دکمه‌ها رو بزن تا دستور اجرا بشه 👇",
                buttons=buttons,
            )
            return

        if data.startswith("panel_page_"):
            page = int(data.replace("panel_page_", ""))
            buttons = get_all_commands_buttons(PANEL_COMMANDS, page=page)
            await event.edit(
                "🎛️ **پنل مدیریت دستورات**\nیکی از دکمه‌ها رو بزن تا دستور اجرا بشه 👇",
                buttons=buttons,
            )
            return

        if data.startswith("panel_cmd_"):
            idx = int(data.replace("panel_cmd_", ""))
            if 0 <= idx < len(PANEL_COMMANDS):
                _, label, command_text = PANEL_COMMANDS[idx]
                await event.answer(f"⏳ در حال اجرا: {label}")
                await _execute_panel_command(self_client, owner_id, command_text)
            else:
                await event.answer("❗ دستور نامعتبر است.", alert=True)
            return

    return cl
