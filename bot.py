# ===================== NexoSelf • bot.py =====================
# هندلرهای selfbot و پنل مدیریت
# این فایل توسط bot_manager.py و helper_bot.py import می‌شه
#
# قابلیت‌ها:
#   • دشمن / فحش / بلاک / سکوت پیوی
#   • عشق / ری‌اکت
#   • منشی هوشمند / AFK
#   • پاسخ‌دهی هوشمند با DeepSeek AI (آفلاین)
#   • ساعت در نام / بیو
#   • تاپینگ / بولد
#   • اسپم، ابزار، انیمیشن
#   • PANEL_CATEGORIES برای پنل دکمه‌ای helper_bot
# =====================================================================

from __future__ import annotations

import asyncio
import json
import os
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import database as db
from ai_reply import (
    handle_ai_autoreply,
    is_ai_enabled,
    get_ai_context,
    set_ai_context,
    toggle_ai,
)
from telethon import TelegramClient, events, functions, types


# ─── ثابت‌های کش در حافظه ───────────────────────────────────────────────────
# برای هر owner_id یک دیکشنری در حافظه نگه می‌داریم تا هر بار به دیتابیس نزنیم
_STATE: Dict[int, Dict[str, Any]] = {}   # تنظیمات ساده (True/False/str)
_LISTS: Dict[int, Dict[str, set]] = {}   # لیست‌های مجموعه‌ای (enemies, love, ...)
_MAPS:  Dict[int, Dict[str, dict]] = {}  # نگاشت‌ها (react_map)


# ─── ابزارهای دیتابیس ───────────────────────────────────────────────────────
def _st(owner_id: int) -> Dict[str, Any]:
    """دیکشنری state یک کاربر را برمی‌گردونه (از کش یا دیتابیس)."""
    if owner_id not in _STATE:
        _STATE[owner_id] = {}
    return _STATE[owner_id]


def _ls(owner_id: int) -> Dict[str, set]:
    if owner_id not in _LISTS:
        _LISTS[owner_id] = {}
    return _LISTS[owner_id]


def _mp(owner_id: int) -> Dict[str, dict]:
    if owner_id not in _MAPS:
        _MAPS[owner_id] = {}
    return _MAPS[owner_id]


def _get_flag(owner_id: int, key: str, default: bool = False) -> bool:
    st = _st(owner_id)
    if key not in st:
        st[key] = db.get_setting(owner_id, key, "1" if default else "0") == "1"
    return st[key]


def _set_flag(owner_id: int, key: str, value: bool):
    _st(owner_id)[key] = value
    db.set_setting(owner_id, key, "1" if value else "0")


def _toggle_flag(owner_id: int, key: str, default: bool = False) -> bool:
    new = not _get_flag(owner_id, key, default)
    _set_flag(owner_id, key, new)
    return new


def _get_str(owner_id: int, key: str, default: str = "") -> str:
    st = _st(owner_id)
    if key not in st:
        st[key] = db.get_setting(owner_id, key, default) or default
    return st[key]


def _set_str(owner_id: int, key: str, value: str):
    _st(owner_id)[key] = value
    db.set_setting(owner_id, key, value)


def _get_list(owner_id: int, key: str) -> set:
    ls = _ls(owner_id)
    if key not in ls:
        raw = db.get_setting(owner_id, key, "[]")
        try:
            ls[key] = set(json.loads(raw))
        except Exception:
            ls[key] = set()
    return ls[key]


def _save_list(owner_id: int, key: str):
    ls = _ls(owner_id)
    db.set_setting(owner_id, key, json.dumps(list(ls.get(key, set()))))


def _get_map(owner_id: int, key: str) -> dict:
    mp = _mp(owner_id)
    if key not in mp:
        raw = db.get_setting(owner_id, key, "{}")
        try:
            mp[key] = json.loads(raw)
        except Exception:
            mp[key] = {}
    return mp[key]


def _save_map(owner_id: int, key: str):
    mp = _mp(owner_id)
    db.set_setting(owner_id, key, json.dumps(mp.get(key, {})))


# ─── ابزارهای کمکی ──────────────────────────────────────────────────────────
def fc(text: str) -> str:
    return f"`{text}`"


async def safe_edit(event, text: str):
    try:
        await event.edit(text)
    except Exception:
        try:
            await event.respond(text)
        except Exception:
            pass


# ─── لیست فحش پیش‌فرض ────────────────────────────────────────────────────────
BASE_INSULTS = [
    "برو بابا",
    "خاک بر سرت",
    "دهنتو ببند",
    "گمشو",
    "بی‌ادب",
    "ادب داشته باش",
]


def _get_insults(owner_id: int) -> list:
    raw = db.get_setting(owner_id, "custom_insults", "[]")
    try:
        extra = json.loads(raw)
    except Exception:
        extra = []
    return BASE_INSULTS + extra


# ═══════════════════════════════════════════════════════════════════════════════
#  PANEL_CATEGORIES — پنل دکمه‌ای helper_bot
#
#  هر دسته: {"title": "...", "commands": [(key, label, command, style), ...]}
#  style: "success"=سبز(روشن), "danger"=قرمز(خاموش), "primary"=آبی(اکشن), None=بی‌رنگ
# ═══════════════════════════════════════════════════════════════════════════════
PANEL_CATEGORIES: Dict[str, Any] = {
    "automation": {
        "title": "اتوماسیون",
        "commands": [
            ("clock_name",  "ساعت در نام",       "toggle:clock_name",  None),
            ("clock_bio",   "ساعت در بیو",        "toggle:clock_bio",   None),
            ("typing",      "تاپینگ همیشگی",      "toggle:typing",      None),
            ("bold",        "پیام‌های بولد",       "toggle:bold",        None),
            ("autoread",    "خودکارخوانی",         "toggle:autoread",    None),
            ("log_pm",      "لاگ پیوی",            "toggle:log_pm",      None),
        ],
    },
    "secretary": {
        "title": "منشی و پاسخ خودکار",
        "commands": [
            ("secretary",   "منشی هوشمند",         "toggle:secretary",   None),
            ("afk",         "حالت AFK",             "toggle:afk",         None),
            ("ai_autoreply","پاسخ DeepSeek AI",     "toggle:ai_autoreply",None),
            ("set_sec_txt", "تنظیم متن منشی",       "action:set_sec_txt", "primary"),
            ("set_afk_txt", "تنظیم متن AFK",        "action:set_afk_txt", "primary"),
            ("ai_context",  "تنظیم اطلاعات AI",    "action:ai_context",  "primary"),
            ("ai_status",   "وضعیت AI",             "action:ai_status",   "primary"),
        ],
    },
    "lists": {
        "title": "لیست‌ها",
        "commands": [
            ("pm_silence_all", "سکوت پیوی همگانی", "toggle:pm_silence_all", None),
            ("enemy_list",     "لیست دشمن",         "action:enemy_list",     "primary"),
            ("love_list",      "لیست عشق",           "action:love_list",      "primary"),
            ("block_list",     "لیست بلاک",          "action:block_list",     "primary"),
            ("clear_enemies",  "پاکسازی دشمن‌ها",   "action:clear_enemies",  "danger"),
            ("clear_blocks",   "پاکسازی بلاک‌ها",   "action:clear_blocks",   "danger"),
        ],
    },
    "safety": {
        "title": "امنیت",
        "commands": [
            ("anti_forward", "ضد فوروارد پیوی",    "toggle:anti_forward",  None),
            ("anti_link",    "ضد لینک پیوی",        "toggle:anti_link",     None),
        ],
    },
    "tools": {
        "title": "ابزار",
        "commands": [
            ("ping",       "پینگ سلف",             "action:ping",        "primary"),
            ("del_chat",   "دیلیت چت فعلی",        "action:del_chat",    "danger"),
            ("leave_grps", "ترک همه گروه‌ها",      "action:leave_grps",  "danger"),
            ("leave_chns", "ترک همه چنل‌ها",       "action:leave_chns",  "danger"),
        ],
    },
    "spam": {
        "title": "اسپم",
        "commands": [
            ("spam40",  "اسپم ۴۰ بار",    "action:spam40",   "warning"),
            ("spam100", "اسپم ۱۰۰ بار",   "action:spam100",  "warning"),
        ],
    },
}


# ─── ساختار دو سطحی پنل ─────────────────────────────────────────────────────
def build_category_menu() -> List[Tuple[str, str, Any]]:
    """لیست دسته‌ها — (key, title, _) — برای سطح اول پنل."""
    return [(k, v["title"], None) for k, v in PANEL_CATEGORIES.items()]


def build_category_commands(owner_id: int, category_key: str) -> List[Tuple]:
    """
    آیتم‌های یک دسته با وضعیت رنگی فعلی.
    هر آیتم: (key, label, command_text, style)
    style = "success" (روشن/سبز) یا "danger" (خاموش/قرمز) برای toggle‌ها
    """
    cat = PANEL_CATEGORIES.get(category_key)
    if not cat:
        return []

    result = []
    _toggle_states = {
        "clock_name":      ("clock_name",    "ساعت در نام"),
        "clock_bio":       ("clock_bio",     "ساعت در بیو"),
        "typing":          ("typing",        "تاپینگ همیشگی"),
        "bold":            ("bold_on",       "پیام‌های بولد"),
        "autoread":        ("autoread",      "خودکارخوانی"),
        "log_pm":          ("log_pm",        "لاگ پیوی"),
        "secretary":       ("secretary",     "منشی هوشمند"),
        "afk":             ("afk",           "حالت AFK"),
        "ai_autoreply":    ("ai_autoreply",  "پاسخ DeepSeek AI"),
        "pm_silence_all":  ("pm_silence_all","سکوت پیوی همگانی"),
        "anti_forward":    ("anti_forward",  "ضد فوروارد پیوی"),
        "anti_link":       ("anti_link",     "ضد لینک پیوی"),
    }

    for (key, label, command, _style) in cat["commands"]:
        if command.startswith("toggle:"):
            flag_key = command.replace("toggle:", "")
            # برای ai_autoreply از ماژول ai_reply استفاده می‌کنیم
            if flag_key == "ai_autoreply":
                is_on = is_ai_enabled(owner_id)
            else:
                is_on = _get_flag(owner_id, flag_key)
            style = "success" if is_on else "danger"
            state_txt = "روشن" if is_on else "خاموش"
            result.append((key, f"{label} — {state_txt}", command, style))
        else:
            result.append((key, label, command, "primary"))

    return result


# ─── اجرای دستور پنل ─────────────────────────────────────────────────────────
async def _execute_panel_command(client: TelegramClient, owner_id: int, command_text: str):
    """وقتی کاربر روی دکمه‌ای کلیک می‌کنه این تابع دستور را اجرا می‌کنه."""

    # ─── toggle ──────────────────────────────────────────────────────────────
    if command_text.startswith("toggle:"):
        flag = command_text.replace("toggle:", "")

        if flag == "ai_autoreply":
            new = toggle_ai(owner_id)
            msg = f"[AI] پاسخ DeepSeek {'روشن' if new else 'خاموش'} شد."
        else:
            new = _toggle_flag(owner_id, flag)
            labels = {
                "clock_name":    ("ساعت در نام",       "روشن", "خاموش"),
                "clock_bio":     ("ساعت در بیو",        "روشن", "خاموش"),
                "typing":        ("تاپینگ",             "روشن", "خاموش"),
                "bold_on":       ("بولد",               "فعال", "غیرفعال"),
                "autoread":      ("خودکارخوانی",        "روشن", "خاموش"),
                "log_pm":        ("لاگ پیوی",           "روشن", "خاموش"),
                "secretary":     ("منشی هوشمند",        "روشن", "خاموش"),
                "afk":           ("حالت AFK",           "روشن", "خاموش"),
                "pm_silence_all":("سکوت پیوی همگانی",  "فعال", "غیرفعال"),
                "anti_forward":  ("ضد فوروارد",         "فعال", "غیرفعال"),
                "anti_link":     ("ضد لینک",            "فعال", "غیرفعال"),
            }
            info = labels.get(flag, (flag, "روشن", "خاموش"))
            msg = f"[پنل] {info[0]} {info[1] if new else info[2]} شد."

        await client.send_message("me", msg)
        return

    # ─── actions ─────────────────────────────────────────────────────────────
    if command_text == "action:ai_status":
        enabled = is_ai_enabled(owner_id)
        context = get_ai_context(owner_id)
        preview = context[:250] + "..." if len(context) > 250 else context
        await client.send_message(
            "me",
            f"[AI] وضعیت:\n"
            f"پاسخ خودکار: {'روشن' if enabled else 'خاموش'}\n\n"
            f"اطلاعات / زمینه:\n{preview or '(تنظیم نشده)'}"
        )
        return

    if command_text == "action:ai_context":
        await client.send_message(
            "me",
            "[AI] برای تنظیم اطلاعات، اینجا در چت خودت بنویس:\n\n"
            "ai_context: [اطلاعات شما]\n\n"
            "نمونه:\n"
            "ai_context: قیمت گوشی Samsung A55: 18 میلیون. iPhone 15: 45 میلیون. "
            "فروشگاه در تهران، پاسداران است."
        )
        return

    if command_text == "action:set_sec_txt":
        await client.send_message(
            "me",
            "[منشی] برای تنظیم متن منشی بنویس:\n\ntنظیم متن منشی [متن دلخواه]"
        )
        return

    if command_text == "action:set_afk_txt":
        await client.send_message(
            "me",
            "[AFK] برای تنظیم متن AFK بنویس:\n\nتنظیم متن afk [متن دلخواه]"
        )
        return

    if command_text == "action:ping":
        await client.send_message("me", "[پنل] پینگ: کار می‌کنم.")
        return

    if command_text == "action:enemy_list":
        enemies = _get_list(owner_id, "enemies")
        if not enemies:
            await client.send_message("me", "[لیست دشمن] خالی است.")
        else:
            lines = [f"♕ {i+1}. {uid}" for i, uid in enumerate(enemies)]
            await client.send_message("me", "[لیست دشمن]\n" + "\n".join(lines))
        return

    if command_text == "action:love_list":
        love = _get_list(owner_id, "love_users")
        if not love:
            await client.send_message("me", "[لیست عشق] خالی است.")
        else:
            lines = [f"♛ {i+1}. {uid}" for i, uid in enumerate(love)]
            await client.send_message("me", "[لیست عشق]\n" + "\n".join(lines))
        return

    if command_text == "action:block_list":
        blist = _get_list(owner_id, "block_list")
        if not blist:
            await client.send_message("me", "[لیست بلاک] خالی است.")
        else:
            lines = [f"❈ {i+1}. {uid}" for i, uid in enumerate(blist)]
            await client.send_message("me", "[لیست بلاک]\n" + "\n".join(lines))
        return

    if command_text == "action:clear_enemies":
        _get_list(owner_id, "enemies").clear()
        _save_list(owner_id, "enemies")
        await client.send_message("me", "[دشمن] لیست دشمن‌ها پاکسازی شد.")
        return

    if command_text == "action:clear_blocks":
        _get_list(owner_id, "block_list").clear()
        _save_list(owner_id, "block_list")
        await client.send_message("me", "[بلاک] لیست بلاک‌ها پاکسازی شد.")
        return

    if command_text == "action:del_chat":
        await client.send_message("me", "[ابزار] برای دیلیت چت، دستور «دیلیت چت» را در همون چت بنویس.")
        return

    if command_text == "action:leave_grps":
        await client.send_message("me", "[ابزار] دستور «ترک همگانی گپ» را ارسال کن.")
        return

    if command_text == "action:leave_chns":
        await client.send_message("me", "[ابزار] دستور «ترک همگانی چنل» را ارسال کن.")
        return

    if command_text in ("action:spam40", "action:spam100"):
        await client.send_message(
            "me",
            "[اسپم] دستور «اسپم[40]» یا «اسپم[100]» را در چت هدف ریپلای روی متن بنویس."
        )
        return


# ═══════════════════════════════════════════════════════════════════════════════
#  _register_handlers — ثبت event handler‌های selfbot
# ═══════════════════════════════════════════════════════════════════════════════
def _register_handlers(client: TelegramClient, owner_id: int, entry: Dict[str, Any]):
    """تمام هندلرهای selfbot را برای یک کلاینت ثبت می‌کنه."""

    # ─── دکوریتور روشن/خاموش سلف ─────────────────────────────────────────────
    def _self_on(func):
        async def wrapper(event, *args, **kwargs):
            if not _get_flag(owner_id, "self_on", default=True):
                return
            return await func(event, *args, **kwargs)
        return wrapper

    # ─── سلف روشن / خاموش ────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(سلف روشن|self on)$'))
    async def self_on_h(event):
        _set_flag(owner_id, "self_on", True)
        await safe_edit(event, "꧁سلف با موفقیت روشن شد꧂")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(سلف خاموش|self off)$'))
    async def self_off_h(event):
        _set_flag(owner_id, "self_on", False)
        await safe_edit(event, "꧁سلف با موفقیت خاموش شد꧂")

    # ─── دشمن با ریپلای ──────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(دشمن|enemy)$'))
    @_self_on
    async def enemy_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید!")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        me = await client.get_me()
        if user.id == me.id:
            await safe_edit(event, "❈نمی‌توانی خودت را دشمن کنی.")
            return
        enemies = _get_list(owner_id, "enemies")
        if user.id in enemies:
            await safe_edit(event, "❈کاربر در لیست قرار داشته.")
            return
        enemies.add(user.id)
        _save_list(owner_id, "enemies")
        await safe_edit(event, f"❈کاربر {fc(str(user.id))} در لیست دشمن قرار گرفت✓")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^دشمن\((.+)\)$'))
    @_self_on
    async def enemy_user_h(event):
        username = event.pattern_match.group(1).strip().lstrip("@")
        try:
            user = await client.get_entity(username)
        except Exception:
            await safe_edit(event, "❈کاربر یافت نشد.")
            return
        enemies = _get_list(owner_id, "enemies")
        if user.id in enemies:
            await safe_edit(event, "❈کاربر در لیست قرار داشته.")
            return
        enemies.add(user.id)
        _save_list(owner_id, "enemies")
        await safe_edit(event, f"♕کاربر {fc(str(user.id))} به لیست دشمن اضافه شد♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(حذف دشمن|delenemy)$'))
    @_self_on
    async def del_enemy_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید!")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        enemies = _get_list(owner_id, "enemies")
        if user.id in enemies:
            enemies.discard(user.id)
            _save_list(owner_id, "enemies")
            await safe_edit(event, f"❈کاربر {fc(str(user.id))} از لیست دشمن خارج شد.")
        else:
            await safe_edit(event, "❈کاربر در لیست دشمن نبود.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(لیست دشمن|enemy list)$'))
    @_self_on
    async def enemy_list_h(event):
        enemies = _get_list(owner_id, "enemies")
        if not enemies:
            await safe_edit(event, "♕هیچ دشمنی ثبت نشده است♕")
            return
        lines = []
        for i, uid in enumerate(enemies, 1):
            try:
                u = await client.get_entity(uid)
                uname = f"@{u.username}" if getattr(u, "username", None) else "بدون یوزرنیم"
            except Exception:
                uname = "نامشخص"
            lines.append(f"♕{i}. {fc(str(uid))} | {uname}")
        await safe_edit(event, "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(پاکسازی لیست دشمن|clear enemy list)$'))
    @_self_on
    async def clear_enemy_h(event):
        _get_list(owner_id, "enemies").clear()
        _save_list(owner_id, "enemies")
        await safe_edit(event, "♕لیست دشمن پاکسازی شد♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(دشمن همگانی|global enemy)$'))
    @_self_on
    async def global_enemy_on_h(event):
        glb = _get_list(owner_id, "global_enemy_chats")
        glb.add(event.chat_id)
        _save_list(owner_id, "global_enemy_chats")
        await safe_edit(event, "♕دشمن همگانی در این گپ فعال شد♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(لغو دشمن همگانی|global enemy off)$'))
    @_self_on
    async def global_enemy_off_h(event):
        glb = _get_list(owner_id, "global_enemy_chats")
        if event.chat_id in glb:
            glb.discard(event.chat_id)
            _save_list(owner_id, "global_enemy_chats")
            await safe_edit(event, "♕دشمن همگانی در این گپ لغو شد♕")
        else:
            await safe_edit(event, "♕در این گپ دشمن همگانی فعال نبود♕")

    # ─── بلاک / انبلاک ───────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(بلاک کاربر|block user)$'))
    @_self_on
    async def block_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        try:
            await client(functions.contacts.BlockRequest(id=user.id))
            _get_list(owner_id, "block_list").add(user.id)
            _save_list(owner_id, "block_list")
            await safe_edit(event, f"❈کاربر {fc(str(user.id))} بلاک شد✓")
        except Exception as e:
            await safe_edit(event, f"♕خطا در بلاک: {e}♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(انبلاک کاربر|unblock user)$'))
    @_self_on
    async def unblock_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        try:
            await client(functions.contacts.UnblockRequest(id=user.id))
            _get_list(owner_id, "block_list").discard(user.id)
            _save_list(owner_id, "block_list")
            await safe_edit(event, f"❈کاربر {fc(str(user.id))} انبلاک شد✓")
        except Exception as e:
            await safe_edit(event, f"♕خطا در انبلاک: {e}♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(لیست بلاک|block list)$'))
    @_self_on
    async def block_list_h(event):
        blist = _get_list(owner_id, "block_list")
        if not blist:
            await safe_edit(event, "♕لیست بلاک خالی است♕")
            return
        lines = [f"❈{i}. {fc(str(uid))}" for i, uid in enumerate(blist, 1)]
        await safe_edit(event, "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(پاکسازی لیست بلاک|clear block list)$'))
    @_self_on
    async def clear_block_h(event):
        for uid in list(_get_list(owner_id, "block_list")):
            try:
                await client(functions.contacts.UnblockRequest(id=uid))
            except Exception:
                pass
        _get_list(owner_id, "block_list").clear()
        _save_list(owner_id, "block_list")
        await safe_edit(event, "❈لیست بلاک پاکسازی شد✓")

    # ─── سکوت پیوی ───────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(سکوت پیوی|pm silence)$'))
    @_self_on
    async def pm_silence_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        _get_list(owner_id, "pm_silence_users").add(user.id)
        _save_list(owner_id, "pm_silence_users")
        await safe_edit(event, f"♕کاربر {fc(str(user.id))} در سکوت پیوی قرار گرفت♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^سکوت پیوی\((.+)\)$'))
    @_self_on
    async def pm_silence_user_h(event):
        username = event.pattern_match.group(1).strip().lstrip("@")
        try:
            user = await client.get_entity(username)
        except Exception:
            await safe_edit(event, "♕کاربر یافت نشد♕")
            return
        _get_list(owner_id, "pm_silence_users").add(user.id)
        _save_list(owner_id, "pm_silence_users")
        await safe_edit(event, f"♕کاربر {fc(str(user.id))} در سکوت پیوی قرار گرفت♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(سکوت پیوی لغو|pm silence off)$'))
    @_self_on
    async def pm_silence_off_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        _get_list(owner_id, "pm_silence_users").discard(user.id)
        _save_list(owner_id, "pm_silence_users")
        await safe_edit(event, f"♕کاربر {fc(str(user.id))} از سکوت پیوی خارج شد♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(سکوت پیوی همگانی فعال|pm silence all on)$'))
    @_self_on
    async def pm_silence_all_on_h(event):
        _set_flag(owner_id, "pm_silence_all", True)
        await safe_edit(event, "♕سکوت پیوی همگانی با موفقیت آغاز شد♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(سکوت پیوی همگانی لغو|pm silence all off)$'))
    @_self_on
    async def pm_silence_all_off_h(event):
        _set_flag(owner_id, "pm_silence_all", False)
        await safe_edit(event, "♕سکوت پیوی همگانی پایان یافت♕")

    # ─── عشق ──────────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(تنظیم عشق|set love)$'))
    @_self_on
    async def set_love_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        _get_list(owner_id, "love_users").add(user.id)
        _save_list(owner_id, "love_users")
        uname = f"@{user.username}" if getattr(user, "username", None) else "بدون یوزرنیم"
        await safe_edit(
            event,
            f"♛کاربر: [{user.first_name}](tg://user?id={user.id})\n"
            f"♛یوزرنیم: {uname}\n"
            f"♛آیدی: {fc(str(user.id))}\n"
            f"♕با موفقیت به لیست عشق وارد شد♛"
        )

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(لیست عشق|love list)$'))
    @_self_on
    async def love_list_h(event):
        love = _get_list(owner_id, "love_users")
        if not love:
            await safe_edit(event, "♕لیست عشق خالی است♕")
            return
        lines = [f"♛{i}. {fc(str(uid))}" for i, uid in enumerate(love, 1)]
        await safe_edit(event, "\n".join(lines))

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(حذف عشق|remove love)$'))
    @_self_on
    async def del_love_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        _get_list(owner_id, "love_users").discard(user.id)
        _save_list(owner_id, "love_users")
        await safe_edit(event, f"❈کاربر {fc(str(user.id))} از لیست عشق خارج شد.")

    # ─── ری‌اکت ───────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^تنظیم ری‌اکت\((.+)\)$'))
    @_self_on
    async def set_react_h(event):
        emoji = event.pattern_match.group(1).strip()
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        rmap = _get_map(owner_id, "react_map")
        rmap[str(user.id)] = emoji
        _save_map(owner_id, "react_map")
        await safe_edit(event, f"♕ری‌اکت {emoji} برای {fc(str(user.id))} تنظیم شد♕")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(حذف ری‌اکت|remove react)$'))
    @_self_on
    async def del_react_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی فرد مورد نظر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        rmap = _get_map(owner_id, "react_map")
        rmap.pop(str(user.id), None)
        _save_map(owner_id, "react_map")
        await safe_edit(event, f"♕ری‌اکت کاربر {fc(str(user.id))} حذف شد♕")

    # ─── منشی هوشمند ──────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(منشی روشن|secretary on)$'))
    @_self_on
    async def sec_on_h(event):
        _set_flag(owner_id, "secretary", True)
        await safe_edit(event, "❈منشی هوشمند با موفقیت روشن شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(منشی خاموش|secretary off)$'))
    @_self_on
    async def sec_off_h(event):
        _set_flag(owner_id, "secretary", False)
        await safe_edit(event, "❈منشی هوشمند با موفقیت خاموش شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^تنظیم متن منشی\s+(.+)$'))
    @_self_on
    async def sec_txt_h(event):
        txt = event.pattern_match.group(1).strip()
        if not txt:
            await safe_edit(event, "♕متن منشی خالی است♕")
            return
        _set_str(owner_id, "secretary_text", txt)
        await safe_edit(event, "❈متن منشی با موفقیت تنظیم شد.")

    # ─── AFK ──────────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(afk روشن|afk on)$'))
    @_self_on
    async def afk_on_h(event):
        _set_flag(owner_id, "afk", True)
        await safe_edit(event, "❈حالت AFK روشن شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(afk خاموش|afk off)$'))
    @_self_on
    async def afk_off_h(event):
        _set_flag(owner_id, "afk", False)
        await safe_edit(event, "❈حالت AFK خاموش شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^تنظیم متن afk\s+(.+)$'))
    @_self_on
    async def afk_txt_h(event):
        txt = event.pattern_match.group(1).strip()
        _set_str(owner_id, "afk_text", txt)
        await safe_edit(event, "❈متن AFK با موفقیت تنظیم شد.")

    # ─── ساعت در نام / بیو ────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(ساعت روشن|clock on)$'))
    @_self_on
    async def clock_on_h(event):
        _set_flag(owner_id, "clock_name", True)
        await safe_edit(event, "❈ساعت با موفقیت روشن شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(ساعت خاموش|clock off)$'))
    @_self_on
    async def clock_off_h(event):
        _set_flag(owner_id, "clock_name", False)
        await safe_edit(event, "❈تایم با موفقیت خاموش شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(ساعت بیو روشن|bio clock on)$'))
    @_self_on
    async def bio_on_h(event):
        _set_flag(owner_id, "clock_bio", True)
        await safe_edit(event, "❈ساعت بیو با موفقیت روشن شد.")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(ساعت بیو خاموش|bio clock off)$'))
    @_self_on
    async def bio_off_h(event):
        _set_flag(owner_id, "clock_bio", False)
        await safe_edit(event, "❈ساعت بیو با موفقیت خاموش شد.")

    # ─── بولد ─────────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(بولد فعال|bold on)$'))
    @_self_on
    async def bold_on_h(event):
        _set_flag(owner_id, "bold_on", True)
        await safe_edit(event, "꧁بولد با موفقیت فعال شد꧂")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(لغو بولد|bold off)$'))
    @_self_on
    async def bold_off_h(event):
        _set_flag(owner_id, "bold_on", False)
        await safe_edit(event, "꧁بولد با موفقیت غیرفعال شد꧂")

    # ─── هوش مصنوعی: تنظیم اطلاعات ──────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^ai_context:\s*(.+)'))
    async def ai_ctx_h(event):
        ctx = event.pattern_match.group(1).strip()
        if ctx:
            set_ai_context(owner_id, ctx)
            await event.delete()
            await client.send_message("me", "[AI] اطلاعات ذخیره شد. پاسخ‌ها بر اساس این اطلاعات خواهند بود.")

    # ─── اسپم ────────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(اسپم سلف|selfspam)$'))
    @_self_on
    async def self_spam_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی پیامی ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        text = reply.raw_text
        await event.delete()
        for _ in range(40):
            await client.send_message(event.chat_id, text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^اسپم\[(\d+)\]$'))
    @_self_on
    async def spam_n_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی پیامی ریپلای کنید♕")
            return
        count = int(event.pattern_match.group(1))
        reply = await event.get_reply_message()
        text = reply.raw_text
        await event.delete()
        for _ in range(min(count, 200)):
            await client.send_message(event.chat_id, text)

    # ─── پینگ ────────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(پینگ سلف|self ping)$'))
    @_self_on
    async def ping_h(event):
        start = datetime.now()
        await safe_edit(event, "❈درحال دریافت...")
        await asyncio.sleep(1)
        await safe_edit(event, "❈درحال بروزرسانی...")
        await asyncio.sleep(1)
        ms = int((datetime.now() - start).total_seconds() * 1000)
        await safe_edit(
            event,
            "╔══════════════\n"
            "║  NexoSelf Ping  ║\n"
            "╚══════════════╝\n\n"
            f"> Edit speed: {ms // 3} ms\n"
            f"> Ping response: {ms} ms"
        )

    # ─── انیمیشن‌ها ──────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(گل|flower)$'))
    @_self_on
    async def flower_h(event):
        for f in ["🌺","🏵","💐","🌸","💮","🌷","🌹","🍁","🌻","🌼"]:
            await safe_edit(event, f)
            await asyncio.sleep(0.3)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(قلب|heart)$'))
    @_self_on
    async def heart_h(event):
        for h in ["💙","💚","💛","🧡","💜","❤","🤍","❤️‍🔥"]:
            await safe_edit(event, h)
            await asyncio.sleep(0.3)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(تپش قلب|heartbeat)$'))
    @_self_on
    async def heartbeat_h(event):
        for _ in range(6):
            await safe_edit(event, "❤💓❤💓❤💓")
            await asyncio.sleep(0.4)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(روند زمستان|winter)$'))
    @_self_on
    async def winter_h(event):
        for ic in ["☀","⛅","🌥","🌦","🌧","⛈️","🌨","☃️"]:
            await safe_edit(event, ic)
            await asyncio.sleep(0.4)
        await safe_edit(event, "I like winter")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^تابلو\s+(.+)$'))
    @_self_on
    async def board_h(event):
        emoji = event.pattern_match.group(1).strip()
        line = emoji * 20
        await safe_edit(
            event,
            "┌────────────────┐\n"
            f"│{line}\n"
            "└────────────────┘\n"
            "      \\(•◡•)/\n"
            "       \\   /\n"
            "        ---\n"
            "        | |"
        )

    # ─── ایدی کاربر ──────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(ایدی کاربر|user id)$'))
    @_self_on
    async def uid_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی کاربر ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        user = await reply.get_sender()
        await safe_edit(event, f"آیدی: {fc(str(user.id))}")

    # ─── دیلیت چت ────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(دیلیت چت|delete chat)$'))
    @_self_on
    async def del_chat_h(event):
        try:
            await client(functions.messages.DeleteHistoryRequest(
                peer=event.chat_id, max_id=0, revoke=True
            ))
            await safe_edit(event, "♕گفتگو با موفقیت حذف شد♕")
        except Exception as e:
            await safe_edit(event, f"♕خطا در حذف چت: {e}♕")

    # ─── ترک گروه / چنل ──────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(ترک همگانی گپ|leave all groups)$'))
    @_self_on
    async def leave_groups_h(event):
        await safe_edit(event, "در حال ترک همه گپ‌ها...")
        count = 0
        async for dialog in client.iter_dialogs():
            if dialog.is_group:
                try:
                    await client(functions.channels.LeaveChannelRequest(dialog.entity))
                    count += 1
                except Exception:
                    pass
        await safe_edit(event, f"♕لف همگانی گروه انجام شد ({count})")

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(ترک همگانی چنل|leave all channels)$'))
    @_self_on
    async def leave_channels_h(event):
        await safe_edit(event, "در حال ترک همه چنل‌ها...")
        count = 0
        async for dialog in client.iter_dialogs():
            if dialog.is_channel and not dialog.is_group:
                try:
                    await client(functions.channels.LeaveChannelRequest(dialog.entity))
                    count += 1
                except Exception:
                    pass
        await safe_edit(event, f"♕پاکسازی چنل‌ها انجام شد [{count}]♕")

    # ─── سیو مدیا ────────────────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(سیو|save)$'))
    @_self_on
    async def save_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی مدیا ریپلای کنید♕")
            return
        replied = await event.get_reply_message()
        if not replied.media:
            await safe_edit(event, "♕پیام ریپلای شده مدیا ندارد♕")
            return
        await event.delete()
        media = await client.download_media(replied.media)
        await client.send_file("me", media)
        await client.send_message("me", "مدیا با موفقیت ذخیره شد✓")

    # ─── تنظیم عکس پروفایل ───────────────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(تنظیم عکس|set photo)$'))
    @_self_on
    async def set_photo_h(event):
        if not event.is_reply:
            await safe_edit(event, "♕لطفا روی عکس ریپلای کنید♕")
            return
        reply = await event.get_reply_message()
        if not reply.photo:
            await safe_edit(event, "♕پیام ریپلای شده عکس نیست♕")
            return
        path = await client.download_media(reply.photo)
        try:
            await client(functions.photos.UploadProfilePhotoRequest(
                file=await client.upload_file(path)
            ))
            await safe_edit(event, "♕عکس پروفایل با موفقیت تنظیم شد♕")
        except Exception as e:
            await safe_edit(event, f"♕خطا: {e}♕")
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    # ─── راهنما (سبک Static selfbot) ─────────────────────────────────────────
    @client.on(events.NewMessage(outgoing=True, pattern=r'^(راهنما|help)$'))
    async def help_h(event):
        text = (
            "+==============================+\n"
            "|     NexoSelf SelfBot v1      |\n"
            "+==============================+\n\n"

            "【مدیریت سلف】\n"
            "«سلف روشن» | «سلف خاموش»\n\n"

            "【دشمن و فحش】\n"
            "«دشمن» — ریپلای روی فرد\n"
            "«دشمن(@یوزرنیم)» — با یوزرنیم\n"
            "«حذف دشمن» — ریپلای\n"
            "«لیست دشمن» | «پاکسازی لیست دشمن»\n"
            "«دشمن همگانی» | «لغو دشمن همگانی»\n\n"

            "【بلاک و سکوت】\n"
            "«بلاک کاربر» | «انبلاک کاربر» — ریپلای\n"
            "«لیست بلاک» | «پاکسازی لیست بلاک»\n"
            "«سکوت پیوی» | «سکوت پیوی لغو» — ریپلای\n"
            "«سکوت پیوی(@یوز)» | «سکوت پیوی همگانی فعال»\n"
            "«سکوت پیوی همگانی لغو»\n\n"

            "【عشق و ری‌اکت】\n"
            "«تنظیم عشق» | «لیست عشق» | «حذف عشق»\n"
            "«تنظیم ری‌اکت(ایموجی)» | «حذف ری‌اکت»\n\n"

            "【منشی، AFK، هوش مصنوعی】\n"
            "«منشی روشن» | «منشی خاموش»\n"
            "«تنظیم متن منشی [متن]»\n"
            "«afk روشن» | «afk خاموش»\n"
            "«تنظیم متن afk [متن]»\n"
            "«ai_context: [اطلاعات]» — تنظیم زمینه AI\n\n"

            "【ساعت و اتوماسیون】\n"
            "«ساعت روشن» | «ساعت خاموش»\n"
            "«ساعت بیو روشن» | «ساعت بیو خاموش»\n"
            "«بولد فعال» | «لغو بولد»\n\n"

            "【ابزار و ابزار گروه】\n"
            "«پینگ سلف» | «ایدی کاربر» — ریپلای\n"
            "«دیلیت چت» | «تنظیم عکس» — ریپلای\n"
            "«سیو» — ریپلای روی مدیا\n"
            "«ترک همگانی گپ» | «ترک همگانی چنل»\n\n"

            "【اسپم و انیمیشن】\n"
            "«اسپم سلف» | «اسپم[عدد]» — ریپلای\n"
            "«گل» | «قلب» | «تپش قلب» | «روند زمستان»\n"
            "«تابلو [ایموجی]»\n\n"

            "──────────────────────────────\n"
            "راهنمای بیشتر: «راهنما 2»\n"
            "پنل دکمه‌ای: «پنل» (در این چت)\n"
        )
        await safe_edit(event, text)

    @client.on(events.NewMessage(outgoing=True, pattern=r'^(راهنما 2|help2)$'))
    async def help2_h(event):
        text = (
            "+==============================+\n"
            "|     NexoSelf SelfBot v2      |\n"
            "+==============================+\n\n"

            "【پنل دکمه‌ای】\n"
            "«پنل» — باز کردن پنل با دکمه‌های شیشه‌ای\n"
            "روی هر دکمه کلیک = روشن/خاموش آن قابلیت\n\n"

            "【هوش مصنوعی DeepSeek】\n"
            "۱. کلید DEEPSEEK_API_KEY را تنظیم کن\n"
            "۲. «ai_context: [اطلاعات]» بنویس\n"
            "   نمونه: ai_context: قیمت iPhone 15: 45 میلیون\n"
            "۳. از پنل → منشی → «پاسخ DeepSeek AI» روشن کن\n"
            "وقتی آفلاینی، سلف با AI جواب پیام‌ها رو میده\n\n"

            "【منشی هوشمند】\n"
            "«منشی روشن/خاموش»\n"
            "«تنظیم متن منشی [متن دلخواه]»\n"
            "وقتی روشنه، هر پیوی جواب خودکار میگیره\n\n"

            "【ساعت زنده】\n"
            "«ساعت روشن» — ساعت در نام کاربری\n"
            "«ساعت بیو روشن» — ساعت در بیو\n"
            "هر ۶۰ ثانیه آپدیت میشه\n\n"

            "【لیست‌ها و مدیریت】\n"
            "«لیست دشمن» | «لیست عشق» | «لیست بلاک»\n"
            "«پاکسازی لیست دشمن/بلاک»\n\n"

            "──────────────────────────────\n"
            "پشتیبانی: @" + "NexoSelf_bot\n"
        )
        await safe_edit(event, text)

    # ─── هندلر پیام‌های ورودی (منشی / AFK / AI / ری‌اکت / دشمن) ────────────
    @client.on(events.NewMessage(incoming=True))
    async def incoming_h(event):
        if not _get_flag(owner_id, "self_on", default=True):
            return

        me = await client.get_me()
        sender_id = event.sender_id

        # ─── سکوت پیوی همگانی ────────────────────────────────────────────────
        if event.is_private and _get_flag(owner_id, "pm_silence_all"):
            try:
                await event.delete()
            except Exception:
                pass
            return

        # ─── سکوت پیوی فردی ──────────────────────────────────────────────────
        if event.is_private and sender_id in _get_list(owner_id, "pm_silence_users"):
            try:
                await event.delete()
            except Exception:
                pass
            return

        # ─── ضد فوروارد ──────────────────────────────────────────────────────
        if event.is_private and _get_flag(owner_id, "anti_forward") and event.forward:
            try:
                await event.delete()
            except Exception:
                pass
            return

        # ─── ضد لینک ─────────────────────────────────────────────────────────
        if event.is_private and _get_flag(owner_id, "anti_link"):
            import re as _re
            if _re.search(r'(https?://|t\.me/|@\w+)', event.raw_text or ""):
                try:
                    await event.delete()
                except Exception:
                    pass
                return

        # ─── لاگ پیوی ────────────────────────────────────────────────────────
        if event.is_private and _get_flag(owner_id, "log_pm") and sender_id != me.id:
            try:
                sender = await event.get_sender()
                sname = getattr(sender, "first_name", str(sender_id))
                await client.send_message(
                    "me",
                    f"[لاگ پیوی] از {sname} ({sender_id}):\n{event.raw_text}"
                )
            except Exception:
                pass

        # ─── ری‌اکت خودکار ────────────────────────────────────────────────────
        rmap = _get_map(owner_id, "react_map")
        if str(sender_id) in rmap:
            try:
                await client.send_reaction(event.chat_id, event.id, rmap[str(sender_id)])
            except Exception:
                pass

        # ─── دشمن همگانی در گپ ───────────────────────────────────────────────
        if event.chat_id in _get_list(owner_id, "global_enemy_chats") and not event.out:
            if sender_id != me.id:
                try:
                    insult = random.choice(_get_insults(owner_id))
                    await event.reply(insult)
                except Exception:
                    pass
                return

        # ─── دشمن تکی ─────────────────────────────────────────────────────────
        if sender_id in _get_list(owner_id, "enemies") and not event.out:
            try:
                insult = random.choice(_get_insults(owner_id))
                await event.reply(insult)
            except Exception:
                pass
            return

        # ─── اولویت‌بندی پاسخ خودکار در پیوی ────────────────────────────────
        if not event.is_private or sender_id == me.id:
            return

        # ─── هوش مصنوعی DeepSeek (اولویت اول) ────────────────────────────────
        if is_ai_enabled(owner_id):
            try:
                sender = await event.get_sender()
                sname = getattr(sender, "first_name", "") or str(sender_id)
                replied = await handle_ai_autoreply(
                    client=client,
                    owner_id=owner_id,
                    sender_id=sender_id,
                    sender_name=sname,
                    message_text=event.raw_text or "",
                )
                if replied:
                    return
            except Exception as _ae:
                print(f"[AI] خطا: {_ae}")

        # ─── منشی هوشمند (اولویت دوم) ────────────────────────────────────────
        if _get_flag(owner_id, "secretary"):
            try:
                await event.reply(
                    _get_str(owner_id, "secretary_text",
                             "سلام، فعلاً در دسترس نیستم، بعداً جواب می‌دم.")
                )
            except Exception:
                pass
            return

        # ─── AFK (اولویت سوم) ────────────────────────────────────────────────
        if _get_flag(owner_id, "afk"):
            try:
                await event.reply(
                    _get_str(owner_id, "afk_text", "فعلاً نیستم، بعداً جواب می‌دم.")
                )
            except Exception:
                pass

    # ─── هندلر پیام‌های خروجی (بولد / خودکارخوانی) ──────────────────────────
    @client.on(events.NewMessage(outgoing=True))
    async def outgoing_h(event):
        if not _get_flag(owner_id, "self_on", default=True):
            return

        # بولد
        if _get_flag(owner_id, "bold_on") and event.raw_text:
            try:
                await event.edit(f"**{event.raw_text}**")
            except Exception:
                pass

    # ─── خودکارخوانی پیام‌های ورودی ─────────────────────────────────────────
    @client.on(events.NewMessage(incoming=True))
    async def autoread_h(event):
        if _get_flag(owner_id, "autoread"):
            try:
                await client.send_read_acknowledge(event.chat_id)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════════════════════
#  _clock_loop — تسک پس‌زمینه: آپدیت ساعت در نام و بیو
# ═══════════════════════════════════════════════════════════════════════════════
async def _clock_loop(client: TelegramClient, owner_id: int):
    me = await client.get_me()
    base_bio = ""
    try:
        full = await client(functions.users.GetFullUserRequest(me.id))
        base_bio = full.full_user.about or ""
    except Exception:
        pass

    while True:
        try:
            now = datetime.now().strftime("%H:%M")

            if _get_flag(owner_id, "clock_name"):
                try:
                    await client(functions.account.UpdateProfileRequest(
                        first_name=me.first_name or "",
                        last_name=now,
                    ))
                except Exception:
                    pass

            if _get_flag(owner_id, "clock_bio"):
                try:
                    await client(functions.account.UpdateProfileRequest(
                        about=f"{now} | {base_bio}"[:70]
                    ))
                except Exception:
                    pass

            await asyncio.sleep(60)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[clock_loop][{owner_id}] خطا: {e}")
            await asyncio.sleep(15)


# ═══════════════════════════════════════════════════════════════════════════════
#  _scheduler_loop — تسک پس‌زمینه: پیام‌های زمان‌بندی‌شده
# ═══════════════════════════════════════════════════════════════════════════════
async def _scheduler_loop(client: TelegramClient, owner_id: int):
    """پیام‌های زمان‌بندی‌شده را بررسی و ارسال می‌کنه."""
    import database as _db
    while True:
        try:
            pending = _db.get_pending_scheduled(owner_id)
            for task in pending:
                try:
                    await client.send_message(
                        int(task["chat_id"]),
                        task["message_text"]
                    )
                    _db.mark_scheduled_sent(task["id"])
                except Exception as e:
                    print(f"[scheduler][{owner_id}] خطا در ارسال: {e}")
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[scheduler][{owner_id}] خطا: {e}")
            await asyncio.sleep(30)
