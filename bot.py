"""
bot.py - کلاینت تلگرام و هندلرها (نسخه اصلاح‌شده)
────────────────────────────────────────────────────────────
اصلاحات انجام‌شده:
✅ رفع asyncio.get_event_loop() در محیط چند Thread
✅ مدیریت صحیح CancelledError با asyncio.gather
✅ استفاده از asyncio.create_task به‌جای ensure_future
✅ محدود کردن FloodWait به حداکثر 60 ثانیه
✅ افزودن try/except به تمام int() ها
✅ استفاده از logging به‌جای print
✅ یکسان‌سازی ساختار entry با bot_manager.py
✅ اعتبارسنجی owner_id در تمام توابع
✅ سازگاری کامل با bot_manager.py (AdvancedBotManager)
"""
import asyncio
import re
import os
import datetime
import random
import threading
import time
import logging
from typing import Dict, Any, Optional, List

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.errors import FloodWaitError, UnauthorizedError

import database as db
import config
from texts import ENEMY_REPLIES, FRIEND_REPLIES

# ─── راه‌اندازی logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ─── فونت‌ها ───────────────────────────────────────────────────────────────────
_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

FONTS = {
    "0": lambda t: t,
    "1": lambda t: _convert_font(t, "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"),
    "2": lambda t: _convert_font(t, "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻"),
    "3": lambda t: _convert_font(t, "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"),
    "4": lambda t: _convert_font(t, "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"),
    "5": lambda t: _convert_font(t, "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"),
    "6": lambda t: _convert_font(t, "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"),
    "7": lambda t: " ".join(c + "\u0336" for c in t),
    "8": lambda t: " ".join(c + "\u0332" for c in t),
}

LINK_PATTERN = re.compile(
    r"(https?://\S+|t.me/\S+|telegram.me/\S+|www.\S+)", re.IGNORECASE
)
_POST_LINK_RE = re.compile(
    r"^(?:https?://)?t.me/([A-Za-z0-9_]+)/(\d+)/?$", re.IGNORECASE
)

# ─── سیستم محدودیت زمانی ──────────────────────────────────────────────────────
_last_secretary_reply: Dict[int, float] = {}
_last_friend_reply: Dict[int, float] = {}
SECRETARY_COOLDOWN = getattr(config, "SECRETARY_COOLDOWN", 86400)  # 24 ساعت
FRIEND_COOLDOWN = getattr(config, "FRIEND_COOLDOWN", 3600)  # 1 ساعت


def _convert_font(text: str, chars: str) -> str:
    """تبدیل متن به فونت خاص"""
    result = []
    for ch in text:
        if ch in _ALPHA:
            result.append(chars[_ALPHA.index(ch)])
        else:
            result.append(ch)
    return "".join(result)


def _apply_font(owner_id: int, text: str) -> str:
    """اعمال فونت انتخابی کاربر"""
    font_id = db.get_setting(owner_id, "selected_font", "0")
    fn = FONTS.get(font_id, FONTS["0"])
    return fn(text)


# ─── فونت‌های ساعت ─────────────────────────────────────────────────────────────
CLOCK_FONTS = {
    "0": "0123456789",
    "1": "⓿❶❷❸❹❺❻❼❽❾",
    "2": "𝟬𝟭𝟮𝟯𝟰𝟱𝟲𝟳𝟴𝟵",
    "3": "⓪①②③④⑤⑥⑦⑧⑨",
    "4": "𝟢𝟣𝟤𝟥𝟦𝟧𝟨𝟩𝟪𝟫",
    "5": "0⑴⑵⑶⑷⑸⑹⑺⑻⑼",
    "6": "₀₁₂₃₄₅₆₇₈₉",
    "7": "⁰¹²³⁴⁵⁶⁷⁸⁹",
    "8": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗",
    "9": "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡",
}


def _apply_clock_font(owner_id: int, text: str) -> str:
    """اعمال فونت ساعت"""
    font_id = db.get_setting(owner_id, "selected_clock_font", "0")
    digits = CLOCK_FONTS.get(font_id, CLOCK_FONTS["0"])
    return "".join(digits[int(ch)] if ch.isdigit() else ch for ch in text)


_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def persian_time() -> str:
    """دریافت زمان فعلی ایران"""
    iran_tz = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
    now = datetime.datetime.now(iran_tz)
    return f"{now.hour:02d}:{now.minute:02d}".translate(_SUPER)


# ─── توابع کمکی ───────────────────────────────────────────────────────────────
def _validate_owner_id(owner_id: int) -> bool:
    """اعتبارسنجی owner_id"""
    return isinstance(owner_id, int) and owner_id > 0


def _safe_int(value: Any, default: int = 0) -> int:
    """تبدیل امن به int با مدیریت خطا"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _get_media_dir(owner_id: int) -> str:
    """دریافت مسیر ذخیره مدیا با اعتبارسنجی"""
    if not _validate_owner_id(owner_id):
        raise ValueError(f"owner_id نامعتبر: {owner_id}")
    media_dir = os.path.join("saved_media", str(owner_id))
    os.makedirs(media_dir, exist_ok=True)
    return media_dir


def _is_owner_account(me: Any) -> bool:
    """تشخیص اینکه آیا یک کاربر تلگرام، مالک اصلی ربات است"""
    try:
        me_phone = (getattr(me, "phone", None) or "").lstrip("+")
        owner_phone = getattr(config, "OWNER_PHONE", "").lstrip("+")
        return (
            getattr(me, "id", None) == getattr(config, "OWNER_TG_ID", None)
            or (bool(owner_phone) and me_phone == owner_phone)
            or getattr(me, "username", None) == getattr(config, "OWNER_USERNAME", "")
        )
    except Exception as e:
        logger.warning("خطا در تشخیص مالک: %s", e)
        return False


# ─── توابع کمکی هندلر ─────────────────────────────────────────────────────────
async def _safe_edit(event, owner_id: int, text: str, font_fn=None):
    """ویرایش امن پیام با مدیریت FloodWait"""
    try:
        if font_fn is None:
            fn = FONTS.get(db.get_setting(owner_id, "selected_font", "0"), FONTS["0"])
            text = fn(text)
        else:
            text = font_fn(text)
        await event.edit(text)
    except FloodWaitError as e:
        wait_time = min(e.seconds + 1, 60)  # حداکثر 60 ثانیه
        logger.warning("[%s] FloodWait: %s ثانیه", owner_id, wait_time)
        await asyncio.sleep(wait_time)
    except Exception as e:
        logger.error("[%s] خطا در edit: %s", owner_id, e)


async def _resolve_target(event, parts: List[str]) -> Optional[Dict[str, Any]]:
    """دریافت هدف از ریپلای یا آیدی عددی"""
    replied = await event.get_reply_message()
    if replied:
        sender = await replied.get_sender()
        if sender:
            return {
                "id": sender.id,
                "username": getattr(sender, "username", None),
                "name": getattr(sender, "first_name", str(sender.id)),
            }
    for p in parts[1:]:
        if p.lstrip("-").isdigit():
            return {"id": _safe_int(p), "username": None, "name": p}
    return None


# ─── ثبت هندلرها (per-user) ───────────────────────────────────────────────────
def _register_handlers(cl: TelegramClient, owner_id: int, entry: Dict[str, Any]):
    """
    ثبت تمام هندلرهای بات برای یک کلاینت
    ⚠️ این تابع sync است (bot_manager.py آن را sync فراخوانی می‌کند)
    """
    if not _validate_owner_id(owner_id):
        logger.error("owner_id نامعتبر برای ثبت هندلرها: %s", owner_id)
        return

    @cl.on(events.NewMessage(incoming=True))
    async def on_incoming(event):
        """پردازش پیام‌های ورودی"""
        # اگر پلن منقضی شده، هیچ کاری نکن
        if entry.get("paused"):
            return

        msg = event.message
        sender = await event.get_sender()
        chat = await event.get_chat()
        sender_id = getattr(sender, "id", 0)
        chat_id = getattr(chat, "id", 0)
        text = msg.text or ""

        # بررسی تگ شدن در گروه‌ها
        is_tagged = False
        if not event.is_private:
            me = await cl.get_me()
            if msg.entities:
                for entity in msg.entities:
                    if hasattr(entity, 'user_id') and entity.user_id == me.id:
                        is_tagged = True
                        break
            replied_msg = await event.get_reply_message()
            if replied_msg and replied_msg.sender_id == me.id:
                is_tagged = True
            if me.username and me.username.lower() in text.lower():
                is_tagged = True

        # اگر در گروه است و تگ نشده، فقط کارهای خودکار
        if not event.is_private and not is_tagged:
            if db.get_setting(owner_id, "auto_seen_active") == "1":
                try:
                    await cl.send_read_acknowledge(chat_id, msg)
                except Exception:
                    pass

            if db.get_setting(owner_id, "auto_save_media") == "1" and msg.media:
                try:
                    media_dir = _get_media_dir(owner_id)
                    await cl.download_media(msg, file=media_dir + "/")
                except Exception as e:
                    logger.error("[%s] خطا در دانلود مدیا: %s", owner_id, e)
            return

        if db.is_silent_chat(owner_id, chat_id) or db.is_silent_user(owner_id, sender_id):
            return

        # ذخیره خودکار مدیا
        if db.get_setting(owner_id, "auto_save_media") == "1" and msg.media:
            try:
                media_dir = _get_media_dir(owner_id)
                await cl.download_media(msg, file=media_dir + "/")
            except Exception as e:
                logger.error("[%s] خطا در ذخیره مدیا: %s", owner_id, e)

        # ذخیره مدیای تایمدار
        if event.is_private and msg.media:
            ttl = getattr(msg.media, "ttl_seconds", None)
            if ttl:
                try:
                    me = await cl.get_me()
                    media_dir = _get_media_dir(owner_id)
                    path = await cl.download_media(msg, file=media_dir + "/")
                    if path:
                        await cl.send_file(
                            me.id, path,
                            caption=f"📥 مدیای تایمدار ذخیره شد\n👤 از: {getattr(sender, 'first_name', sender_id)} ({sender_id})"
                        )
                except Exception as e:
                    logger.error("[%s] خطا در ذخیره مدیای تایمدار: %s", owner_id, e)

        # سین خودکار
        if db.get_setting(owner_id, "auto_seen_active") == "1":
            try:
                await cl.send_read_acknowledge(chat_id, msg)
            except Exception:
                pass

        # جوین اجباری (فقط پیوی)
        if event.is_private and db.get_setting(owner_id, "force_join_active") == "1":
            channel_id = db.get_setting(owner_id, "force_join_channel", "")
            if channel_id:
                is_member = False
                try:
                    from telethon.tl.functions.channels import GetParticipantRequest
                    from telethon.errors import UserNotParticipantError, ChannelPrivateError
                    try:
                        channel_entity = await cl.get_entity(
                            _safe_int(channel_id.lstrip("-")) * (-1 if channel_id.startswith("-") else 1)
                            if channel_id.lstrip("-").isdigit() else channel_id
                        )
                        await cl(GetParticipantRequest(channel_entity, sender_id))
                        is_member = True
                    except (UserNotParticipantError, KeyError):
                        is_member = False
                    except ChannelPrivateError:
                        is_member = True
                    except Exception:
                        is_member = True
                except Exception:
                    is_member = True

                if not is_member:
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    join_msg = db.get_setting(
                        owner_id, "force_join_message",
                        "⛔ برای ارسال پیام ابتدا باید در کانال ما عضو شوید."
                    )
                    try:
                        channel_link = db.get_setting(owner_id, "force_join_link", "")
                        from telethon.tl.types import (
                            ReplyInlineMarkup, KeyboardButtonUrl, KeyboardButtonRow
                        )
                        if channel_link:
                            buttons = ReplyInlineMarkup(rows=[
                                KeyboardButtonRow(buttons=[
                                    KeyboardButtonUrl(
                                        text="📢 عضویت در کانال ✅",
                                        url=channel_link
                                    )
                                ])
                            ])
                            await cl.send_message(sender_id, join_msg, buttons=buttons)
                        else:
                            await cl.send_message(sender_id, join_msg)
                    except Exception:
                        pass
                    return

        # منشی (فقط پیوی)
        if db.get_setting(owner_id, "secretary_active") == "1" and event.is_private:
            now = time.time()
            last_reply = _last_secretary_reply.get(chat_id, 0)
            if now - last_reply >= SECRETARY_COOLDOWN:
                sec_msg = db.get_setting(owner_id, "secretary_message", "در حال حاضر در دسترس نیستم.")
                try:
                    await event.reply(sec_msg)
                    _last_secretary_reply[chat_id] = now
                except Exception as e:
                    logger.error("[%s] خطا در منشی: %s", owner_id, e)
            return

        # ری‌اکشن خودکار
        if db.get_setting(owner_id, "auto_reaction_active") == "1":
            emoji = db.get_setting(owner_id, "auto_reaction_emoji", "❤️")
            try:
                from telethon.tl.functions.messages import SendReactionRequest
                from telethon.tl.types import ReactionEmoji
                await cl(SendReactionRequest(
                    peer=chat_id,
                    msg_id=msg.id,
                    reaction=[ReactionEmoji(emoticon=emoji)],
                    big=False,
                    add_to_recent=True
                ))
            except Exception as e:
                logger.warning("[%s] خطا در ری‌اکشن: %s", owner_id, e)

        # پاسخ به دوستان
        if event.is_private and db.is_friend(owner_id, sender_id):
            now = time.time()
            last_reply = _last_friend_reply.get(sender_id, 0)
            if now - last_reply >= FRIEND_COOLDOWN:
                try:
                    await event.reply(random.choice(FRIEND_REPLIES))
                    _last_friend_reply[sender_id] = now
                except Exception as e:
                    logger.error("[%s] خطا در پاسخ به دوست: %s", owner_id, e)

        # پاسخ به دشمن
        if db.get_setting(owner_id, "enemy_reply_active") == "1" and db.is_enemy(owner_id, sender_id):
            try:
                await event.reply(random.choice(ENEMY_REPLIES))
            except Exception as e:
                logger.error("[%s] خطا در پاسخ به دشمن: %s", owner_id, e)

        # ضد لینک (فقط پیوی)
        if db.get_setting(owner_id, "anti_link_active") == "1" and event.is_private and LINK_PATTERN.search(text):
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل پیوی
        if db.get_setting(owner_id, "private_lock_active") == "1" and event.is_private:
            try:
                await msg.delete()
            except Exception:
                pass

    @cl.on(events.NewMessage(outgoing=True))
    async def on_outgoing(event):
        """پردازش پیام‌های خروجی (دستورات)"""
        text = event.raw_text.strip()

        # دستورات همیشه فعال
        if text == "سلف روشن":
            db.set_setting(owner_id, "self_bot_active", "1")
            await _safe_edit(event, owner_id, "✅ سلف‌بات روشن شد.")
            return
        if text == "سلف خاموش":
            db.set_setting(owner_id, "self_bot_active", "0")
            await _safe_edit(event, owner_id, "❌ سلف‌بات خاموش شد.")
            return

        # اگر پلن منقضی شده، فقط دستور وضعیت را اجرا کن
        if entry.get("paused"):
            if text in ("وضعیت", "راهنما", "help"):
                pass
            else:
                await _safe_edit(
                    event, owner_id,
                    "⛔ اشتراک شما منقضی شده است.\n"
                    "برای تمدید پلن با ادمین در تماس باشید.\n"
                    "بعد از تمدید، سلف تا ۵ دقیقه دیگر خودکار فعال می‌شود."
                )
                return

        # لیست دستورات تنظیماتی
        config_commands = [
            "منشی روشن", "منشی خاموش", "پیام منشی",
            "ضد حذف روشن", "ضد حذف خاموش",
            "ضد لینک روشن", "ضد لینک خاموش",
            "قفل پیوی روشن", "قفل پیوی خاموش",
            "سین خودکار روشن", "سین خودکار خاموش",
            "ری‌اکشن روشن", "ری‌اکشن خاموش",
            "ذخیره مدیا روشن", "ذخیره مدیا خاموش",
            "ساعت نام روشن", "ساعت نام خاموش",
            "ساعت بیو روشن", "ساعت بیو خاموش",
            "پاسخ دشمن روشن", "پاسخ دشمن خاموش",
            "تنظیم دشمن", "حذف دشمن", "نمایش لیست دشمن", "پاک کردن لیست دشمن",
            "تنظیم دوست", "حذف دوست", "نمایش لیست دوست", "پاک کردن لیست دوست",
            "سایلنت چت روشن", "سایلنت چت خاموش", "سایلنت کاربر", "لغو سایلنت کاربر",
            "فونت", "لیست فونت", "فونت متن روشن", "فونت متن خاموش", "بنویس",
            "بولد", "ایتالیک", "مونو", "اسپویلر", "کوت", "خط‌خورده", "زیرخط",
            "ذخیره", "ارسال ذخیره",
            "ترجمه", "هوا", "قیمت دلار", "ارز",
            "وضعیت", "راهنما", "help",
            "حذف بعد",
            "سیو کانال", "توقف سیو",
            "تنظیم کانال", "حذف کانال اجباری", "جوین اجباری روشن", "جوین اجباری خاموش",
            "پیام جوین", "لینک کانال جوین",
        ]

        is_config_command = any(text.startswith(cmd) or text == cmd for cmd in config_commands)

        # اگر دستور تنظیماتی نیست و سلف خاموش است، اجرا نکن
        if not is_config_command and db.get_setting(owner_id, "self_bot_active") != "1":
            return

        await _handle_command(cl, event, text, owner_id, entry)

    logger.debug("[%s] هندلرها ثبت شدند", owner_id)


# ─── پردازش دستورات ──────────────────────────────────────────────────────────
async def _handle_command(cl, event, text: str, owner_id: int, entry: Dict[str, Any]):
    """پردازش دستورات کاربر"""
    msg = event.message

    def gs(key, default=None):
        return db.get_setting(owner_id, key, default)

    def ss(key, value):
        db.set_setting(owner_id, key, value)

    async def edit(t):
        await _safe_edit(event, owner_id, t)

    # ─── دشمن ────────────────────────────────────────────────────────────────
    if text.startswith("تنظیم دشمن"):
        target = await _resolve_target(event, text.split())
        if target:
            db.add_enemy(owner_id, target["id"], target.get("username"), target.get("name"))
            await edit(f"🔴 {target.get('name', target['id'])} به لیست دشمن اضافه شد.")
        else:
            await edit("❗ روی پیام کاربر ریپلای کن یا آیدی عددی بنویس.")

    elif text.startswith("حذف دشمن"):
        target = await _resolve_target(event, text.split())
        if target:
            removed = db.remove_enemy(owner_id, target["id"])
            await edit("✅ از لیست دشمن حذف شد." if removed else "❗ در لیست نبود.")
        else:
            await edit("❗ روی پیام کاربر ریپلای کن یا آیدی عددی بنویس.")

    elif text == "نمایش لیست دشمن":
        enemies = db.get_enemies(owner_id)
        if not enemies:
            await edit("📋 لیست دشمن خالی است.")
        else:
            lines = [f"🔴 لیست دشمن ({len(enemies)} نفر):\n"]
            for e in enemies:
                lines.append(f"• {e['name'] or e['username'] or e['user_id']} — `{e['user_id']}`")
            await edit("\n".join(lines))

    elif text == "پاک کردن لیست دشمن":
        db.clear_enemies(owner_id)
        await edit("🗑️ لیست دشمن پاک شد.")

    # ─── دوست ────────────────────────────────────────────────────────────────
    elif text.startswith("تنظیم دوست"):
        target = await _resolve_target(event, text.split())
        if target:
            db.add_friend(owner_id, target["id"], target.get("username"), target.get("name"))
            await edit(f"💚 {target.get('name', target['id'])} به لیست دوست اضافه شد.")
        else:
            await edit("❗ روی پیام کاربر ریپلای کن یا آیدی عددی بنویس.")

    elif text.startswith("حذف دوست"):
        target = await _resolve_target(event, text.split())
        if target:
            removed = db.remove_friend(owner_id, target["id"])
            await edit("✅ از لیست دوست حذف شد." if removed else "❗ در لیست نبود.")
        else:
            await edit("❗ روی پیام کاربر ریپلای کن یا آیدی عددی بنویس.")

    elif text == "نمایش لیست دوست":
        friends = db.get_friends(owner_id)
        if not friends:
            await edit("📋 لیست دوست خالی است.")
        else:
            lines = [f"💚 لیست دوست ({len(friends)} نفر):\n"]
            for f in friends:
                lines.append(f"• {f['name'] or f['username'] or f['user_id']} — `{f['user_id']}`")
            await edit("\n".join(lines))

    elif text == "پاک کردن لیست دوست":
        db.clear_friends(owner_id)
        await edit("🗑️ لیست دوست پاک شد.")

    # ─── منشی ────────────────────────────────────────────────────────────────
    elif text == "منشی روشن":
        ss("secretary_active", "1")
        await edit("🤖 منشی خودکار روشن شد.\n💡 هر کاربر فقط هر 24 ساعت یک بار پاسخ می‌گیرد.")
    elif text == "منشی خاموش":
        ss("secretary_active", "0")
        await edit("🤖 منشی خودکار خاموش شد.")
    elif text.startswith("پیام منشی "):
        ss("secretary_message", text[len("پیام منشی "):].strip())
        await edit("✅ پیام منشی تنظیم شد.")

    # ─── ضد حذف ──────────────────────────────────────────────────────────────
    elif text == "ضد حذف روشن":
        ss("anti_delete_active", "1")
        await edit("🛡️ ضد حذف روشن شد.")
    elif text == "ضد حذف خاموش":
        ss("anti_delete_active", "0")
        await edit("🛡️ ضد حذف خاموش شد.")

    # ─── ضد لینک ─────────────────────────────────────────────────────────────
    elif text == "ضد لینک روشن":
        ss("anti_link_active", "1")
        await edit("🔗 ضد لینک روشن شد.")
    elif text == "ضد لینک خاموش":
        ss("anti_link_active", "0")
        await edit("🔗 ضد لینک خاموش شد.")

    # ─── قفل پیوی ────────────────────────────────────────────────────────────
    elif text == "قفل پیوی روشن":
        ss("private_lock_active", "1")
        await edit("🔒 قفل پیوی روشن شد.")
    elif text == "قفل پیوی خاموش":
        ss("private_lock_active", "0")
        await edit("🔓 قفل پیوی خاموش شد.")

    # ─── سین خودکار ──────────────────────────────────────────────────────────
    elif text == "سین خودکار روشن":
        ss("auto_seen_active", "1")
        await edit("👁️ سین خودکار روشن شد.")
    elif text == "سین خودکار خاموش":
        ss("auto_seen_active", "0")
        await edit("👁️ سین خودکار خاموش شد.")

    # ─── ری‌اکشن ─────────────────────────────────────────────────────────────
    elif text == "ری‌اکشن روشن":
        ss("auto_reaction_active", "1")
        await edit("❤️ ری‌اکشن خودکار روشن شد.")
    elif text == "ری‌اکشن خاموش":
        ss("auto_reaction_active", "0")
        await edit("❤️ ری‌اکشن خودکار خاموش شد.")
    elif text.startswith("ری‌اکشن "):
        emoji = text[len("ری‌اکشن "):].strip()
        ss("auto_reaction_emoji", emoji)
        await edit(f"✅ ری‌اکشن پیش‌فرض: {emoji}")

    # ─── ذخیره مدیا ──────────────────────────────────────────────────────────
    elif text == "ذخیره مدیا روشن":
        _get_media_dir(owner_id)
        ss("auto_save_media", "1")
        await edit("💾 ذخیره خودکار مدیا روشن شد.")
    elif text == "ذخیره مدیا خاموش":
        ss("auto_save_media", "0")
        await edit("💾 ذخیره خودکار مدیا خاموش شد.")

    # ─── سیو کانال ───────────────────────────────────────────────────────────
    elif text == "سیو کانال" or text.startswith("سیو کانال "):
        parts = text.split()
        channel_input = parts[2] if len(parts) >= 3 else None
        if not channel_input:
            await edit(
                "❗ فرمت درست یکی از این دو حالت:\n"
                "• سیو کانال [لینک یک پست خاص]\n"
                "  مثال: سیو کانال https://t.me/channel/123\n"
                "• سیو کانال [@یوزرنیم یا لینک کانال] [تعداد]\n"
                "  مثال: سیو کانال @channel 50"
            )
        elif _POST_LINK_RE.match(channel_input):
            await edit("⏳ در حال ذخیره این پست...")
            asyncio.create_task(_save_channel_media(cl, channel_input, None, owner_id))
        else:
            limit = _safe_int(parts[3], 100) if len(parts) >= 4 else 100
            await edit(f"⏳ در حال پردازش کانال، تا {limit} مدیا ذخیره می‌شود...")
            asyncio.create_task(_save_channel_media(cl, channel_input, limit, owner_id))

    elif text == "توقف سیو":
        ss("channel_save_active", "0")
        await edit("🛑 سیو کانال متوقف شد.")

    # ─── سایلنت ──────────────────────────────────────────────────────────────
    elif text == "سایلنت چت روشن":
        chat = await event.get_chat()
        db.add_silent_chat(owner_id, chat.id)
        await edit("🔇 این چت سایلنت شد.")
    elif text == "سایلنت چت خاموش":
        chat = await event.get_chat()
        db.remove_silent_chat(owner_id, chat.id)
        await edit("🔔 سایلنت این چت برداشته شد.")
    elif text.startswith("سایلنت کاربر "):
        uid = _safe_int(text.split()[-1])
        if uid:
            db.add_silent_user(owner_id, uid)
            await edit(f"🔇 کاربر {uid} سایلنت شد.")
        else:
            await edit("❗ آیدی عددی معتبر وارد کنید.")
    elif text.startswith("لغو سایلنت کاربر "):
        uid = _safe_int(text.split()[-1])
        if uid:
            db.remove_silent_user(owner_id, uid)
            await edit(f"🔔 سایلنت کاربر {uid} برداشته شد.")
        else:
            await edit("❗ آیدی عددی معتبر وارد کنید.")

    # ─── پاسخ دشمن ───────────────────────────────────────────────────────────
    elif text == "پاسخ دشمن روشن":
        ss("enemy_reply_active", "1")
        await edit("⚔️ پاسخ خودکار به دشمن روشن شد.")
    elif text == "پاسخ دشمن خاموش":
        ss("enemy_reply_active", "0")
        await edit("⚔️ پاسخ خودکار به دشمن خاموش شد.")

    # ─── فونت متن (حالت خودکار) ──────────────────────────────────────────────
    elif text == "فونت متن روشن":
        ss("text_font_auto", "1")
        font_id = gs("selected_font", "0")
        fn = FONTS.get(font_id, FONTS["0"])
        sample = fn("Hello World")
        await edit(f"✅ فونت متن خودکار روشن شد.\n✏️ از این به بعد هر پیامی که بنویسی با فونت {font_id} ادیت می‌شه.\nنمونه: `{sample}`")

    elif text == "فونت متن خاموش":
        ss("text_font_auto", "0")
        await edit("❌ فونت متن خودکار خاموش شد.\nپیام‌ها دیگه ادیت نمی‌شن.")

    elif text.startswith("بنویس "):
        raw = text[len("بنویس "):].strip()
        if not raw:
            await edit("❗ فرمت: بنویس [متن]")
        else:
            font_id = gs("selected_font", "0")
            fn = FONTS.get(font_id, FONTS["0"])
            styled = fn(raw)
            await edit(styled)

    # ─── قالب‌بندی تلگرام ────────────────────────────────────────────────────
    elif text.startswith("بولد "):
        raw = text[len("بولد "):].strip()
        if raw:
            from telethon.tl.types import MessageEntityBold
            await event.edit(raw, formatting_entities=[MessageEntityBold(0, len(raw))])
        else:
            await edit("❗ فرمت: بولد [متن]")

    elif text.startswith("ایتالیک "):
        raw = text[len("ایتالیک "):].strip()
        if raw:
            from telethon.tl.types import MessageEntityItalic
            await event.edit(raw, formatting_entities=[MessageEntityItalic(0, len(raw))])
        else:
            await edit("❗ فرمت: ایتالیک [متن]")

    elif text.startswith("مونو "):
        raw = text[len("مونو "):].strip()
        if raw:
            from telethon.tl.types import MessageEntityCode
            await event.edit(raw, formatting_entities=[MessageEntityCode(0, len(raw))])
        else:
            await edit("❗ فرمت: مونو [متن]")

    elif text.startswith("اسپویلر "):
        raw = text[len("اسپویلر "):].strip()
        if raw:
            from telethon.tl.types import MessageEntitySpoiler
            await event.edit(raw, formatting_entities=[MessageEntitySpoiler(0, len(raw))])
        else:
            await edit("❗ فرمت: اسپویلر [متن]")

    elif text.startswith("کوت "):
        raw = text[len("کوت "):].strip()
        if raw:
            try:
                from telethon.tl.types import MessageEntityBlockquote
                await event.edit(raw, formatting_entities=[MessageEntityBlockquote(0, len(raw), collapsed=False)])
            except Exception:
                await event.edit(f"❝ {raw} ❞")
        else:
            await edit("❗ فرمت: کوت [متن]")

    elif text.startswith("خط‌خورده "):
        raw = text[len("خط‌خورده "):].strip()
        if raw:
            from telethon.tl.types import MessageEntityStrike
            await event.edit(raw, formatting_entities=[MessageEntityStrike(0, len(raw))])
        else:
            await edit("❗ فرمت: خط‌خورده [متن]")

    elif text.startswith("زیرخط "):
        raw = text[len("زیرخط "):].strip()
        if raw:
            from telethon.tl.types import MessageEntityUnderline
            await event.edit(raw, formatting_entities=[MessageEntityUnderline(0, len(raw))])
        else:
            await edit("❗ فرمت: زیرخط [متن]")

    # ─── فونت ساعت ──────────────────────────────────────────────────────────
    elif text.startswith("فونت ساعت "):
        font_id = text.split()[-1]
        if font_id in CLOCK_FONTS:
            ss("selected_clock_font", font_id)
            sample = _apply_clock_font(owner_id, "12:34")
            await edit(f"⏰ فونت ساعت {font_id} انتخاب شد:\n`{sample}`")
        else:
            await edit("❗ شماره فونت ساعت باید بین ۰ تا ۹ باشد.")

    elif text == "لیست فونت ساعت":
        lines = ["⏰ **فونت‌های ساعت موجود:**\n"]
        for k, digits in CLOCK_FONTS.items():
            sample = " ".join(digits[_safe_int(ch)] for ch in "1234567890")
            lines.append(f"`فونت ساعت {k}` — `{sample}`")
        lines.append("\n💡 برای انتخاب: `فونت ساعت [شماره]`")
        await edit("\n".join(lines))

    # ─── فونت ────────────────────────────────────────────────────────────────
    elif text.startswith("فونت "):
        parts = text.split()
        font_id = parts[-1]
        preview_words = parts[1:-1]
        if font_id in FONTS:
            ss("selected_font", font_id)
            fn = FONTS[font_id]
            if preview_words:
                preview_text = " ".join(preview_words)
                styled = fn(preview_text)
                await edit(f"🔤 فونت {font_id} انتخاب شد:\n`{styled}`")
            else:
                font_names = {
                    "0": "Normal", "1": "Bold", "2": "Italic", "3": "Mono",
                    "4": "Full", "5": "Serif", "6": "Script", "7": "Strike", "8": "Under"
                }
                styled = fn(font_names.get(font_id, f"Font{font_id}"))
                await edit(f"🔤 فونت {font_id} انتخاب شد:\n`{styled}`")
        else:
            await edit("❗ شماره فونت باید بین ۰ تا ۸ باشد.")

    elif text == "لیست فونت":
        font_names = {
            "0": "Normal", "1": "Bold", "2": "Italic", "3": "Mono",
            "4": "Full", "5": "Serif", "6": "Script", "7": "Strike", "8": "Under"
        }
        lines = ["📝 **فونت‌های موجود:**\n"]
        for k, name in font_names.items():
            fn = FONTS[k]
            styled = fn(name)
            lines.append(f"`فونت {k}` — `{styled}`")
        lines.append("\n💡 برای فونت مخصوص ساعت از `لیست فونت ساعت` استفاده کنید.")
        await edit("\n".join(lines))

    # ─── ساعت ────────────────────────────────────────────────────────────────
    elif text == "ساعت نام روشن":
        ss("clock_name_active", "1")
        await edit("⏰ ساعت در نام روشن شد.\n💡 برای تغییر فونت ساعت: `فونت ساعت [0-9]`")
    elif text == "ساعت نام خاموش":
        ss("clock_name_active", "0")
        await edit("⏰ ساعت در نام خاموش شد.")
    elif text == "ساعت بیو روشن":
        ss("clock_bio_active", "1")
        await edit("⏰ ساعت در بیو روشن شد.\n💡 برای تغییر فونت ساعت: `فونت ساعت [0-9]`")
    elif text == "ساعت بیو خاموش":
        ss("clock_bio_active", "0")
        await edit("⏰ ساعت در بیو خاموش شد.")

    # ─── اسپم ────────────────────────────────────────────────────────────────
    elif text.startswith("اسپم "):
        parts = text.split(" ", 2)
        if len(parts) >= 3 and parts[1].isdigit() and len(parts[2].strip()) > 0:
            count = _safe_int(parts[1])
            spam_text = parts[2]
            ss("spam_active", "1")
            label = f"{count} بار" if count <= 9999 else "نامحدود"
            await edit(f"💣 اسپم شروع شد — {label}\nبرای توقف: توقف اسپم")
            chat = await event.get_chat()
            asyncio.create_task(_do_spam(cl, owner_id, chat.id, spam_text, count))

    elif text == "توقف اسپم":
        ss("spam_active", "0")
        await edit("🛑 اسپم متوقف شد.")

    # ─── حذف خودکار ──────────────────────────────────────────────────────────
    elif text.startswith("حذف بعد "):
        parts = text.split()
        if len(parts) >= 3 and parts[2].isdigit():
            secs = _safe_int(parts[2])
            await edit(f"⏱️ پیام بعد از {secs} ثانیه حذف می‌شود.")
            await asyncio.sleep(secs)
            try:
                await msg.delete()
            except Exception:
                pass

    # ─── ذخیره پیام ──────────────────────────────────────────────────────────
    elif text.startswith("ذخیره "):
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            slot = _safe_int(parts[1])
            if 1 <= slot <= 10:
                replied = await event.get_reply_message()
                if replied:
                    db.save_message_slot(owner_id, slot, replied.text or "")
                    await edit(f"💾 پیام در اسلات {slot} ذخیره شد.")
                else:
                    await edit("❗ روی پیام مورد نظر ریپلای کن.")
            else:
                await edit("❗ اسلات باید بین ۱ تا ۱۰ باشد.")

    elif text.startswith("ارسال ذخیره "):
        parts = text.split()
        if len(parts) >= 3 and parts[2].isdigit():
            slot = _safe_int(parts[2])
            saved = db.get_message_slot(owner_id, slot)
            if saved:
                chat = await event.get_chat()
                await cl.send_message(chat.id, saved["content"])
                await msg.delete()
            else:
                await edit(f"❗ اسلات {slot} خالی است.")

    # ─── ترجمه ───────────────────────────────────────────────────────────────
    elif text.startswith("ترجمه "):
        to_tr = text[len("ترجمه "):].strip()
        if not to_tr:
            replied = await event.get_reply_message()
            if replied:
                to_tr = replied.text or ""
        if to_tr:
            await edit(f"🌐 ترجمه:\n{await _translate(to_tr)}")
        else:
            await edit("❗ متن یا ریپلای لازم است.")

    # ─── هواشناسی ────────────────────────────────────────────────────────────
    elif text.startswith("هوا "):
        await edit(await _get_weather(text[len("هوا "):].strip()))

    # ─── قیمت ارز ────────────────────────────────────────────────────────────
    elif text == "ارز" or text == "قیمت دلار" or text.startswith("ارز "):
        sub = text[len("ارز"):].strip() if text != "قیمت دلار" else "دلار"
        sub = sub.replace("‌", " ").replace("‏", " ")
        if any(k in sub for k in ("بیت کوین", "بیتکوین", "bitcoin", "btc")):
            target = "btc"
        elif any(k in sub for k in ("تتر", "tether", "usdt")):
            target = "usdt"
        elif any(k in sub for k in ("یورو", "eur")):
            target = "eur"
        elif any(k in sub for k in ("پوند", "gbp")):
            target = "gbp"
        elif any(k in sub for k in ("دلار", "usd")):
            target = "usd"
        else:
            target = None
        await edit(await _get_currency_text(target))

    # ─── جوین اجباری ─────────────────────────────────────────────────────────
    elif text.startswith("تنظیم کانال "):
        channel_raw = text[len("تنظیم کانال "):].strip()
        if not channel_raw:
            await edit("❗ فرمت: تنظیم کانال [آیدی یا @یوزرنیم]")
        else:
            channel_input = channel_raw
            try:
                entity = await cl.get_entity(
                    _safe_int(channel_input.lstrip("-")) * (-1 if channel_input.startswith("-") else 1)
                    if channel_input.lstrip("-").isdigit() else channel_input
                )
                real_id = str(entity.id)
                title = getattr(entity, "title", channel_input)
                ss("force_join_channel", real_id)
                ss("force_join_active", "1")
                await edit(
                    f"✅ کانال جوین اجباری تنظیم شد:\n"
                    f"📢 {title} (ID: {real_id})\n\n"
                    f"💡 دستورات:\n"
                    f" > `جوین اجباری روشن` / `جوین اجباری خاموش`\n"
                    f" > `پیام جوین [متن]` — تغییر پیام هشدار"
                )
            except Exception as e:
                await edit(f"❌ کانال پیدا نشد: {e}\n\n💡 مطمئن شو سلف عضو کانال/گروه هست.")

    elif text == "حذف کانال اجباری":
        ss("force_join_channel", "")
        ss("force_join_active", "0")
        await edit("🗑️ کانال جوین اجباری حذف شد.")

    elif text == "جوین اجباری روشن":
        channel_id = gs("force_join_channel", "")
        if not channel_id:
            await edit("❗ اول کانال رو تنظیم کن: `تنظیم کانال [آیدی]`")
        else:
            ss("force_join_active", "1")
            await edit("✅ جوین اجباری روشن شد.")

    elif text == "جوین اجباری خاموش":
        ss("force_join_active", "0")
        await edit("❌ جوین اجباری خاموش شد.")

    elif text.startswith("پیام جوین "):
        new_msg = text[len("پیام جوین "):].strip()
        if not new_msg:
            await edit("❗ فرمت: پیام جوین [متن پیام]")
        else:
            ss("force_join_message", new_msg)
            await edit(f"✅ پیام جوین اجباری تنظیم شد:\n\n{new_msg}")

    elif text.startswith("لینک کانال جوین "):
        link = text[len("لینک کانال جوین "):].strip()
        if not link:
            await edit("❗ فرمت: لینک کانال جوین [لینک]\nمثال: لینک کانال جوین https://t.me/mychannel")
        else:
            if not link.startswith("http"):
                link = "https://t.me/" + link.lstrip("@")
            ss("force_join_link", link)
            await edit(f"✅ لینک دکمه جوین تنظیم شد:\n{link}")

    # ─── وضعیت ───────────────────────────────────────────────────────────────
    elif text == "وضعیت":
        status_map = {
            "self_bot_active": "سلف‌بات", "secretary_active": "منشی",
            "anti_delete_active": "ضد حذف", "anti_link_active": "ضد لینک",
            "auto_seen_active": "سین خودکار", "auto_reaction_active": "ری‌اکشن",
            "private_lock_active": "قفل پیوی", "enemy_reply_active": "پاسخ دشمن",
            "auto_save_media": "ذخیره مدیا", "clock_name_active": "ساعت نام",
            "clock_bio_active": "ساعت بیو", "force_join_active": "جوین اجباری",
        }
        lines = [f"📊 وضعیت {config.BOT_NAME} v{config.BOT_VERSION}\n"]
        for key, label in status_map.items():
            icon = "✅" if gs(key) == "1" else "❌"
            lines.append(f"{icon} {label}")
        lines.append(f"\n🔤 فونت: {gs('selected_font', '0')}")
        lines.append(f"✏️ فونت متن خودکار: {'✅ روشن' if gs('text_font_auto', '0') == '1' else '❌ خاموش'}")
        lines.append(f"⏰ فونت ساعت: {gs('selected_clock_font', '0')}")
        fj_ch = gs("force_join_channel", "")
        if fj_ch:
            lines.append(f"📢 کانال جوین اجباری: {fj_ch}")
        lines.append(f"👥 دشمن: {len(db.get_enemies(owner_id))} نفر")
        lines.append(f"💚 دوست: {len(db.get_friends(owner_id))} نفر")
        await edit("\n".join(lines))

    # ─── راهنما ──────────────────────────────────────────────────────────────
    elif text in ("راهنما", "help"):
        await edit(_help_text())

    # ─── ارسال زمان‌بندی شده ─────────────────────────────────────────────────
    elif text.startswith("ارسال زمان‌بندی "):
        m = re.match(r"^ارسال زمان‌بندی (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) (.+)$", text, re.DOTALL)
        if m:
            chat = await event.get_chat()
            db.add_scheduled_message(owner_id, chat.id, m.group(2), m.group(1) + ":00")
            await edit(f"📅 پیام در {m.group(1)} ارسال خواهد شد.")
        else:
            await edit("❗ فرمت: ارسال زمان‌بندی [YYYY-MM-DD HH:MM] متن")

    # ─── پیام عادی — اعمال فونت اگه حالت خودکار روشنه ───────────────────────
    else:
        font_id = gs("selected_font", "0")
        auto_active = gs("text_font_auto", "0") == "1"
        if auto_active and font_id != "0" and text:
            fn = FONTS.get(font_id, FONTS["0"])
            styled = fn(text)
            if styled != text:
                try:
                    await event.edit(styled)
                except FloodWaitError as e:
                    wait_time = min(e.seconds + 1, 60)
                    await asyncio.sleep(wait_time)
                except Exception:
                    pass


# ─── توابع کمکی ───────────────────────────────────────────────────────────────
async def _do_spam(cl, owner_id: int, chat_id: int, text: str, count: int):
    """اسپم با مدیریت FloodWait"""
    delay = float(db.get_setting(owner_id, "spam_delay", "1") or "1")
    sent = 0
    while True:
        if db.get_setting(owner_id, "spam_active") != "1":
            break
        if sent >= count:
            break
        try:
            await cl.send_message(chat_id, text)
            sent += 1
            await asyncio.sleep(delay)
        except FloodWaitError as e:
            wait_time = min(e.seconds + 1, 60)
            await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error("[%s] خطا در اسپم: %s", owner_id, e)
            break
    db.set_setting(owner_id, "spam_active", "0")


async def _save_channel_media(cl, channel_input: str, limit: Optional[int], owner_id: int):
    """ذخیره مدیا از کانال"""
    db.set_setting(owner_id, "channel_save_active", "1")
    media_dir = _get_media_dir(owner_id)
    try:
        me = await cl.get_me()

        # حالت ۱: لینک یک پست خاص
        post_match = _POST_LINK_RE.match(channel_input)
        if post_match:
            channel_username, post_id = post_match.group(1), _safe_int(post_match.group(2))
            try:
                target_msg = await cl.get_messages(channel_username, ids=post_id)
            except Exception as e:
                await cl.send_message(me.id, f"❌ پست پیدا نشد: {e}")
                db.set_setting(owner_id, "channel_save_active", "0")
                return

            if not target_msg or not target_msg.media:
                await cl.send_message(me.id, "❗ این پست مدیا ندارد یا پیدا نشد.")
            else:
                try:
                    path = await cl.download_media(target_msg, file=media_dir + "/")
                    caption = f"📥 سیو پست\n📌 پیام #{target_msg.id}"
                    if target_msg.text:
                        caption += f"\n📝 {target_msg.text[:100]}"
                    await cl.send_file(me.id, path, caption=caption)
                    await cl.send_message(me.id, "✅ پست با موفقیت ذخیره شد.")
                except Exception as e:
                    await cl.send_message(me.id, f"❌ خطا در ذخیره پست: {e}")
            db.set_setting(owner_id, "channel_save_active", "0")
            return

        # حالت ۲: کانال + تعداد
        limit = limit or 100
        if channel_input.startswith("https://t.me/"):
            channel_input = channel_input.replace("https://t.me/", "")
        if channel_input.startswith("@"):
            channel_input = channel_input[1:]

        saved = skipped = 0
        async for msg in cl.iter_messages(channel_input, limit=limit):
            if db.get_setting(owner_id, "channel_save_active") != "1":
                break
            if msg.media:
                try:
                    path = await cl.download_media(msg, file=media_dir + "/")
                    if path:
                        caption = f"📥 سیو کانال\n📌 پیام #{msg.id}"
                        if msg.text:
                            caption += f"\n📝 {msg.text[:100]}"
                        await cl.send_file(me.id, path, caption=caption)
                        saved += 1
                        await asyncio.sleep(1.5)
                except FloodWaitError as e:
                    wait_time = min(e.seconds + 2, 60)
                    await asyncio.sleep(wait_time)
                except Exception:
                    skipped += 1
            else:
                skipped += 1

        db.set_setting(owner_id, "channel_save_active", "0")
        await cl.send_message(me.id, f"✅ سیو کانال تموم شد\n💾 ذخیره شد: {saved}\n⏭ رد شد: {skipped}")
    except Exception as e:
        db.set_setting(owner_id, "channel_save_active", "0")
        try:
            me = await cl.get_me()
            await cl.send_message(me.id, f"❌ خطا در سیو کانال: {e}")
        except Exception:
            pass


async def _translate(text: str) -> str:
    """ترجمه متن به فارسی"""
    try:
        import urllib.request, urllib.parse, json
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=fa&dt=t&q={urllib.parse.quote(text)}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data[0][0][0]
    except Exception:
        return "⚠️ خطا در ترجمه"


async def _get_weather(city: str) -> str:
    """دریافت اطلاعات هواشناسی"""
    try:
        import urllib.request, urllib.parse, json
        api_key = config.WEATHER_API_KEY
        if not api_key:
            return "⚠️ کلید API هواشناسی تنظیم نشده."
        url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid={api_key}&units=metric&lang=fa"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return (
                f"🌤️ هوای {city}:\n"
                f"وضعیت: {data['weather'][0]['description']}\n"
                f"دما: {data['main']['temp']}°C\n"
                f"رطوبت: {data['main']['humidity']}%"
            )
    except Exception:
        return "⚠️ خطا در دریافت اطلاعات هوا"


_CURRENCY_LABELS = {
    "usd": "💵 دلار آمریکا",
    "eur": "💶 یورو",
    "gbp": "💷 پوند انگلیس",
    "usdt": "💎 تتر (USDT)",
    "btc": "₿ بیت‌کوین",
    "eth": "⟠ اتریوم",
}
_CURRENCY_DEFAULT_LIST = ("usd", "eur", "gbp", "usdt", "btc", "eth")
_currency_cache = {"data": {}, "ts": 0.0}
_CURRENCY_CACHE_TTL = 60


async def _fetch_currency_prices() -> dict:
    """دریافت قیمت ارزها به تومان"""
    now = time.time()
    if now - _currency_cache["ts"] < _CURRENCY_CACHE_TTL and _currency_cache["data"]:
        return _currency_cache["data"]

    loop = asyncio.get_event_loop()
    result = {}

    # مرحله ۱: نرخ دلار آزاد از Nobitex
    usd_toman = 0
    for src in ("usdt", "btc", "eth"):
        try:
            nb = await loop.run_in_executor(
                None, lambda s=src: _fetch_json_sync(
                    "https://api.nobitex.ir/market/stats",
                    json_body={"srcCurrency": s, "dstCurrency": "rls"}, timeout=8
                )
            )
            rial = float(nb["stats"][f"{src}-rls"]["latest"])
            val = int(rial / 10)
            result[src] = val
            if src == "usdt":
                usd_toman = val
                result["usd"] = val
        except Exception as e:
            logger.warning("Nobitex %s: %s", src, e)

    # مرحله ۲: نرخ یورو/پوند
    if usd_toman:
        try:
            fx = await loop.run_in_executor(
                None, lambda: _fetch_json_sync(
                    "https://open.er-api.com/v6/latest/USD", timeout=8
                )
            )
            rates = fx.get("rates", {})
            if rates.get("EUR"):
                result["eur"] = int(usd_toman * rates["EUR"])
            if rates.get("GBP"):
                result["gbp"] = int(usd_toman * rates["GBP"])
            if rates.get("AED"):
                result["aed"] = int(usd_toman * rates["AED"])
        except Exception as e:
            logger.warning("exchangerate EUR/GBP: %s", e)
            result.setdefault("eur", int(usd_toman * 1.08))
            result.setdefault("gbp", int(usd_toman * 1.27))

    # مرحله ۳: BTC/ETH از CoinGecko
    if usd_toman and ("btc" not in result or "eth" not in result):
        try:
            cg = await loop.run_in_executor(
                None, lambda: _fetch_json_sync(
                    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd",
                    timeout=10
                )
            )
            btc_usd = cg.get("bitcoin", {}).get("usd", 0)
            eth_usd = cg.get("ethereum", {}).get("usd", 0)
            if btc_usd:
                result["btc"] = int(btc_usd * usd_toman)
            if eth_usd:
                result["eth"] = int(eth_usd * usd_toman)
        except Exception as e:
            logger.warning("CoinGecko: %s", e)

    if not result:
        return _currency_cache.get("data") or {}

    _currency_cache["data"] = result
    _currency_cache["ts"] = now
    return result


def _fetch_json_sync(url, json_body=None, timeout=6, retries=3):
    """درخواست HTTP همگام"""
    import urllib.request, json as _json, time as _time
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    if json_body is not None:
        req.data = _json.dumps(json_body).encode()
        req.add_header("Content-Type", "application/json")
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return _json.loads(resp.read().decode())
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                _time.sleep(2 ** attempt)
    raise last_err


async def _get_currency_text(target: str = None) -> str:
    """دریافت متن قیمت ارز"""
    prices = await _fetch_currency_prices()
    if not prices:
        return "❌ دریافت قیمت ممکن نیست"
    if target:
        if target not in prices:
            return "❌ دریافت قیمت ممکن نیست"
        return f"- {_CURRENCY_LABELS[target]}: {prices[target]:,} تومان"

    lines = [
        f"- {_CURRENCY_LABELS[c]}: {prices[c]:,} تومان"
        for c in _CURRENCY_DEFAULT_LIST if c in prices
    ]
    return "\n".join(lines) if lines else "❌ دریافت قیمت ممکن نیست"


def _help_text() -> str:
    """متن راهنما"""
    sections = [
        ("🔹 اصلی", ["سلف روشن", "سلف خاموش", "وضعیت", "راهنما"]),
        ("🔹 لیست‌ها", [
            "تنظیم دشمن  ← ریپلای روی پیام",
            "حذف دشمن  ← ریپلای یا آیدی",
            "نمایش لیست دشمن",
            "پاک کردن لیست دشمن",
            "تنظیم دوست  ← ریپلای روی پیام",
            "حذف دوست  ← ریپلای یا آیدی",
            "نمایش لیست دوست",
            "پاک کردن لیست دوست",
        ]),
        ("🔹 منشی", [
            "منشی روشن",
            "منشی خاموش",
            "پیام منشی [متن]",
            "💡 هر کاربر هر ۲۴ ساعت یک بار پاسخ می‌گیرد",
        ]),
        ("🔹 امنیت", [
            "ضد حذف روشن", "ضد حذف خاموش",
            "ضد لینک روشن", "ضد لینک خاموش",
            "قفل پیوی روشن", "قفل پیوی خاموش",
            "پاسخ دشمن روشن", "پاسخ دشمن خاموش",
        ]),
        ("🔹 جوین اجباری", [
            "تنظیم کانال [آیدی یا @یوزرنیم]",
            "لینک کانال جوین [لینک]",
            "پیام جوین [متن]",
            "جوین اجباری روشن / خاموش",
            "حذف کانال اجباری",
        ]),
        ("🔹 اتوماسیون", [
            "سین خودکار روشن", "سین خودکار خاموش",
            "ری‌اکشن روشن", "ری‌اکشن خاموش",
            "ری‌اکشن [ایموجی]",
            "ذخیره مدیا روشن", "ذخیره مدیا خاموش",
            "ساعت نام روشن", "ساعت نام خاموش",
            "ساعت بیو روشن", "ساعت بیو خاموش",
        ]),
        ("🔹 ابزار", [
            "ترجمه [متن]",
            "هوا [شهر]",
            "ارز  ← دلار، تتر، یورو، پوند",
            "ارز دلار / ارز تتر / ارز یورو / ارز پوند / ارز بیت کوین",
        ]),
        ("🔹 اسپم", [
            "اسپم [تعداد] [متن]  ← مثال: اسپم 100 سلام",
            "توقف اسپم",
        ]),
        ("🔹 پیام", [
            "ذخیره [1-10]  ← ریپلای",
            "ارسال ذخیره [1-10]",
            "حذف بعد [ثانیه]",
            "ارسال زمان‌بندی [YYYY-MM-DD HH:MM] متن",
        ]),
        ("🔹 سیو مدیا", [
            "سیو کانال [لینک پست]  ← ذخیره یک پست",
            "سیو کانال [@کانال] [تعداد]  ← ذخیره چند پست",
            "توقف سیو",
        ]),
        ("🔹 قالب‌بندی", [
            "بولد [متن]", "ایتالیک [متن]", "مونو [متن]",
            "اسپویلر [متن]", "کوت [متن]", "خط‌خورده [متن]", "زیرخط [متن]",
        ]),
        ("🔹 فونت", [
            "فونت [0-8]", "فونت [متن] [0-8]", "لیست فونت",
            "فونت متن روشن", "فونت متن خاموش", "بنویس [متن]",
            "فونت ساعت [0-9]", "لیست فونت ساعت",
        ]),
    ]
    parts = ["📖 راهنمای NexoSelf\n"]
    for title, cmds in sections:
        parts.append(f"\n{title}")
        for cmd in cmds:
            parts.append(f" > `{cmd}`")
    return "\n".join(parts)


# ─── حلقه‌های پس‌زمینه ─────────────────────────────────────────────────────────
async def _clock_loop(cl: TelegramClient, owner_id: int):
    """به‌روزرسانی ساعت نام/بیو"""
    last_minute = -1
    while True:
        try:
            iran_tz = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
            now = datetime.datetime.now(iran_tz)
            current_minute = now.minute

            if current_minute != last_minute:
                last_minute = current_minute
                time_str = f"{now.hour:02d}:{now.minute:02d}"
                styled_time = _apply_clock_font(owner_id, time_str)

                if db.get_setting(owner_id, "clock_name_active") == "1":
                    try:
                        await cl(UpdateProfileRequest(last_name=styled_time[:64]))
                        logger.debug("[%s] ساعت نام به‌روز شد", owner_id)
                    except Exception as e:
                        logger.warning("[%s] خطا در به‌روزرسانی نام: %s", owner_id, e)

                if db.get_setting(owner_id, "clock_bio_active") == "1":
                    try:
                        await cl(UpdateProfileRequest(about=f"⏰ {styled_time}"[:70]))
                        logger.debug("[%s] ساعت بیو به‌روز شد", owner_id)
                    except Exception as e:
                        logger.warning("[%s] خطا در به‌روزرسانی بیو: %s", owner_id, e)

            await asyncio.sleep(5)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[%s] خطا در _clock_loop: %s", owner_id, e)
            await asyncio.sleep(10)


async def _scheduler_loop(cl: TelegramClient, owner_id: int):
    """ارسال پیام‌های زمان‌بندی‌شده"""
    while True:
        try:
            for p in db.get_pending_scheduled(owner_id):
                try:
                    await cl.send_message(p["chat_id"], p["message"])
                    db.mark_scheduled_sent(p["id"])
                except Exception as e:
                    logger.error("[%s] خطا در ارسال پیام زمان‌بندی: %s", owner_id, e)

            await asyncio.sleep(30)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("[%s] خطا در _scheduler_loop: %s", owner_id, e)
            await asyncio.sleep(30)


# ─── BotManager (سازگار با bot_manager.py) ────────────────────────────────────
class BotManager:
    """مدیریت چندین کلاینت تلگرام همزمان (نسخه سازگار با AdvancedBotManager)"""

    def __init__(self):
        self._bots: Dict[int, Dict[str, Any]] = {}
        self._timers: Dict[int, threading.Timer] = {}
        self._timer_starts: Dict[int, float] = {}
        self._sub_watchers: Dict[int, threading.Timer] = {}
        self._lock = threading.RLock()

    def is_running(self, owner_id: int) -> bool:
        """بررسی آیا بات در حال اجراست"""
        if not _validate_owner_id(owner_id):
            return False
        with self._lock:
            entry = self._bots.get(owner_id)
            return bool(entry and not entry.get("task", None) or not entry.get("task", None).done())

    def get_client(self, owner_id: int) -> Optional[TelegramClient]:
        """دریافت کلاینت یک بات"""
        if not _validate_owner_id(owner_id):
            return None
        with self._lock:
            entry = self._bots.get(owner_id)
            return entry["client"] if entry else None

    def _cancel_timer(self, owner_id: int):
        """لغو تایمر انقضا"""
        with self._lock:
            t = self._timers.pop(owner_id, None)
            self._timer_starts.pop(owner_id, None)
        if t:
            try:
                t.cancel()
                logger.debug("[%s] تایمر لغو شد", owner_id)
            except Exception as e:
                logger.warning("[%s] خطا در لغو تایمر: %s", owner_id, e)

    def session_end_time(self, owner_id: int) -> Optional[float]:
        """دریافت زمان باقی‌مانده تا انقضای سشن"""
        if not _validate_owner_id(owner_id):
            return None
        with self._lock:
            start = self._timer_starts.get(owner_id)
            if start is None:
                return None
            elapsed = time.time() - start
            remaining = (config.SESSION_HOURS * 3600) - elapsed
            return max(0.0, remaining)

    def start(self, owner_id: int, loop: asyncio.AbstractEventLoop,
              check_tokens: bool = True, is_restart: bool = False) -> bool:
        """شروع یک بات"""
        if not _validate_owner_id(owner_id):
            logger.error("owner_id نامعتبر: %s", owner_id)
            return False

        logger.info("[%s] شروع فرآیند استارت%s", owner_id, " (ریستارت)" if is_restart else "")

        if self.is_running(owner_id):
            self.stop(owner_id)
            time.sleep(0.3)

        # بررسی اشتراک
        try:
            tg_id = db.get_telegram_id_by_owner(owner_id)
            is_owner = (tg_id is not None and tg_id == config.OWNER_TG_ID)

            if not is_owner and not db.is_subscribed(owner_id):
                logger.warning("[%s] اشتراک منقضی شده", owner_id)
                return False
        except Exception as e:
            logger.error("[%s] خطا در بررسی اشتراک: %s", owner_id, e)
            return False

        # محاسبه زمان باقی‌مانده
        now_ts = time.time()
        remaining = None
        reset_started_at = False

        if config.BOT_TOKEN and not is_owner:
            if is_restart:
                started_raw = db.get_setting(owner_id, "session_started_at", "")
                try:
                    started_at = float(started_raw) if started_raw else None
                except (TypeError, ValueError):
                    started_at = None

                if started_at is None:
                    started_at = now_ts

                remaining = (config.SESSION_HOURS * 3600) - (now_ts - started_at)
                if remaining <= 0:
                    remaining = config.SESSION_HOURS * 3600
                    reset_started_at = True
            else:
                remaining = config.SESSION_HOURS * 3600
                reset_started_at = True

        # کسر توکن
        tokens_deducted = 0
        if config.BOT_TOKEN and check_tokens and not is_owner:
            try:
                balance = db.get_token_balance(owner_id)
                if balance < config.TOKENS_PER_SESSION:
                    logger.error("[%s] توکن کافی نیست: %s < %s", owner_id, balance, config.TOKENS_PER_SESSION)
                    return False
                db.deduct_tokens(owner_id, config.TOKENS_PER_SESSION)
                tokens_deducted = config.TOKENS_PER_SESSION
                logger.info("[%s] %s توکن کسر شد", owner_id, tokens_deducted)
            except Exception as e:
                logger.error("[%s] خطا در کسر توکن: %s", owner_id, e)
                return False

        # ساخت entry (سازگار با AdvancedBotManager)
        entry = {
            "client": None,
            "task": None,
            "stop": False,
            "is_owner": is_owner,
            "tokens_deducted": tokens_deducted,
            "owner_refunded": False,
            "paused": False,
            "loop": loop,
            "state": None,  # برای سازگاری با BotState
            "retry_count": 0,
            "start_time": now_ts,
            "last_heartbeat": now_ts,
        }

        with self._lock:
            self._bots[owner_id] = entry

        # استارت تسک
        try:
            task = asyncio.run_coroutine_threadsafe(self._run_bot(owner_id), loop)
            with self._lock:
                if owner_id in self._bots:
                    self._bots[owner_id]["task"] = task
        except Exception as e:
            logger.error("[%s] خطا در استارت تسک: %s", owner_id, e)
            with self._lock:
                self._bots.pop(owner_id, None)
            return False

        # تنظیم تایمر
        if config.BOT_TOKEN and not is_owner:
            self._cancel_timer(owner_id)
            if reset_started_at:
                db.set_setting(owner_id, "session_started_at", str(now_ts))

            timer = threading.Timer(remaining, self.stop, args=[owner_id])
            timer.daemon = True
            timer.start()

            with self._lock:
                self._timers[owner_id] = timer
                self._timer_starts[owner_id] = now_ts

            logger.info("[%s] تایمر %s ساعته تنظیم شد", owner_id, config.SESSION_HOURS)

        # تایمر چک اشتراک
        if not is_owner:
            self._start_subscription_watcher(owner_id)

        logger.info("[%s] بات با موفقیت استارت شد", owner_id)
        return True

    def pause(self, owner_id: int):
        """متوقف کردن موقت عملیات"""
        if not _validate_owner_id(owner_id):
            return
        with self._lock:
            entry = self._bots.get(owner_id)
            if entry and not entry.get("is_owner"):
                entry["paused"] = True
                logger.info("[%s] سلف موقتاً متوقف شد", owner_id)

    def resume(self, owner_id: int):
        """از سرگیری عملیات"""
        if not _validate_owner_id(owner_id):
            return
        with self._lock:
            entry = self._bots.get(owner_id)
            if entry and entry.get("paused"):
                entry["paused"] = False
                logger.info("[%s] سلف دوباره فعال شد", owner_id)

    def is_paused(self, owner_id: int) -> bool:
        """بررسی وضعیت pause"""
        if not _validate_owner_id(owner_id):
            return False
        with self._lock:
            entry = self._bots.get(owner_id)
            return bool(entry and entry.get("paused"))

    def _subscription_check(self, owner_id: int):
        """بررسی دوره‌ای اشتراک"""
        if not self.is_running(owner_id):
            return

        with self._lock:
            entry = self._bots.get(owner_id)
            if entry and entry.get("is_owner"):
                return

        try:
            subscribed = db.is_subscribed(owner_id)
            if not subscribed:
                self.pause(owner_id)
            else:
                self.resume(owner_id)
        except Exception as e:
            logger.error("[%s] خطا در بررسی اشتراک: %s", owner_id, e)

        self._start_subscription_watcher(owner_id)

    def _start_subscription_watcher(self, owner_id: int):
        """شروع تایمر چک اشتراک"""
        with self._lock:
            old = self._sub_watchers.pop(owner_id, None)
        if old:
            try:
                old.cancel()
            except Exception:
                pass

        timer = threading.Timer(300, self._subscription_check, args=[owner_id])
        timer.daemon = True
        timer.start()

        with self._lock:
            self._sub_watchers[owner_id] = timer

    def stop(self, owner_id: int):
        """متوقف کردن کامل بات"""
        if not _validate_owner_id(owner_id):
            return

        logger.info("[%s] در حال توقف...", owner_id)

        # لغو تایمرها
        self._cancel_timer(owner_id)

        # لغو watcher
        with self._lock:
            watcher = self._sub_watchers.pop(owner_id, None)
        if watcher:
            try:
                watcher.cancel()
            except Exception:
                pass

        with self._lock:
            entry = self._bots.get(owner_id)
            if not entry:
                return
            entry["stop"] = True
            client = entry.get("client")
            loop = entry.get("loop")

        # disconnect کلاینت
        if client and loop:
            try:
                if client.is_connected():
                    future = asyncio.run_coroutine_threadsafe(client.disconnect(), loop)
                    try:
                        future.result(timeout=5.0)
                    except Exception as e:
                        logger.warning("[%s] خطا در disconnect: %s", owner_id, e)
            except Exception as e:
                logger.warning("[%s] خطا در ارسال disconnect: %s", owner_id, e)

        with self._lock:
            self._bots.pop(owner_id, None)

        logger.info("[%s] بات متوقف شد", owner_id)

    def stop_all(self):
        """متوقف کردن همه بات‌ها"""
        logger.info("توقف همه بات‌ها...")
        with self._lock:
            owners = list(self._bots.keys())

        for oid in owners:
            try:
                self.stop(oid)
            except Exception as e:
                logger.error("[%s] خطا در توقف: %s", oid, e)

        logger.info("همه بات‌ها متوقف شدند")

    async def _run_bot(self, owner_id: int):
        """اجرای اصلی بات با Auto Reconnect"""
        MAX_RETRIES = getattr(config, "MAX_RECONNECT_RETRIES", 10)
        retry_count = 0
        retry_delay = 5

        while retry_count < MAX_RETRIES:
            with self._lock:
                entry = self._bots.get(owner_id)
                if not entry or entry["stop"]:
                    break

            try:
                # دریافت session
                session_data = db.get_setting(owner_id, "session_data", "")
                if not session_data:
                    logger.warning("[%s] session یافت نشد", owner_id)
                    retry_count += 1
                    await asyncio.sleep(min(retry_delay * (2 ** min(retry_count, 3)), 30))
                    continue

                # ساخت کلاینت
                cl = TelegramClient(
                    StringSession(session_data),
                    config.API_ID,
                    config.API_HASH,
                    connection_retries=5,
                    retry_delay=2,
                    auto_reconnect=True,
                )

                with self._lock:
                    if owner_id in self._bots:
                        self._bots[owner_id]["client"] = cl

                # ثبت هندلرها
                _register_handlers(cl, owner_id, entry)

                # اتصال
                await cl.start()
                me = await cl.get_me()
                logger.info("[%s] بات متصل شد — @%s", owner_id, me.username or me.first_name)

                db.save_telegram_user_id(owner_id, me.id)

                # تشخیص مالک
                if _is_owner_account(me):
                    with self._lock:
                        if owner_id in self._bots:
                            self._bots[owner_id]["is_owner"] = True
                    self._cancel_timer(owner_id)

                    with self._lock:
                        refunded = entry.get("owner_refunded", False)
                        deducted = entry.get("tokens_deducted", 0)

                    if not refunded and deducted > 0:
                        try:
                            db.add_tokens(owner_id, deducted)
                            with self._lock:
                                if owner_id in self._bots:
                                    self._bots[owner_id]["owner_refunded"] = True
                            logger.info("[%s] مالک — %s توکن برگشت", owner_id, deducted)
                        except Exception as e:
                            logger.error("[%s] خطا در برگشت توکن: %s", owner_id, e)

                # استارت تسک‌های پس‌زمینه
                clock_task = asyncio.create_task(_clock_loop(cl, owner_id))
                sched_task = asyncio.create_task(_scheduler_loop(cl, owner_id))

                retry_count = 0
                retry_delay = 5

                # منتظر قطع شدن
                await cl.run_until_disconnected()

                # لغو تسک‌های پس‌زمینه با مدیریت صحیح
                clock_task.cancel()
                sched_task.cancel()
                await asyncio.gather(clock_task, sched_task, return_exceptions=True)

                with self._lock:
                    entry = self._bots.get(owner_id)
                    if not entry or entry["stop"]:
                        break

                # بررسی session
                session_data = db.get_setting(owner_id, "session_data", "")
                if not session_data:
                    logger.warning("[%s] session حذف شده — توقف کامل", owner_id)
                    break

                logger.warning("[%s] اتصال قطع شد، تلاش مجدد...", owner_id)

            except UnauthorizedError:
                logger.error("[%s] Session نامعتبر — نیاز به لاگین مجدد", owner_id)
                db.set_setting(owner_id, "logged_in", "0")
                db.set_setting(owner_id, "session_data", "")
                break

            except asyncio.CancelledError:
                logger.warning("[%s] تسک لغو شد", owner_id)
                break

            except Exception as e:
                err_str = str(e)
                logger.error("[%s] خطا: %s", owner_id, e, exc_info=True)

                fatal_errors = ("AUTH_KEY_UNREGISTERED", "SESSION_REVOKED", "USER_DEACTIVATED")
                if any(k in err_str for k in fatal_errors):
                    logger.error("[%s] Session باطل شده — توقف کامل", owner_id)
                    db.set_setting(owner_id, "logged_in", "0")
                    db.set_setting(owner_id, "session_data", "")
                    break

                retry_count += 1
                if retry_count >= MAX_RETRIES:
                    logger.error("[%s] بیش از حد مجاز تلاش — توقف", owner_id)
                    break

            wait = min(retry_delay * (2 ** min(retry_count, 3)), 120)
            logger.info("[%s] تلاش مجدد در %.1f ثانیه...", owner_id, wait)
            await asyncio.sleep(wait)
            retry_delay = min(retry_delay * 2, 120)

        logger.info("[%s] بات متوقف شد", owner_id)
        with self._lock:
            self._bots.pop(owner_id, None)


# Singleton
bot_manager = BotManager()
