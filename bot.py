import asyncio
import re
import os
import json
import datetime
import random
import threading
import time
from telethon import TelegramClient, events
from telethon.tl.types import InputMediaDice
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.errors import FloodWaitError
import database as db
import config
from texts import ENEMY_REPLIES, FRIEND_REPLIES  

# ─── فونت‌ها ───────────────────────────────────────────────────────────────────
FONTS = {
    "0": lambda t: t,
    "1": lambda t: _convert_font(t, "𝗔𝗕𝗖𝗗𝗘𝗙𝗚𝗛𝗜𝗝𝗞𝗟𝗠𝗡𝗢𝗣𝗤𝗥𝗦𝗧𝗨𝗩𝗪𝗫𝗬𝗭𝗮𝗯𝗰𝗱𝗲𝗳𝗴𝗵𝗶𝗷𝗸𝗹𝗺𝗻𝗼𝗽𝗾𝗿𝘀𝘁𝘂𝘃𝘄𝘅𝘆𝘇"),
    "2": lambda t: _convert_font(t, "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻"),
    "3": lambda t: _convert_font(t, "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"),
    "4": lambda t: _convert_font(t, "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"),
    "5": lambda t: _convert_font(t, "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"),
    "6": lambda t: _convert_font(t, "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"),
    "7": lambda t: "".join(c + "\u0336" for c in t),
    "8": lambda t: "".join(c + "\u0332" for c in t),
}
_ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

LINK_PATTERN = re.compile(
    r"(https?://\S+|t\.me/\S+|telegram\.me/\S+|www\.\S+)", re.IGNORECASE
)

# لینک یک پست خاص، مثل: https://t.me/channelname/123 یا t.me/channelname/123
_POST_LINK_RE = re.compile(
    r"^(?:https?://)?t\.me/([A-Za-z0-9_]+)/(\d+)/?$", re.IGNORECASE
)

# ─── سیستم محدودیت زمانی برای منشی و دوست ────────────────────────────────────
_last_secretary_reply = {}  # {chat_id: timestamp}
_last_friend_reply = {}     # {sender_id: timestamp}
SECRETARY_COOLDOWN = 86400  # 24 ساعت
FRIEND_COOLDOWN = 3600      # 1 ساعت

# ─── دستیار هوش مصنوعی (دیپ‌سیک) ──────────────────────────────────────────────
_last_ai_reply = {}  # {chat_id: timestamp} — کول‌داون پاسخ هوش مصنوعی
_last_outgoing_activity = {}  # {owner_id: timestamp} — آخرین باری که خودِ کاربر پیام فرستاده
AI_AWAY_SECONDS = 300  # اگه ۵ دقیقه از آخرین پیامِ خودِ کاربر گذشته باشه، "غایب" در نظر گرفته می‌شه
AI_REPLY_COOLDOWN = 60  # حداقل فاصله بین دو پاسخ هوش مصنوعی در یک چت

def _convert_font(text, chars):
    result = []
    for ch in text:
        if ch in _ALPHA:
            result.append(chars[_ALPHA.index(ch)])
        else:
            result.append(ch)
    return "".join(result)


def _apply_font(owner_id, text):
    font_id = db.get_setting(owner_id, "selected_font", "0")
    fn = FONTS.get(font_id, FONTS["0"])
    return fn(text)


# ─── فونت‌های مخصوص ساعت (فقط روی ارقام اعمال می‌شود) ──────────────────────────
# ایموجی‌های ساعت آنالوگ برای حالت «ساعت پرمیوم» (ایندکس = ساعت به‌صورت ۱۲ ساعته)
_CLOCK_FACE_EMOJIS = [
    "🕛", "🕐", "🕑", "🕒", "🕓", "🕔",
    "🕕", "🕖", "🕗", "🕘", "🕙", "🕚",
]

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


def _apply_clock_font(owner_id, text):
    font_id = db.get_setting(owner_id, "selected_clock_font", "0")
    digits = CLOCK_FONTS.get(font_id, CLOCK_FONTS["0"])
    return "".join(digits[int(ch)] if ch.isdigit() else ch for ch in text)


_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")

def persian_time():
    iran_tz = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
    now = datetime.datetime.now(iran_tz)
    return f"{now.hour:02d}:{now.minute:02d}".translate(_SUPER)


# ─── BotManager: مدیریت چندین کلاینت همزمان ────────────────────────────────────
class BotManager:
    def __init__(self):
        self._bots = {}
        self._timers = {}

    def is_running(self, owner_id: int) -> bool:
        entry = self._bots.get(owner_id)
        return bool(entry and not entry["task"].done())

    def get_client(self, owner_id: int):
        entry = self._bots.get(owner_id)
        return entry["client"] if entry else None

    def get_owner_by_tg_id(self, tg_id: int):
        """
        از روی آیدی تلگرام کاربر (همان آیدی‌ای که به بات کمکی پنل وصل شده)
        owner_id و entry مربوط به سلف در حال اجرای او را پیدا می‌کند.
        فقط بین سلف‌های در حال اجرا جستجو می‌کند.
        """
        for owner_id, entry in self._bots.items():
            if not entry or not entry.get("client"):
                continue
            try:
                if db.get_telegram_id_by_owner(owner_id) == tg_id:
                    return owner_id, entry
            except Exception:
                continue
        return None, None

    def _cancel_timer(self, owner_id: int):
        t = self._timers.pop(owner_id, None)
        if t:
            t.cancel()

    def session_end_time(self, owner_id: int):
        t = self._timers.get(owner_id)
        if t and t.is_alive():
            remaining = t.interval - (time.time() - t._timer_start if hasattr(t, '_timer_start') else 0)
            return max(0, remaining)
        return None

    def start(self, owner_id: int, loop: asyncio.AbstractEventLoop, check_tokens: bool = True,
              is_restart: bool = False) -> bool:
        """
        is_restart=True یعنی این استارت یک «اتصال مجدد خودکار» است (مثلاً بعد از بالا آمدن
        دوباره‌ی سرور روی Render). در این حالت سلف کاربر همیشه باید روشن بماند و کاربر
        نباید مجبور باشد دوباره چیزی بزند؛ پس این حالت هیچ‌وقت استارت را مسدود نمی‌کند:
        اگر از زمان شروع سشن قبلی (ذخیره‌شده در Supabase) کمتر از SESSION_HOURS گذشته باشد،
        فقط زمان واقعی باقی‌مانده به تایمر داده می‌شود؛ اگر هم تمام شده باشد، به‌جای قطع کردن
        کاربر، یک پنجره‌ی تازه (fresh) برایش شروع می‌شود تا ری‌استارت سرور هیچ‌وقت سلف را
        برای کاربر خاموش نکند.
        """
        if self.is_running(owner_id):
            self.stop(owner_id)

        tg_id = db.get_telegram_id_by_owner(owner_id)
        is_owner = (tg_id is not None and tg_id == config.OWNER_TG_ID)

        # ─── چک اشتراک (پلن) ──────────────────────────────────────────────────
        if not is_owner and not db.is_subscribed(owner_id):
            return False

        # ─── محاسبه‌ی زمان باقی‌مانده‌ی سشن (قبل از وصل شدن) ────────────────────
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
                    # سشن قبلی تموم شده، ولی چون این یک اتصال مجدد خودکار بعد از
                    # ری‌استارت سرور است، کاربر را قطع نمی‌کنیم — یک پنجره‌ی تازه می‌دهیم
                    remaining = config.SESSION_HOURS * 3600
                    reset_started_at = True
            else:
                remaining = config.SESSION_HOURS * 3600
                reset_started_at = True

        tokens_deducted = 0
        if config.BOT_TOKEN and check_tokens and not is_owner:
            balance = db.get_token_balance(owner_id)
            if balance < config.TOKENS_PER_SESSION:
                return False
            db.deduct_tokens(owner_id, config.TOKENS_PER_SESSION)
            tokens_deducted = config.TOKENS_PER_SESSION

        entry = {"client": None, "task": None, "stop": False, "is_owner": is_owner,
                 "tokens_deducted": tokens_deducted, "owner_refunded": False, "paused": False}
        self._bots[owner_id] = entry
        task = asyncio.run_coroutine_threadsafe(
            self._run_bot(owner_id), loop
        )
        entry["task"] = task

        if config.BOT_TOKEN and not is_owner:
            self._cancel_timer(owner_id)
            if reset_started_at:
                # شروع تازه‌ی سشن (لاگین جدید، استارت دستی، یا ری‌استارت بعد از تمام
                # شدن پنجره‌ی قبلی) → زمان شروع جدید در Supabase ثبت می‌شود
                db.set_setting(owner_id, "session_started_at", str(now_ts))
            timer = threading.Timer(
                remaining, self.stop, args=[owner_id]
            )
            timer.daemon = True
            timer._timer_start = now_ts
            timer.start()
            self._timers[owner_id] = timer

        # ─── تایمر چک دوره‌ای اشتراک (هر ۵ دقیقه) ──────────────────────────
        if not is_owner:
            self._start_subscription_watcher(owner_id)

        return True

    def pause(self, owner_id: int):
        """کانکشن تلگرام رو نگه می‌داره ولی تمام عملیات سلف رو متوقف می‌کنه"""
        entry = self._bots.get(owner_id)
        if not entry or entry.get("is_owner"):
            return
        if not entry.get("paused"):
            entry["paused"] = True
            print(f"⏸️  [{owner_id}] پلن منقضی — سلف موقتاً متوقف شد (اتصال زنده‌ست)")

    def resume(self, owner_id: int):
        """بعد از تمدید پلن، سلف رو دوباره فعال می‌کنه"""
        entry = self._bots.get(owner_id)
        if not entry:
            return
        if entry.get("paused"):
            entry["paused"] = False
            print(f"▶️  [{owner_id}] پلن تمدید شد — سلف دوباره فعال شد")

    def is_paused(self, owner_id: int) -> bool:
        entry = self._bots.get(owner_id)
        return bool(entry and entry.get("paused"))

    def _subscription_check(self, owner_id: int):
        """هر ۵ دقیقه پلن رو چک می‌کنه — pause/resume می‌کنه، disconnect نمی‌کنه"""
        if not self.is_running(owner_id):
            return
        entry = self._bots.get(owner_id)
        if entry and entry.get("is_owner"):
            return
        if not db.is_subscribed(owner_id):
            self.pause(owner_id)
        else:
            # اگه پلن تمدید شده بود، resume کن
            self.resume(owner_id)
        # چک بعدی ۵ دقیقه دیگه
        self._start_subscription_watcher(owner_id)

    def _start_subscription_watcher(self, owner_id: int):
        """یک تایمر ۵ دقیقه‌ای برای چک پلن راه‌اندازی می‌کنه"""
        t = threading.Timer(300, self._subscription_check, args=[owner_id])
        t.daemon = True
        t.start()
        # نگه داشتن رفرنس در یک دیکشنری جداگانه
        if not hasattr(self, '_sub_watchers'):
            self._sub_watchers = {}
        self._sub_watchers[owner_id] = t

    def stop(self, owner_id: int):
        self._cancel_timer(owner_id)
        # لغو watcher پلن
        if hasattr(self, '_sub_watchers'):
            w = self._sub_watchers.pop(owner_id, None)
            if w:
                w.cancel()
        entry = self._bots.get(owner_id)
        if not entry:
            return
        entry["stop"] = True
        cl = entry.get("client")
        if cl and cl.is_connected():
            try:
                asyncio.run_coroutine_threadsafe(cl.disconnect(), asyncio.get_event_loop())
            except Exception:
                pass

    def stop_all(self):
        for oid in list(self._bots.keys()):
            self.stop(oid)

    async def _run_bot(self, owner_id: int):
        entry = self._bots[owner_id]
        retry_delay = 5

        while not entry["stop"]:
            try:
                session_data = db.get_setting(owner_id, "session_data", "")
                if not session_data:
                    await asyncio.sleep(2)
                    continue

                cl = TelegramClient(
                    StringSession(session_data),
                    config.API_ID,
                    config.API_HASH,
                )
                entry["client"] = cl
                _register_handlers(cl, owner_id, entry)

                await cl.start()
                me = await cl.get_me()
                print(f"✅ [{owner_id}] بات راه‌اندازی شد — {me.first_name} (@{me.username})")

                db.save_telegram_user_id(owner_id, me.id)
                _last_outgoing_activity[owner_id] = time.time()

                # ✅ تشخیص مالک - اصلاح شده با ۳ روش
                me_phone = (me.phone or "").lstrip("+")
                owner_phone = getattr(config, "OWNER_PHONE", "").lstrip("+")
                
                is_now_owner = (
                    me.id == config.OWNER_TG_ID or
                    (bool(owner_phone) and me_phone == owner_phone) or
                    me.username == getattr(config, "OWNER_USERNAME", "")
                )

                if is_now_owner:
                    entry["is_owner"] = True
                    self._cancel_timer(owner_id)
                    if not entry.get("owner_refunded") and entry.get("tokens_deducted", 0) > 0:
                        db.add_tokens(owner_id, entry["tokens_deducted"])
                        entry["owner_refunded"] = True
                        print(f"👑 [{owner_id}] مالک تشخیص داده شد - {entry['tokens_deducted']} توکن برگشت داده شد")
                    print(f"👑 [{owner_id}] مالک: @{me.username} (ID: {me.id}) — تایمر لغو — رایگان ♾️")

                # ✅ استارت ساعت با دقت بالا
                clock_task = asyncio.ensure_future(_clock_loop(cl, owner_id))
                sched_task = asyncio.ensure_future(_scheduler_loop(cl, owner_id))
                typing_task = asyncio.ensure_future(_typing_loop(cl, owner_id))

                retry_delay = 5
                await cl.run_until_disconnected()

                clock_task.cancel()
                sched_task.cancel()

                if entry["stop"]:
                    break

                # ✅ چک کن session هنوز در دیتابیس وجود داره
                try:
                    session_data = db.get_setting(owner_id, "session_data", "")
                    if not session_data:
                        print(f"⚠️  [{owner_id}] session حذف شده — توقف کامل")
                        break
                except Exception:
                    break

                print(f"⚠️  [{owner_id}] اتصال قطع شد، اتصال مجدد...")

            except Exception as e:
                err_str = str(e)
                print(f"❌ [{owner_id}] خطا: {e}")

                # ✅ اگه session توسط تلگرام باطل شده، نیاز به لاگین مجدد
                if any(k in err_str for k in ("AUTH_KEY_UNREGISTERED", "SESSION_REVOKED",
                                               "USER_DEACTIVATED", "UnauthorizedError")):
                    print(f"❌ [{owner_id}] Session باطل شده — نیاز به لاگین مجدد")
                    db.set_setting(owner_id, "logged_in", "0")
                    db.set_setting(owner_id, "session_data", "")
                    break

                if entry["stop"]:
                    break

            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 120)

        print(f"🛑 [{owner_id}] بات متوقف شد.")


bot_manager = BotManager()



# ─── ثبت هندلرها (per-user) ────────────────────────────────────────────────────
def _register_handlers(cl: TelegramClient, owner_id: int, entry: dict):

    @cl.on(events.NewMessage(incoming=True))
    async def on_incoming(event):
        # اگه پلن منقضی شده، هیچ کاری نکن (اتصال زنده‌ست)
        if entry.get("paused"):
            return
        msg = event.message
        sender = await event.get_sender()
        chat = await event.get_chat()
        sender_id = getattr(sender, "id", 0)
        chat_id = getattr(chat, "id", 0)
        text = msg.text or ""

        # ✅ سکوت: اگه فرستنده توی لیست سکوت باشه و پیوی باشه، پیام دوطرفه پاک می‌شه
        if event.is_private and sender_id and _is_silence_user(owner_id, sender_id):
            try:
                await msg.delete(revoke=True)
            except Exception:
                pass
            return

        # ✅ بررسی آیا ربات تگ شده است (برای گروه‌ها)
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

        # ✅ اگر در گروه است و تگ نشده، فقط کارهای خودکار را انجام بده
        if not event.is_private and not is_tagged:
            if db.get_setting(owner_id, "auto_seen_active") == "1":
                try:
                    await cl.send_read_acknowledge(chat_id, msg)
                except Exception:
                    pass
            
            if db.get_setting(owner_id, "auto_save_media") == "1" and msg.media:
                try:
                    media_dir = f"saved_media/{owner_id}"
                    os.makedirs(media_dir, exist_ok=True)
                    await cl.download_media(msg, file=media_dir + "/")
                except Exception:
                    pass
            return

        if db.is_silent_chat(owner_id, chat_id) or db.is_silent_user(owner_id, sender_id):
            return

        # ذخیره خودکار مدیا
        if db.get_setting(owner_id, "auto_save_media") == "1" and msg.media:
            try:
                media_dir = f"saved_media/{owner_id}"
                os.makedirs(media_dir, exist_ok=True)
                await cl.download_media(msg, file=media_dir + "/")
            except Exception:
                pass

        # ذخیره مدیای تایمدار
        if event.is_private and msg.media:
            ttl = getattr(msg.media, "ttl_seconds", None)
            if ttl:
                try:
                    me = await cl.get_me()
                    media_dir = f"saved_media/{owner_id}"
                    os.makedirs(media_dir, exist_ok=True)
                    path = await cl.download_media(msg, file=media_dir + "/")
                    if path:
                        await cl.send_file(me.id, path,
                            caption=f"📥 مدیای تایمدار ذخیره شد\n👤 از: {getattr(sender, 'first_name', sender_id)} ({sender_id})")
                except Exception:
                    pass

        # سین خودکار
        if db.get_setting(owner_id, "auto_seen_active") == "1":
            try:
                await cl.send_read_acknowledge(chat_id, msg)
            except Exception:
                pass

        # ✅ جوین اجباری (فقط پیوی)
        if event.is_private and db.get_setting(owner_id, "force_join_active") == "1":
            channel_id = db.get_setting(owner_id, "force_join_channel", "")
            if channel_id:
                is_member = False
                try:
                    from telethon.tl.functions.channels import GetParticipantRequest
                    from telethon.errors import UserNotParticipantError, ChannelPrivateError
                    try:
                        channel_entity = await cl.get_entity(int(channel_id) if channel_id.lstrip("-").isdigit() else channel_id)
                        await cl(GetParticipantRequest(channel_entity, sender_id))
                        is_member = True
                    except (UserNotParticipantError, KeyError):
                        is_member = False
                    except ChannelPrivateError:
                        is_member = True  # کانال خصوصی — نمی‌تونیم چک کنیم، رد می‌کنیم
                    except Exception:
                        is_member = True  # خطای ناشناخته — رد می‌کنیم تا اشتباهاً بلاک نشه
                except Exception:
                    is_member = True

                if not is_member:
                    # پیام رو حذف کن
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                    # پیام هشدار با دکمه رنگی جوین
                    join_msg = db.get_setting(owner_id, "force_join_message",
                        "⛔ برای ارسال پیام ابتدا باید در کانال ما عضو شوید.")
                    try:
                        # ساخت دکمه لینک کانال
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

        # ✅ منشی (فقط پیوی - با محدودیت 24 ساعت)
        if db.get_setting(owner_id, "secretary_active") == "1" and event.is_private:
            now = time.time()
            last_reply = _last_secretary_reply.get(chat_id, 0)
            
            if now - last_reply >= SECRETARY_COOLDOWN:
                sec_msg = db.get_setting(owner_id, "secretary_message", "در حال حاضر در دسترس نیستم.")
                try:
                    await event.reply(sec_msg)
                    _last_secretary_reply[chat_id] = now
                except Exception:
                    pass
            return

        # ✅ دستیار هوش مصنوعی (دیپ‌سیک) — فقط وقتی کاربر پیوی و آفلاین/غایب باشه
        if (
            db.get_setting(owner_id, "ai_assistant_active") == "1"
            and event.is_private
            and sender_id != owner_id
        ):
            last_active = _last_outgoing_activity.get(owner_id, 0)
            is_away = (time.time() - last_active) >= AI_AWAY_SECONDS
            if is_away and text.strip():
                now = time.time()
                last_ai_reply = _last_ai_reply.get(chat_id, 0)
                if now - last_ai_reply >= AI_REPLY_COOLDOWN:
                    knowledge = db.get_setting(owner_id, "ai_knowledge_base", "")
                    try:
                        answer = await _ask_deepseek(knowledge, text)
                        if answer:
                            await event.reply(answer)
                            _last_ai_reply[chat_id] = now
                    except Exception as e:
                        print(f"خطا در پاسخ هوش مصنوعی: {e}")


        # ✅ ری‌اکشن خودکار
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
                print(f"⚠️ خطا در ری‌اکشن: {e}")

        # ✅ ری‌اکشن اختصاصی برای یک کاربر خاص
        react_map = _get_react_map(owner_id)
        if str(sender_id) in react_map:
            try:
                from telethon.tl.functions.messages import SendReactionRequest
                from telethon.tl.types import ReactionEmoji
                await cl(SendReactionRequest(
                    peer=chat_id,
                    msg_id=msg.id,
                    reaction=[ReactionEmoji(emoticon=react_map[str(sender_id)])],
                    big=False,
                    add_to_recent=True
                ))
            except Exception:
                pass

        # ✅ پاسخ خودکار محبت‌آمیز به دوستان (فقط در پیوی - با محدودیت 1 ساعت)
        if event.is_private and db.is_friend(owner_id, sender_id):
            now = time.time()
            last_reply = _last_friend_reply.get(sender_id, 0)
            
            if now - last_reply >= FRIEND_COOLDOWN:
                try:
                    await event.reply(random.choice(FRIEND_REPLIES))
                    _last_friend_reply[sender_id] = now
                except Exception:
                    pass

        # پاسخ به دشمن
        if db.get_setting(owner_id, "enemy_reply_active") == "1" and db.is_enemy(owner_id, sender_id):
            try:
                await event.reply(random.choice(ENEMY_REPLIES))
            except Exception:
                pass

        # ضد لینک (فقط پیوی)
        if db.get_setting(owner_id, "anti_link_active") == "1" and event.is_private and LINK_PATTERN.search(text):
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل پیوی (حذف پیام ورودی در پیوی)
        if db.get_setting(owner_id, "private_lock_active") == "1" and event.is_private:
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل یوزرنیم (پیامی که داخلش منشن @username باشه)
        if db.get_setting(owner_id, "lock_username_active") == "1" and event.is_private and re.search(r"@\w{4,32}", text):
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل ریپلای (پیامی که روی پیام دیگه‌ای ریپلای شده)
        if db.get_setting(owner_id, "lock_reply_active") == "1" and event.is_private and msg.is_reply:
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل گیف
        if db.get_setting(owner_id, "lock_gif_active") == "1" and event.is_private and msg.gif:
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل عکس
        if db.get_setting(owner_id, "lock_photo_active") == "1" and event.is_private and msg.photo:
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل استیکر
        if db.get_setting(owner_id, "lock_sticker_active") == "1" and event.is_private and msg.sticker:
            try:
                await msg.delete()
            except Exception:
                pass

        # قفل فوروارد (پیامِ فوروارد شده از یک چت دیگه)
        if db.get_setting(owner_id, "lock_forward_active") == "1" and event.is_private and msg.forward:
            try:
                await msg.delete()
            except Exception:
                pass

    @cl.on(events.NewMessage(outgoing=True))
    async def on_outgoing(event):
        text = event.raw_text.strip()

        # ثبت آخرین فعالیتِ خودِ کاربر — برای تشخیص «غایب/آفلاین» دستیار هوش مصنوعی
        _last_outgoing_activity[owner_id] = time.time()

        # دستورات همیشه فعال
        if text == "سلف روشن":
            db.set_setting(owner_id, "self_bot_active", "1")
            await _safe_edit(event, owner_id, "✅ سلف‌بات روشن شد.")
            return
        if text == "سلف خاموش":
            db.set_setting(owner_id, "self_bot_active", "0")
            await _safe_edit(event, owner_id, "❌ سلف‌بات خاموش شد.")
            return

        # اگه پلن منقضی شده، فقط دستور وضعیت رو اجرا کن
        if entry.get("paused"):
            if text in ("وضعیت", "راهنما", "help"):
                pass  # اجازه بده ادامه پیدا کنه
            else:
                await _safe_edit(event, owner_id,
                    "⛔ اشتراک شما منقضی شده است.\n"
                    "برای تمدید پلن با ادمین در تماس باشید.\n"
                    "بعد از تمدید، سلف تا ۵ دقیقه دیگر خودکار فعال می‌شود."
                )
                return

        # لیست دستورات تنظیماتی که همیشه فعال هستند
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
            "سکوت", "لغو سکوت", "لیست سکوت",
            "فونت ", "لیست فونت", "فونت متن روشن", "فونت متن خاموش", "بنویس ",
            "بولد ", "ایتالیک ", "مونو ", "اسپویلر ", "کوت ", "خط‌خورده ", "زیرخط ",
            "ذخیره ", "ارسال ذخیره ",
            "ترجمه ", "هوا ", "قیمت دلار", "ارز",
            "وضعیت", "راهنما", "help",
            "حذف بعد ",
            "سیو کانال", "توقف سیو",
            "تنظیم کانال ", "حذف کانال اجباری", "جوین اجباری روشن", "جوین اجباری خاموش",
            "پیام جوین ", "لینک کانال جوین ",
            "پنل", "panel",
        ]

        is_config_command = any(text.startswith(cmd) or text == cmd for cmd in config_commands)

        # اگر دستور تنظیماتی نیست و سلف خاموش است، اجرا نکن
        if not is_config_command and db.get_setting(owner_id, "self_bot_active") != "1":
            return

        await _handle_command(cl, event, text, owner_id, entry)



    # ─── تاس (send_dice) ─────────────────────────────────────────────────────────
    async def send_dice(ev, dice_type, target=None):
        reply_to = ev.reply_to_msg_id
        while True:
            if reply_to:
                msg = await ev.reply(file=InputMediaDice(dice_type))
            else:
                msg = await ev.respond(file=InputMediaDice(dice_type))

            if target is None or (msg.media and msg.media.value == target):
                break

            await asyncio.sleep(0.5)
            try:
                await msg.delete()
            except Exception:
                pass

    @cl.on(events.MessageEdited(outgoing=True, pattern=r"(?i)^(?:تاس|roll) (\d)$"))
    @cl.on(events.NewMessage(outgoing=True, pattern=r"(?i)^(?:تاس|roll) (\d)$"))
    async def dice(event):
        if entry.get("paused"):
            return
        await event.delete()
        target = int(event.pattern_match.group(1))
        await send_dice(event, "🎲", target=target)


# ─── پردازش دستورات ────────────────────────────────────────────────────────────
# ─── دستورهای روشن/خاموش جدید پنل (قفل‌ها، ساعت پرمیوم، حالت‌های متن) ─────────
# اینا فقط یک تنظیم ساده در دیتابیس رو ست/ری‌ست می‌کنن (بدون منطق اجراییِ
# جداگانه)، برای این‌که دکمه‌های پنل واقعاً وضعیت روشن/خاموش رو نگه دارن.
_EXTRA_TOGGLE_COMMANDS = {
    "قفل یوزرنیم روشن": ("lock_username_active", "1"),
    "قفل یوزرنیم خاموش": ("lock_username_active", "0"),
    "قفل ریپلای روشن": ("lock_reply_active", "1"),
    "قفل ریپلای خاموش": ("lock_reply_active", "0"),
    "قفل گیف روشن": ("lock_gif_active", "1"),
    "قفل گیف خاموش": ("lock_gif_active", "0"),
    "قفل عکس روشن": ("lock_photo_active", "1"),
    "قفل عکس خاموش": ("lock_photo_active", "0"),
    "قفل استیکر روشن": ("lock_sticker_active", "1"),
    "قفل استیکر خاموش": ("lock_sticker_active", "0"),
    "قفل فوروارد روشن": ("lock_forward_active", "1"),
    "قفل فوروارد خاموش": ("lock_forward_active", "0"),
    "ساعت پرمیوم روشن": ("clock_premium_active", "1"),
    "ساعت پرمیوم خاموش": ("clock_premium_active", "0"),
    "حالت بولد روشن": ("text_style_bold_active", "1"),
    "حالت بولد خاموش": ("text_style_bold_active", "0"),
    "حالت ایتالیک روشن": ("text_style_italic_active", "1"),
    "حالت ایتالیک خاموش": ("text_style_italic_active", "0"),
    "حالت نقل قول روشن": ("text_style_quote_active", "1"),
    "حالت نقل قول خاموش": ("text_style_quote_active", "0"),
    "حالت زیرخط روشن": ("text_style_underline_active", "1"),
    "حالت زیرخط خاموش": ("text_style_underline_active", "0"),
    "حالت اسپویلر روشن": ("text_style_spoiler_active", "1"),
    "حالت اسپویلر خاموش": ("text_style_spoiler_active", "0"),
    "حالت خط‌خورده روشن": ("text_style_strike_active", "1"),
    "حالت خط‌خورده خاموش": ("text_style_strike_active", "0"),
    "حالت تدریجی روشن": ("text_style_gradual_active", "1"),
    "حالت تدریجی خاموش": ("text_style_gradual_active", "0"),
    "حالت تک‌فاصله روشن": ("text_style_single_space_active", "1"),
    "حالت تک‌فاصله خاموش": ("text_style_single_space_active", "0"),
}


async def _handle_command(cl, event, text, owner_id, entry):
    msg = event.message

    def gs(key, default=None):
        return db.get_setting(owner_id, key, default)

    def ss(key, value):
        db.set_setting(owner_id, key, value)

    async def edit(t):
        await _safe_edit(event, owner_id, t)

    # ─── پنل دکمه‌ای مدیریت سلف ─────────────────────────────────────────────────
    # وقتی کاربر در خودِ چت فقط «پنل» یا «panel» می‌نویسه، پیامش پاک می‌شه و
    # به‌جاش همون پیام اینلاینِ واقعی (via @helper_bot) با دکمه‌های رنگی فعال
    # جایگزینش می‌شه - دقیقاً انگار با نوشتن «پنل» پنل شیشه‌ای باز شده.
    if text in ("پنل", "panel"):
        try:
            await event.delete()
        except Exception:
            pass

        if not config.HELPER_BOT_TOKEN:
            await cl.send_message(event.chat_id, "❗ پنل دکمه‌ای فعال نیست (بات کمکی تنظیم نشده).")
            return

        from helper_bot import get_helper_client
        helper = get_helper_client()
        uname = None
        if helper:
            try:
                me = await helper.get_me()
                uname = me.username
            except Exception:
                uname = None

        if not uname:
            await cl.send_message(event.chat_id, "❗ بات کمکی هنوز آماده نیست، کمی بعد دوباره امتحان کن.")
            return

        try:
            results = await cl.inline_query(uname, "پنل")
            if results:
                await results[0].click(event.chat_id)
            else:
                await cl.send_message(event.chat_id, "❗ نتیجه‌ای از بات کمکی دریافت نشد.")
        except Exception as e:
            await cl.send_message(event.chat_id, f"❗ خطا در باز کردن پنل: {e}")

    # ─── دستورهای روشن/خاموش جدید پنل (قفل‌ها، ساعت پرمیوم، حالت‌های متن) ─────
    elif text in _EXTRA_TOGGLE_COMMANDS:
        key, val = _EXTRA_TOGGLE_COMMANDS[text]
        ss(key, val)
        label = text.rsplit(" ", 1)[0]
        state = "روشن" if val == "1" else "خاموش"
        await edit(f"{label} {state} شد.")

    # ─── ماشین حساب ──────────────────────────────────────────────────────────
    elif text.startswith("محاسبه "):
        expr = text[len("محاسبه "):].strip()
        try:
            import ast, operator as _op
            _ops = {
                ast.Add: _op.add, ast.Sub: _op.sub, ast.Mult: _op.mul,
                ast.Div: _op.truediv, ast.Pow: _op.pow, ast.Mod: _op.mod,
                ast.USub: _op.neg, ast.UAdd: _op.pos,
            }

            def _safe_eval(node):
                if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                    return node.value
                if isinstance(node, ast.BinOp) and type(node.op) in _ops:
                    return _ops[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
                if isinstance(node, ast.UnaryOp) and type(node.op) in _ops:
                    return _ops[type(node.op)](_safe_eval(node.operand))
                raise ValueError("عبارت نامعتبر")

            result = _safe_eval(ast.parse(expr, mode="eval").body)
            await edit(f"نتیجه: {result}")
        except Exception:
            await edit("❗ عبارت ریاضی نامعتبر است.\nفرمت درست: `محاسبه 2+2*3`")

    # ─── دستیار هوش مصنوعی (دیپ‌سیک) ───────────────────────────────────────
    elif text == "دیپ سیک روشن":
        if not getattr(config, "DEEPSEEK_API_KEY", ""):
            await edit("کلید API دیپ‌سیک تنظیم نشده است.")
        else:
            ss("ai_assistant_active", "1")
            await edit(
                "دستیار هوش مصنوعی روشن شد.\n"
                f"وقتی {AI_AWAY_SECONDS // 60} دقیقه پیامی نفرستی، به‌جای تو به پیام‌های پیوی جواب می‌ده."
            )
    elif text == "دیپ سیک خاموش":
        ss("ai_assistant_active", "0")
        await edit("دستیار هوش مصنوعی خاموش شد.")

    elif text.startswith("آموزش هوش مصنوعی "):
        info = text[len("آموزش هوش مصنوعی "):].strip()
        if not info:
            await edit("فرمت: آموزش هوش مصنوعی [متن]")
        else:
            existing = gs("ai_knowledge_base", "")
            merged = f"{existing}\n{info}".strip() if existing else info
            ss("ai_knowledge_base", merged)
            await edit("اطلاعات به دانش هوش مصنوعی اضافه شد.")

    elif text == "نمایش دانش هوش مصنوعی":
        info = gs("ai_knowledge_base", "")
        await edit(info if info else "هنوز چیزی به هوش مصنوعی آموزش نداده‌ای.")

    elif text == "پاک کردن دانش هوش مصنوعی":
        ss("ai_knowledge_base", "")
        await edit("دانش هوش مصنوعی پاک شد.")

    elif text == "تایپینگ روشن":
        ss("typing_action_active", "1")
        await edit("اکشن تایپینگ ۲۴ ساعته روشن شد.")
    elif text == "تایپینگ خاموش":
        ss("typing_action_active", "0")
        await edit("اکشن تایپینگ ۲۴ ساعته خاموش شد.")

    elif text == "گیمینگ روشن":
        ss("gaming_action_active", "1")
        await edit("اکشن گیمینگ ۲۴ ساعته روشن شد.")
    elif text == "گیمینگ خاموش":
        ss("gaming_action_active", "0")
        await edit("اکشن گیمینگ ۲۴ ساعته خاموش شد.")

    elif text == "ویس روشن":
        ss("voice_action_active", "1")
        await edit("اکشن ویس ۲۴ ساعته روشن شد.")
    elif text == "ویس خاموش":
        ss("voice_action_active", "0")
        await edit("اکشن ویس ۲۴ ساعته خاموش شد.")

    elif text == "ارسال ویدیو روشن":
        ss("video_action_active", "1")
        await edit("اکشن ارسال ویدیو ۲۴ ساعته روشن شد.")
    elif text == "ارسال ویدیو خاموش":
        ss("video_action_active", "0")
        await edit("اکشن ارسال ویدیو ۲۴ ساعته خاموش شد.")

    # ─── بلاک / آنبلاک کاربر ────────────────────────────────────────────────
    elif text in ("بلاک کاربر", "انبلاک کاربر"):
        target = await _resolve_target_or_username(cl, event, text.split())
        if not target:
            await edit("روی پیام کاربر ریپلای کن یا آیدی عددی/یوزرنیمش رو بنویس.")
        else:
            from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
            blocked = _get_block_list(owner_id)
            try:
                if text == "بلاک کاربر":
                    await cl(BlockRequest(id=target["id"]))
                    if not any(u["id"] == target["id"] for u in blocked):
                        blocked.append(target)
                        _save_block_list(owner_id, blocked)
                    await edit(f"کاربر {target.get('name') or target['id']} بلاک شد.")
                else:
                    await cl(UnblockRequest(id=target["id"]))
                    blocked = [u for u in blocked if u["id"] != target["id"]]
                    _save_block_list(owner_id, blocked)
                    await edit(f"کاربر {target.get('name') or target['id']} آنبلاک شد.")
            except Exception as e:
                await edit(f"خطا: {e}")

    elif text == "لیست بلاک":
        blocked = _get_block_list(owner_id)
        if not blocked:
            await edit("لیست بلاک خالی است.")
        else:
            lines = [f"لیست بلاک ({len(blocked)} نفر):\n"]
            for u in blocked:
                lines.append(f"- {u.get('name') or u.get('username') or u['id']} — `{u['id']}`")
            await edit("\n".join(lines))

    elif text == "پاکسازی لیست بلاک":
        from telethon.tl.functions.contacts import UnblockRequest
        for u in _get_block_list(owner_id):
            try:
                await cl(UnblockRequest(id=u["id"]))
            except Exception:
                pass
        _save_block_list(owner_id, [])
        await edit("لیست بلاک پاکسازی شد و همه آنبلاک شدند.")

    # ─── ری‌اکت اختصاصی برای یک کاربر خاص ───────────────────────────────────
    elif text.startswith("تنظیم ری‌اکت "):
        emoji = text[len("تنظیم ری‌اکت "):].strip()
        target = await _resolve_target(event, text.split())
        if not emoji or not target:
            await edit("فرمت: روی پیام کاربر ریپلای کن و بنویس «تنظیم ری‌اکت [ایموجی]»")
        else:
            mapping = _get_react_map(owner_id)
            mapping[str(target["id"])] = emoji
            _save_react_map(owner_id, mapping)
            await edit(f"از این به بعد پیام‌های {target.get('name') or target['id']} با {emoji} ری‌اکت می‌شود.")

    elif text == "حذف ری‌اکت":
        target = await _resolve_target(event, text.split())
        if not target:
            await edit("روی پیام کاربر ریپلای کن.")
        else:
            mapping = _get_react_map(owner_id)
            mapping.pop(str(target["id"]), None)
            _save_react_map(owner_id, mapping)
            await edit("ری‌اکت اختصاصی این کاربر حذف شد.")

    # ─── ترک همگانی گروه/کانال ──────────────────────────────────────────────
    elif text == "ترک همگانی گروه":
        from telethon.tl.functions.channels import LeaveChannelRequest
        await edit("در حال ترک همه گروه‌ها...")
        count = 0
        async for dialog in cl.iter_dialogs():
            if dialog.is_group:
                try:
                    await cl(LeaveChannelRequest(dialog.entity))
                    count += 1
                except Exception:
                    pass
        await edit(f"ترک همگانی گروه انجام شد. تعداد: {count}")

    elif text == "ترک همگانی کانال":
        from telethon.tl.functions.channels import LeaveChannelRequest
        await edit("در حال ترک همه کانال‌ها...")
        count = 0
        async for dialog in cl.iter_dialogs():
            if dialog.is_channel and not dialog.is_group:
                try:
                    await cl(LeaveChannelRequest(dialog.entity))
                    count += 1
                except Exception:
                    pass
        await edit(f"ترک همگانی کانال انجام شد. تعداد: {count}")

    # ─── تبدیل ویدیوی ریپلای‌شده به گیف ──────────────────────────────────────
    elif text == "تبدیل به گیف":
        if not event.is_reply:
            await edit("لطفا روی یک ویدیو ریپلای کن.")
        else:
            reply = await event.get_reply_message()
            if not reply.video and not reply.document:
                await edit("پیام ریپلای‌شده ویدیو نیست.")
            else:
                await edit("در حال تبدیل...")
                path = await cl.download_media(reply)
                gif_path = os.path.splitext(path)[0] + ".gif"
                try:
                    os.rename(path, gif_path)
                    await cl.send_file(event.chat_id, gif_path)
                    await event.delete()
                except Exception as e:
                    await edit(f"خطا در تبدیل به گیف: {e}")
                finally:
                    try:
                        os.remove(gif_path)
                    except Exception:
                        pass

    # ─── ترجمه‌ی متن ریپلای‌شده ──────────────────────────────────────────────
    elif text == "ترجمه متن":
        if not event.is_reply:
            await edit("لطفا روی یک پیام متنی ریپلای کن.")
        else:
            reply = await event.get_reply_message()
            raw = reply.raw_text
            if not raw:
                await edit("پیام ریپلای‌شده متن ندارد.")
            else:
                result = await _translate(raw)
                await edit(f"ترجمه:\n{result}")

    # ─── دشمن ────────────────────────────────────────────────────────────────
    elif text.startswith("تنظیم دشمن"):
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
        ss("secretary_active", "1"); await edit("🤖 منشی خودکار روشن شد.\n💡 هر کاربر فقط هر 24 ساعت یک بار پاسخ می‌گیرد.")
    elif text == "منشی خاموش":
        ss("secretary_active", "0"); await edit("🤖 منشی خودکار خاموش شد.")
    elif text.startswith("پیام منشی "):
        ss("secretary_message", text[len("پیام منشی "):].strip())
        await edit("✅ پیام منشی تنظیم شد.")

    # ─── ضد حذف ──────────────────────────────────────────────────────────────
    elif text == "ضد حذف روشن":
        ss("anti_delete_active", "1"); await edit("🛡️ ضد حذف روشن شد.")
    elif text == "ضد حذف خاموش":
        ss("anti_delete_active", "0"); await edit("🛡️ ضد حذف خاموش شد.")

    # ─── ضد لینک ─────────────────────────────────────────────────────────────
    elif text == "ضد لینک روشن":
        ss("anti_link_active", "1"); await edit("🔗 ضد لینک روشن شد.")
    elif text == "ضد لینک خاموش":
        ss("anti_link_active", "0"); await edit("🔗 ضد لینک خاموش شد.")

    # ─── قفل پیوی ────────────────────────────────────────────────────────────
    elif text == "قفل پیوی روشن":
        ss("private_lock_active", "1"); await edit("🔒 قفل پیوی روشن شد.")
    elif text == "قفل پیوی خاموش":
        ss("private_lock_active", "0"); await edit("🔓 قفل پیوی خاموش شد.")

    # ─── سین خودکار ──────────────────────────────────────────────────────────
    elif text == "سین خودکار روشن":
        ss("auto_seen_active", "1"); await edit("👁️ سین خودکار روشن شد.")
    elif text == "سین خودکار خاموش":
        ss("auto_seen_active", "0"); await edit("👁️ سین خودکار خاموش شد.")

    # ─── ری‌اکشن ─────────────────────────────────────────────────────────────
    elif text == "ری‌اکشن روشن":
        ss("auto_reaction_active", "1"); await edit("❤️ ری‌اکشن خودکار روشن شد.")
    elif text == "ری‌اکشن خاموش":
        ss("auto_reaction_active", "0"); await edit("❤️ ری‌اکشن خودکار خاموش شد.")
    elif text.startswith("ری‌اکشن "):
        emoji = text[len("ری‌اکشن "):].strip()
        ss("auto_reaction_emoji", emoji); await edit(f"✅ ری‌اکشن پیش‌فرض: {emoji}")

    # ─── ذخیره مدیا ──────────────────────────────────────────────────────────
    elif text == "ذخیره مدیا روشن":
        os.makedirs(f"saved_media/{owner_id}", exist_ok=True)
        ss("auto_save_media", "1"); await edit("💾 ذخیره خودکار مدیا روشن شد.")
    elif text == "ذخیره مدیا خاموش":
        ss("auto_save_media", "0"); await edit("💾 ذخیره خودکار مدیا خاموش شد.")

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
            asyncio.ensure_future(_save_channel_media(cl, channel_input, None, owner_id))
        else:
            limit = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else 100
            await edit(f"⏳ در حال پردازش کانال، تا {limit} مدیا ذخیره می‌شود...")
            asyncio.ensure_future(_save_channel_media(cl, channel_input, limit, owner_id))

    elif text == "توقف سیو":
        ss("channel_save_active", "0"); await edit("🛑 سیو کانال متوقف شد.")

    # ─── سایلنت ──────────────────────────────────────────────────────────────
    elif text == "سایلنت چت روشن":
        chat = await event.get_chat()
        db.add_silent_chat(owner_id, chat.id); await edit("🔇 این چت سایلنت شد.")
    elif text == "سایلنت چت خاموش":
        chat = await event.get_chat()
        db.remove_silent_chat(owner_id, chat.id); await edit("🔔 سایلنت این چت برداشته شد.")
    elif text.startswith("سایلنت کاربر "):
        uid = int(text.split()[-1])
        db.add_silent_user(owner_id, uid); await edit(f"🔇 کاربر {uid} سایلنت شد.")
    elif text.startswith("لغو سایلنت کاربر "):
        uid = int(text.split()[-1])
        db.remove_silent_user(owner_id, uid); await edit(f"🔔 سایلنت کاربر {uid} برداشته شد.")

    # ─── سکوت (حذف خودکار دوطرفه‌ی پیام‌های یک کاربر در پیوی) ─────────────────
    elif text.startswith("سکوت"):
        parts = text.split()
        target = await _resolve_target_or_username(cl, event, parts)
        if target:
            added = _add_silence_user(owner_id, target["id"], target.get("username"), target.get("name"))
            if added:
                await edit(f"🔇 سکوت برای {target.get('name') or target['id']} فعال شد؛ پیام‌های پیوی این کاربر از این به بعد دوطرفه پاک می‌شود.")
            else:
                await edit("❗ این کاربر از قبل توی لیست سکوت بود.")
        else:
            await edit("❗ روی پیام کاربر ریپلای کن یا آیدی عددی/یوزرنیمش رو بنویس. مثال: سکوت 123456789")

    elif text.startswith("لغو سکوت"):
        parts = text.split()
        target = await _resolve_target_or_username(cl, event, parts)
        if target:
            removed = _remove_silence_user(owner_id, target["id"])
            await edit("🔔 سکوت این کاربر برداشته شد." if removed else "❗ این کاربر توی لیست سکوت نبود.")
        else:
            await edit("❗ روی پیام کاربر ریپلای کن یا آیدی عددی/یوزرنیمش رو بنویس. مثال: لغو سکوت 123456789")

    elif text == "لیست سکوت":
        users = _get_silence_users(owner_id)
        if not users:
            await edit("📋 لیست سکوت خالی است.")
        else:
            lines = [f"🔇 لیست سکوت ({len(users)} نفر):\n"]
            for u in users:
                lines.append(f"• {u.get('name') or u.get('username') or u['id']} — `{u['id']}`")
            await edit("\n".join(lines))

    # ─── پاسخ دشمن ───────────────────────────────────────────────────────────
    elif text == "پاسخ دشمن روشن":
        ss("enemy_reply_active", "1"); await edit("⚔️ پاسخ خودکار به دشمن روشن شد.")
    elif text == "پاسخ دشمن خاموش":
        ss("enemy_reply_active", "0"); await edit("⚔️ پاسخ خودکار به دشمن خاموش شد.")

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
        # «بنویس [متن]» — متن رو با فونت فعلی برمی‌گردونه
        raw = text[len("بنویس "):].strip()
        if not raw:
            await edit("❗ فرمت: بنویس [متن]")
        else:
            font_id = gs("selected_font", "0")
            fn = FONTS.get(font_id, FONTS["0"])
            styled = fn(raw)
            await edit(styled)

    # ─── قالب‌بندی تلگرام (entities) — کار با فارسی هم دارد ────────────────────
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
                # fallback برای نسخه‌های قدیمی‌تر telethon
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
            digits = CLOCK_FONTS[font_id]
            sample = _apply_clock_font(owner_id, "12:34")
            await edit(f"⏰ فونت ساعت {font_id} انتخاب شد:\n`{sample}`")
        else:
            await edit("❗ شماره فونت ساعت باید بین ۰ تا ۹ باشد.")
    elif text == "لیست فونت ساعت":
        lines = ["⏰ **فونت‌های ساعت موجود:**\n"]
        for k, digits in CLOCK_FONTS.items():
            sample = "".join(digits[int(ch)] for ch in "1234567890")
            lines.append(f"`فونت ساعت {k}` — `{sample}`")
        lines.append("\n💡 برای انتخاب: `فونت ساعت [شماره]`")
        await edit("\n".join(lines))

    # ─── فونت ────────────────────────────────────────────────────────────────
    elif text.startswith("فونت "):
        parts = text.split()
        # "فونت 4" یا "فونت amel 4"
        font_id = parts[-1]
        preview_words = parts[1:-1]  # کلمات بین "فونت" و شماره
        if font_id in FONTS:
            ss("selected_font", font_id)
            fn = FONTS[font_id]
            if preview_words:
                preview = fn(" ".join(preview_words))
                await edit(f"✅ فونت {font_id} انتخاب شد:\n`{preview}`")
            else:
                sample = fn("Hello World")
                await edit(f"✅ فونت {font_id} انتخاب شد.\nنمونه: `{sample}`")
        else:
            await edit("❗ شماره فونت باید بین ۰ تا ۸ باشد.")

    elif text == "لیست فونت":
        lines = ["🔤 **فونت‌های موجود:**\n"]
        for k in FONTS:
            fn = FONTS[k]
            sample = fn("Hello World")
            lines.append(f"`فونت {k}` — `{sample}`")
        lines.append("\n💡 برای انتخاب: `فونت [شماره]`")
        await edit("\n".join(lines))

    # ─── ساعت نام/بیو ─────────────────────────────────────────────────────────
    elif text == "ساعت نام روشن":
        ss("clock_name_active", "1"); await edit("⏰ ساعت نام روشن شد.")
    elif text == "ساعت نام خاموش":
        ss("clock_name_active", "0"); await edit("⏰ ساعت نام خاموش شد.")
    elif text == "ساعت بیو روشن":
        ss("clock_bio_active", "1"); await edit("⏰ ساعت بیو روشن شد.")
    elif text == "ساعت بیو خاموش":
        ss("clock_bio_active", "0"); await edit("⏰ ساعت بیو خاموش شد.")

    # ─── اسپم ────────────────────────────────────────────────────────────────
    elif text.startswith("اسپم "):
        parts = text.split(maxsplit=2)
        if len(parts) >= 3 and parts[1].isdigit():
            count = int(parts[1])
            spam_text = parts[2]
            chat = await event.get_chat()
            ss("spam_active", "1")
            await msg.delete()
            asyncio.ensure_future(_do_spam(cl, owner_id, chat.id, spam_text, count))
        # اگه فرمت درست نیست → هیچ کاری نکن (بی‌صدا)
    elif text == "توقف اسپم":
        ss("spam_active", "0"); await edit("🛑 اسپم متوقف شد.")

    # ─── حذف خودکار ──────────────────────────────────────────────────────────
    elif text.startswith("حذف بعد "):
        parts = text.split()
        if len(parts) >= 3 and parts[2].isdigit():
            secs = int(parts[2])
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
            slot = int(parts[1])
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
            slot = int(parts[2])
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
        sub = sub.replace("‌", " ").replace("‏", "")  # حذف نیم‌فاصله/کاراکترهای نامرئی
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
            target = None  # بدون نام ارز خاص → نمایش لیست ارزهای مهم
        await edit(await _get_currency_text(target))

    # ─── جوین اجباری ─────────────────────────────────────────────────────────
    elif text.startswith("تنظیم کانال "):
        channel_raw = text[len("تنظیم کانال "):].strip()
        if not channel_raw:
            await edit("❗ فرمت: تنظیم کانال [آیدی یا @یوزرنیم]")
        else:
            # نرمال‌سازی: آیدی عددی یا @username
            channel_input = channel_raw
            try:
                entity = await cl.get_entity(
                    int(channel_input.lstrip("-")) * (-1 if channel_input.startswith("-") else 1)
                    if channel_input.lstrip("-").isdigit() else channel_input
                )
                # ذخیره آیدی عددی برای دقت بیشتر
                real_id = str(entity.id)
                title = getattr(entity, "title", channel_input)
                ss("force_join_channel", real_id)
                ss("force_join_active", "1")
                await edit(
                    f"✅ کانال جوین اجباری تنظیم شد:\n"
                    f"📢 {title} (ID: {real_id})\n\n"
                    f"💡 دستورات:\n"
                    f"> `جوین اجباری روشن` / `جوین اجباری خاموش`\n"
                    f"> `پیام جوین [متن]` — تغییر پیام هشدار"
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
            # اطمینان از فرمت لینک
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
        lines.append(f"✏️ فونت متن خودکار: {'✅ روشن' if gs('text_font_auto','0')=='1' else '❌ خاموش'}")
        lines.append(f"⏰ فونت ساعت: {gs('selected_clock_font', '0')}")
        fj_ch = gs("force_join_channel", "")
        if fj_ch:
            lines.append(f"📢 کانال جوین اجباری: {fj_ch}")
        lines.append(f"👥 دشمن: {len(db.get_enemies(owner_id))} نفر")
        lines.append(f"💚 دوست: {len(db.get_friends(owner_id))} نفر")
        await edit("\n".join(lines))

    # ─── راهنما ───────────────────────────────────────────────────────────────
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

    # ─── پیام عادی (دستور نیست) — اعمال فونت اگه حالت خودکار روشنه ─────────────
    else:
        font_id = gs("selected_font", "0")
        auto_active = gs("text_font_auto", "0") == "1"
        # فونت خودکار: فقط وقتی "فونت متن روشن" باشه، همه پیام‌ها ادیت می‌شن
        if auto_active and font_id != "0" and text:
            fn = FONTS.get(font_id, FONTS["0"])
            styled = fn(text)
            if styled != text:
                try:
                    await event.edit(styled)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 1)
                except Exception:
                    pass

        # ─── حالت متن (سطح ۲ پنل): اعمال خودکار سبک‌های نوشتاری روی پیام ────
        style_on = {
            "quote": gs("text_style_quote_active", "0") == "1",
            "underline": gs("text_style_underline_active", "0") == "1",
            "spoiler": gs("text_style_spoiler_active", "0") == "1",
            "bold": gs("text_style_bold_active", "0") == "1",
            "italic": gs("text_style_italic_active", "0") == "1",
            "strike": gs("text_style_strike_active", "0") == "1",
            "single_space": gs("text_style_single_space_active", "0") == "1",
            "gradual": gs("text_style_gradual_active", "0") == "1",
        }
        if text and any(style_on.values()):
            from telethon.tl.types import (
                MessageEntityBold, MessageEntityItalic, MessageEntityUnderline,
                MessageEntityStrike, MessageEntitySpoiler, MessageEntityBlockquote,
            )

            body = " ".join(list(text.replace(" ", ""))) if style_on["single_space"] else text

            def _entities_for(length):
                ents = []
                if style_on["bold"]:
                    ents.append(MessageEntityBold(0, length))
                if style_on["italic"]:
                    ents.append(MessageEntityItalic(0, length))
                if style_on["underline"]:
                    ents.append(MessageEntityUnderline(0, length))
                if style_on["strike"]:
                    ents.append(MessageEntityStrike(0, length))
                if style_on["spoiler"]:
                    ents.append(MessageEntitySpoiler(0, length))
                if style_on["quote"]:
                    try:
                        ents.append(MessageEntityBlockquote(0, length, collapsed=False))
                    except Exception:
                        pass
                return ents

            try:
                if style_on["gradual"]:
                    # افکت تایپ تدریجی: پیام رو در چند مرحله کامل نشون می‌ده
                    steps = 5
                    n = len(body)
                    for i in range(1, steps + 1):
                        cut = max(1, (n * i) // steps)
                        partial = body[:cut]
                        try:
                            await event.edit(partial, formatting_entities=_entities_for(len(partial)) or None)
                        except FloodWaitError as e:
                            await asyncio.sleep(e.seconds + 1)
                        except Exception:
                            break
                        if cut < n:
                            await asyncio.sleep(0.35)
                else:
                    entities = _entities_for(len(body))
                    if body != text or entities:
                        await event.edit(body, formatting_entities=entities or None)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception:
                pass


# ─── توابع کمکی ────────────────────────────────────────────────────────────────
async def _safe_edit(event, owner_id, text):
    try:
        fn = FONTS.get(db.get_setting(owner_id, "selected_font", "0"), FONTS["0"])
        await event.edit(fn(text))
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds + 1)
    except Exception:
        pass


async def _resolve_target(event, parts):
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
            return {"id": int(p), "username": None, "name": p}
    return None


async def _resolve_target_or_username(cl, event, parts):
    """
    مثل _resolve_target ولی علاوه بر ریپلای و آیدی عددی، یوزرنیم (@user یا user) را
    هم با کوئری گرفتن از تلگرام به آیدی عددی تبدیل می‌کند. برای دستور «سکوت» استفاده می‌شود.
    """
    target = await _resolve_target(event, parts)
    if target:
        return target
    for p in parts[1:]:
        candidate = p.lstrip("@")
        if not candidate:
            continue
        try:
            entity = await cl.get_entity(candidate)
            return {
                "id": entity.id,
                "username": getattr(entity, "username", None),
                "name": getattr(entity, "first_name", None) or candidate,
            }
        except Exception:
            continue
    return None


# ─── سکوت: حذف خودکار و دوطرفه‌ی پیام‌های یک کاربر خاص در پیوی ────────────────
_SILENCE_KEY = "silence_users"


def _get_silence_users(owner_id: int) -> list:
    raw = db.get_setting(owner_id, _SILENCE_KEY, "")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _save_silence_users(owner_id: int, users: list):
    db.set_setting(owner_id, _SILENCE_KEY, json.dumps(users))


def _add_silence_user(owner_id: int, user_id: int, username=None, name=None):
    users = _get_silence_users(owner_id)
    if any(u["id"] == user_id for u in users):
        return False
    users.append({"id": user_id, "username": username, "name": name})
    _save_silence_users(owner_id, users)
    return True


def _remove_silence_user(owner_id: int, user_id: int) -> bool:
    users = _get_silence_users(owner_id)
    new_users = [u for u in users if u["id"] != user_id]
    if len(new_users) == len(users):
        return False
    _save_silence_users(owner_id, new_users)
    return True


def _is_silence_user(owner_id: int, user_id: int) -> bool:
    return any(u["id"] == user_id for u in _get_silence_users(owner_id))


# ─── بلاک: لیست کاربرانی که با «بلاک کاربر» بلاک شدن ──────────────────────────
_BLOCK_KEY = "blocked_users"


def _get_block_list(owner_id: int) -> list:
    raw = db.get_setting(owner_id, _BLOCK_KEY, "")
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


def _save_block_list(owner_id: int, users: list):
    db.set_setting(owner_id, _BLOCK_KEY, json.dumps(users))


# ─── ری‌اکت اختصاصی: یک ایموجی ثابت که فقط برای پیام‌های یک کاربر خاص زده می‌شه ─
_REACT_MAP_KEY = "user_react_map"


def _get_react_map(owner_id: int) -> dict:
    raw = db.get_setting(owner_id, _REACT_MAP_KEY, "")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _save_react_map(owner_id: int, mapping: dict):
    db.set_setting(owner_id, _REACT_MAP_KEY, json.dumps(mapping))


async def _do_spam(cl, owner_id, chat_id, text, count):
    # delay پیش‌فرض ۱ ثانیه (دو برابر سرعت نسبت به قبل که ۲ بود)
    delay = float(db.get_setting(owner_id, "spam_delay", "1"))
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
            await asyncio.sleep(e.seconds + 1)
        except Exception:
            break
    db.set_setting(owner_id, "spam_active", "0")


async def _save_channel_media(cl, channel_input, limit, owner_id):
    db.set_setting(owner_id, "channel_save_active", "1")
    media_dir = f"saved_media/{owner_id}"
    os.makedirs(media_dir, exist_ok=True)
    try:
        me = await cl.get_me()

        # ─── حالت ۱: لینک یک پست خاص ────────────────────────────────────
        post_match = _POST_LINK_RE.match(channel_input)
        if post_match:
            channel_username, post_id = post_match.group(1), int(post_match.group(2))
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

        # ─── حالت ۲: کانال + تعداد ──────────────────────────────────────
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
                    await asyncio.sleep(e.seconds + 2)
                except Exception:
                    skipped += 1
            else:
                skipped += 1

        db.set_setting(owner_id, "channel_save_active", "0")
        await cl.send_message(me.id,
            f"✅ سیو کانال تموم شد\n💾 ذخیره شد: {saved}\n⏭ رد شد: {skipped}")
    except Exception as e:
        db.set_setting(owner_id, "channel_save_active", "0")
        try:
            me = await cl.get_me()
            await cl.send_message(me.id, f"❌ خطا در سیو کانال: {e}")
        except Exception:
            pass


async def _ask_deepseek(knowledge_base: str, question: str) -> str:
    """
    یک سوال از طرف کسی که به سلف پیام داده رو به مدل دیپ‌سیک می‌ده، به‌همراه
    اطلاعاتی که خودِ کاربر قبلاً به هوش مصنوعی آموزش داده (مثل لیست قیمت‌ها)،
    و پاسخ متنی رو برمی‌گردونه. اگه کلید API تنظیم نشده باشه یا خطایی رخ بده،
    None برمی‌گردونه (یعنی پاسخی ارسال نشه).
    """
    api_key = getattr(config, "DEEPSEEK_API_KEY", "")
    if not api_key:
        return None
    try:
        import urllib.request
        system_prompt = (
            "تو دستیار پاسخ‌گویی خودکار یک اکانت تلگرام هستی. صاحب اکانت الان "
            "در دسترس نیست. فقط بر اساس اطلاعاتی که صاحب اکانت زیر آورده شده "
            "به پیام‌های افراد پاسخ بده. اگه سوال ربطی به این اطلاعات نداشت یا "
            "اطلاعات کافی نبود، مختصر و محترمانه بگو که صاحب اکانت به‌زودی خودش "
            "جواب می‌ده. پاسخ باید کوتاه، مستقیم و طبیعی باشه، بدون ایموجی.\n\n"
            f"اطلاعاتی که صاحب اکانت داده:\n{knowledge_base or '(چیزی ثبت نشده)'}"
        )
        payload = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            "max_tokens": 300,
            "temperature": 0.4,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        def _do_request():
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())

        data = await asyncio.get_event_loop().run_in_executor(None, _do_request)
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"خطا در ارتباط با دیپ‌سیک: {e}")
        return None


async def _translate(text):
    try:
        import urllib.request, urllib.parse, json
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=fa&dt=t&q={urllib.parse.quote(text)}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return data[0][0][0]
    except Exception:
        return "⚠️ خطا در ترجمه"


async def _get_weather(city):
    try:
        import urllib.request, urllib.parse, json
        api_key = config.WEATHER_API_KEY
        if not api_key:
            return "⚠️ کلید API هواشناسی تنظیم نشده."
        url = f"https://api.openweathermap.org/data/2.5/weather?q={urllib.parse.quote(city)}&appid={api_key}&units=metric&lang=fa"
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return (f"🌤️ هوای {city}:\n"
                    f"وضعیت: {data['weather'][0]['description']}\n"
                    f"دما: {data['main']['temp']}°C\n"
                    f"رطوبت: {data['main']['humidity']}%")
    except Exception:
        return "⚠️ خطا در دریافت اطلاعات هوا"


_CURRENCY_LABELS = {
    "usd":  "💵 دلار آمریکا",
    "eur":  "💶 یورو",
    "gbp":  "💷 پوند انگلیس",
    "usdt": "💎 تتر (USDT)",
    "btc":  "₿ بیت‌کوین",
    "eth":  "⟠ اتریوم",
}
_CURRENCY_DEFAULT_LIST = ("usd", "eur", "gbp", "usdt", "btc", "eth")

_currency_cache = {"data": {}, "ts": 0.0}
_CURRENCY_CACHE_TTL = 60  # ثانیه

async def _fetch_currency_prices() -> dict:
    """
    دریافت قیمت ارزها به تومان:
    - دلار آزاد → Nobitex (usdt-rls) که برابر نرخ آزاد است
    - یورو/پوند → open.er-api.com (رایگان) × نرخ دلار
    - بیت‌کوین/اتریوم → CoinGecko × نرخ دلار
    - کش ۶۰ ثانیه‌ای
    """
    now = time.time()
    if now - _currency_cache["ts"] < _CURRENCY_CACHE_TTL and _currency_cache["data"]:
        return _currency_cache["data"]

    loop = asyncio.get_event_loop()
    result = {}

    # ─── مرحله ۱: نرخ دلار آزاد از Nobitex ──────────────────────────────────
    usd_toman = 0
    for src, pair in [("usdt", "usdt-rls"), ("btc", "btc-rls"), ("eth", "eth-rls")]:
        try:
            nb = await loop.run_in_executor(
                None, lambda s=src: _fetch_json_sync(
                    "https://api.nobitex.ir/market/stats",
                    json_body={"srcCurrency": s, "dstCurrency": "rls"}, timeout=8
                )
            )
            rial = float(nb["stats"][f"{s}-rls"]["latest"])
            val = int(rial / 10)
            result[src] = val
            if src == "usdt":
                usd_toman = val
                result["usd"] = val
        except Exception as e:
            print(f"⚠️ Nobitex {src}: {e}")

    # ─── مرحله ۲: نرخ یورو/پوند از exchangerate-api ─────────────────────────
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
            print(f"⚠️ exchangerate EUR/GBP: {e}")
            result.setdefault("eur", int(usd_toman * 1.08))
            result.setdefault("gbp", int(usd_toman * 1.27))

    # ─── مرحله ۳: BTC/ETH دقیق‌تر از CoinGecko ──────────────────────────────
    if usd_toman and ("btc" not in result or "eth" not in result):
        try:
            cg = await loop.run_in_executor(
                None, lambda: _fetch_json_sync(
                    "https://api.coingecko.com/api/v3/simple/price"
                    "?ids=bitcoin,ethereum&vs_currencies=usd", timeout=10
                )
            )
            btc_usd = cg.get("bitcoin", {}).get("usd", 0)
            eth_usd = cg.get("ethereum", {}).get("usd", 0)
            if btc_usd:
                result["btc"] = int(btc_usd * usd_toman)
            if eth_usd:
                result["eth"] = int(eth_usd * usd_toman)
        except Exception as e:
            print(f"⚠️ CoinGecko: {e}")

    if not result:
        return _currency_cache.get("data") or {}

    _currency_cache["data"] = result
    _currency_cache["ts"] = now
    return result


def _fetch_json_sync(url, json_body=None, timeout=6, retries=3):
    """درخواست HTTP همگام (در executor اجرا می‌شود تا event loop بلاک نشود)"""
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
                _time.sleep(2 ** attempt)  # 1s, 2s
    raise last_err


async def _get_currency_text(target: str = None) -> str:
    """
    target=None → نمایش لیست ارزهای مهم (دلار، تتر، یورو، پوند)
    target='usd'/'eur'/'gbp'/'usdt'/'btc' → فقط همان یک ارز
    """
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


def _help_text():
    # هر دستور در یک بلوک quote + mono جداگانه
    sections = [
        ("🔹 اصلی", [
            "سلف روشن",
            "سلف خاموش",
            "وضعیت",
            "راهنما",
        ]),
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
            "ضد حذف روشن",
            "ضد حذف خاموش",
            "ضد لینک روشن",
            "ضد لینک خاموش",
            "قفل پیوی روشن",
            "قفل پیوی خاموش",
            "پاسخ دشمن روشن",
            "پاسخ دشمن خاموش",
            "سکوت [آیدی یا یوزرنیم]  ← ریپلای یا آیدی/یوزرنیم",
            "لغو سکوت [آیدی یا یوزرنیم]",
            "لیست سکوت",
            "💡 پیام‌های پیوی کاربر سکوت‌شده به‌صورت خودکار و دوطرفه پاک می‌شود",
        ]),
        ("🔹 جوین اجباری", [
            "تنظیم کانال [آیدی یا @یوزرنیم]  ← تنظیم کانال",
            "لینک کانال جوین [لینک]  ← لینک دکمه رنگی جوین",
            "پیام جوین [متن]  ← تغییر متن پیام هشدار",
            "جوین اجباری روشن / خاموش",
            "حذف کانال اجباری",
            "💡 پیام عضو‌نشده حذف + هشدار با دکمه رنگی میفرسته",
        ]),
        ("🔹 اتوماسیون", [
            "سین خودکار روشن",
            "سین خودکار خاموش",
            "ری‌اکشن روشن",
            "ری‌اکشن خاموش",
            "ری‌اکشن [ایموجی]  ← تغییر ایموجی",
            "ذخیره مدیا روشن",
            "ذخیره مدیا خاموش",
            "ساعت نام روشن",
            "ساعت نام خاموش",
            "ساعت بیو روشن",
            "ساعت بیو خاموش",
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
            "💡 تعداد نامحدود — فرمت باید دقیق باشه",
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
        ("🔹 قالب‌بندی (فارسی/انگلیسی)", [
            "بولد [متن]  ← متن ضخیم",
            "ایتالیک [متن]  ← متن کج",
            "مونو [متن]  ← متن کد",
            "اسپویلر [متن]  ← متن مخفی",
            "کوت [متن]  ← نقل قول",
            "خط‌خورده [متن]  ← متن خط‌خورده",
            "زیرخط [متن]  ← متن زیرخط",
            "💡 روی متن فارسی هم کار می‌کند",
        ]),
        ("🔹 فونت", [
            "فونت [0-8]  ← انتخاب فونت",
            "فونت [متن] [0-8]  ← نوشتن یه کلمه با فونت",
            "لیست فونت  ← نمایش همه فونت‌ها",
            "──────────────────",
            "فونت متن روشن  ← هر پیامی که بنویسی ادیت می‌شه",
            "فونت متن خاموش  ← خاموش کردن حالت خودکار",
            "بنویس [متن]  ← نوشتن با فونت فعلی (بدون روشن کردن خودکار)",
            "──────────────────",
            "فونت ساعت [0-9]  ← فونت ساعت نام/بیو",
            "لیست فونت ساعت  ← نمایش فونت‌های ساعت",
        ]),
        ("🎲 تاس", [
            "تاس [1-6]  ← ارسال تاس با عدد دلخواه 🎲",
            "roll [1-6]  ← همان دستور به انگلیسی",
        ]),
        ("💡 نکات", [
            "در گروه‌ها فقط وقتی تگ شوید پاسخ می‌دهد",
            "پاسخ به دوستان هر ۱ ساعت یک بار",
        ]),
    ]
    parts = ["📖 **راهنمای NexoSelf**\n"]
    for title, cmds in sections:
        parts.append(f"\n{title}")
        for cmd in cmds:
            parts.append(f"> `{cmd}`")
    return "\n".join(parts)


# ─── پنل دکمه‌ای مدیریت سلف — دسته‌بندی‌شده (برای بات کمکی / helper_bot.py) ─────
# هر دسته یک "title" داره، یک لیست "toggles" (سوییچ‌های روشن/خاموش، رنگشون از
# طریق style واقعی دکمه مشخص می‌شه نه ایموجی)، یک لیست "actions" (دکمه‌های
# ساده‌ی اجرایی یا فقط اطلاع‌رسانی) و به‌صورت اختیاری:
#   "children": [(برچسب دکمه, کلید زیرمنو), ...] → دکمه‌هایی که به یک دسته‌ی
#                دیگه (زیرمنو) می‌رن، مثلاً «فونت ساعت» یا «دوست»/«دشمن».
#   "parent": کلید دسته‌ی والد → دکمه‌ی «بازگشت» این دسته به‌جای منوی اصلی،
#             به همون دسته‌ی والد برمی‌گرده.
# actions: (برچسب دکمه، متن دستور، ...) — اگه متن دستور با "INFO::" شروع بشه،
# یعنی این دکمه فقط یک پیام کوتاه (toast) نشون می‌ده و هیچ دستوری روی سلف
# اجرا نمی‌شه (برای مواردی مثل ماشین‌حساب/ترجمه که نیاز به ورودی متنی دارن).
PANEL_CATEGORIES = {
    # ─── سطح ۱: منوی اصلی ───────────────────────────────────────────────────
    "clock": {
        "title": "ساعت",
        "toggles": [
            ("clock_name_active", "ساعت نام", "ساعت نام روشن", "ساعت نام خاموش"),
            ("clock_bio_active", "ساعت بیو", "ساعت بیو روشن", "ساعت بیو خاموش"),
            ("clock_premium_active", "ساعت پرمیوم", "ساعت پرمیوم روشن", "ساعت پرمیوم خاموش"),
        ],
        "actions": [],
        "children": [("فونت ساعت", "clock_font")],
    },
    "text_mode": {
        "title": "حالت متن",
        "toggles": [
            ("text_style_quote_active", "نقل قول", "حالت نقل قول روشن", "حالت نقل قول خاموش"),
            ("text_style_underline_active", "زیر خط", "حالت زیرخط روشن", "حالت زیرخط خاموش"),
            ("text_style_spoiler_active", "اسپویلر", "حالت اسپویلر روشن", "حالت اسپویلر خاموش"),
            ("text_style_gradual_active", "تدریجی", "حالت تدریجی روشن", "حالت تدریجی خاموش"),
            ("text_style_bold_active", "بولد", "حالت بولد روشن", "حالت بولد خاموش"),
            ("text_style_italic_active", "ایتالیک", "حالت ایتالیک روشن", "حالت ایتالیک خاموش"),
            ("text_style_strike_active", "خط خورده", "حالت خط‌خورده روشن", "حالت خط‌خورده خاموش"),
            ("text_style_single_space_active", "تک فاصله", "حالت تک‌فاصله روشن", "حالت تک‌فاصله خاموش"),
        ],
        "actions": [],
    },
    "locks": {
        "title": "قفل ها",
        "toggles": [
            ("lock_username_active", "قفل یوزرنیم", "قفل یوزرنیم روشن", "قفل یوزرنیم خاموش"),
            ("lock_reply_active", "قفل ریپلای", "قفل ریپلای روشن", "قفل ریپلای خاموش"),
            ("lock_gif_active", "قفل گیف", "قفل گیف روشن", "قفل گیف خاموش"),
            ("private_lock_active", "قفل پیوی", "قفل پیوی روشن", "قفل پیوی خاموش"),
            ("anti_link_active", "قفل لینک", "ضد لینک روشن", "ضد لینک خاموش"),
            ("lock_photo_active", "قفل عکس", "قفل عکس روشن", "قفل عکس خاموش"),
            ("lock_sticker_active", "قفل استیکر", "قفل استیکر روشن", "قفل استیکر خاموش"),
            ("lock_forward_active", "قفل فوروارد", "قفل فوروارد روشن", "قفل فوروارد خاموش"),
            ("anti_delete_active", "قفل ضد حذف", "ضد حذف روشن", "ضد حذف خاموش"),
        ],
        "actions": [],
    },
    "secretary": {
        "title": "منشی",
        "toggles": [
            ("secretary_active", "منشی", "منشی روشن", "منشی خاموش"),
        ],
        "actions": [
            ("نمایش متن دستورات منشی", "INFO::دستورات منشی:\nمنشی روشن / منشی خاموش\nپیام منشی [متن دلخواه]"),
        ],
    },
    "forced_join": {
        "title": "عضویت اجباری",
        "toggles": [
            ("force_join_active", "عضویت اجباری", "جوین اجباری روشن", "جوین اجباری خاموش"),
        ],
        "actions": [
            ("نمایش متن دستورات", "INFO::دستورات عضویت اجباری:\nتنظیم کانال [آیدی/لینک]\nحذف کانال اجباری\nجوین اجباری روشن / جوین اجباری خاموش"),
            ("حذف کانال اجباری", "حذف کانال اجباری"),
        ],
    },
    "automation": {
        "title": "اتوماسیون",
        "toggles": [
            ("auto_seen_active", "سین خودکار", "سین خودکار روشن", "سین خودکار خاموش"),
            ("auto_reaction_active", "ری‌اکشن خودکار", "ری‌اکشن روشن", "ری‌اکشن خاموش"),
            ("auto_save_media", "ذخیره مدیا", "ذخیره مدیا روشن", "ذخیره مدیا خاموش"),
            ("typing_action_active", "اکشن تایپینگ 24 ساعته", "تایپینگ روشن", "تایپینگ خاموش"),
            ("gaming_action_active", "اکشن گیمینگ 24 ساعته", "گیمینگ روشن", "گیمینگ خاموش"),
            ("voice_action_active", "اکشن ویس 24 ساعته", "ویس روشن", "ویس خاموش"),
            ("video_action_active", "اکشن ارسال ویدیو 24 ساعته", "ارسال ویدیو روشن", "ارسال ویدیو خاموش"),
        ],
        "actions": [
            ("توقف اسپم", "توقف اسپم"),
            ("توقف سیو کانال", "توقف سیو"),
        ],
    },
    "friend_enemy": {
        "title": "دوست و دشمن",
        "toggles": [],
        "actions": [],
        "children": [("دوست", "friend_enemy_friend"), ("دشمن", "friend_enemy_enemy")],
    },
    "tools": {
        "title": "ابزار",
        "toggles": [],
        "actions": [
            ("ماشین حساب", "INFO::برای استفاده تایپ کن: محاسبه [عبارت] — مثال: محاسبه 2+2*3"),
            ("ترجمه", "INFO::برای استفاده تایپ کن: ترجمه [متن]"),
            ("ارز", "ارز"),
            ("آب و هوا", "INFO::برای استفاده تایپ کن: هوا [نام شهر]"),
            ("وضعیت", "وضعیت"),
            ("راهنما", "راهنما"),
            ("لیست بلاک", "لیست بلاک"),
            ("پاکسازی لیست بلاک", "پاکسازی لیست بلاک"),
            ("ترک همگانی گروه", "ترک همگانی گروه"),
            ("ترک همگانی کانال", "ترک همگانی کانال"),
            ("تبدیل به گیف", "INFO::روی یک ویدیو ریپلای کن و تایپ کن: تبدیل به گیف"),
            ("ترجمه متن ریپلای‌شده", "INFO::روی یک پیام متنی ریپلای کن و تایپ کن: ترجمه متن"),
            ("بلاک کاربر", "INFO::روی پیام کاربر ریپلای کن و تایپ کن: بلاک کاربر"),
            ("تنظیم ری‌اکت اختصاصی", "INFO::روی پیام کاربر ریپلای کن و تایپ کن: تنظیم ری‌اکت [ایموجی]"),
        ],
    },
    "ai_assistant": {
        "title": "هوش مصنوعی",
        "toggles": [
            ("ai_assistant_active", "دیپ سیک", "دیپ سیک روشن", "دیپ سیک خاموش"),
        ],
        "actions": [
            ("افزودن اطلاعات", "INFO::برای اضافه‌کردن اطلاعات تایپ کن: آموزش هوش مصنوعی [متن] — مثال: آموزش هوش مصنوعی قیمت گوشی X ۱۰ میلیون تومان است"),
            ("نمایش دانش هوش مصنوعی", "نمایش دانش هوش مصنوعی"),
            ("پاک کردن دانش هوش مصنوعی", "پاک کردن دانش هوش مصنوعی"),
        ],
    },
    "premium_emoji": {
        # این دسته توی helper_bot.py به‌طور خاص هندل می‌شه: با کلیک، فقط یک
        # پیام کوتاه نشون داده می‌شه و هیچ زیرمنویی باز نمی‌شه.
        "title": "ایموجی پرمیوم",
        "toggles": [],
        "actions": [],
        "stub_message": "این بخش هنوز در دسترس نیست",
    },

    # ─── زیرمنوها (توی منوی اصلی نشون داده نمی‌شن، فقط از طریق children) ────
    "clock_font": {
        "title": "فونت ساعت",
        "toggles": [],
        "actions": [(f"فونت {k}", f"فونت ساعت {k}") for k in "0123456789"],
        "parent": "clock",
    },
    "friend_enemy_friend": {
        "title": "دوست",
        "toggles": [],
        "actions": [
            ("نمایش لیست دوست", "نمایش لیست دوست"),
            ("پاک کردن لیست دوست", "پاک کردن لیست دوست"),
        ],
        "parent": "friend_enemy",
    },
    "friend_enemy_enemy": {
        "title": "دشمن",
        "toggles": [
            ("enemy_reply_active", "پاسخ دشمن", "پاسخ دشمن روشن", "پاسخ دشمن خاموش"),
        ],
        "actions": [
            ("نمایش لیست دشمن", "نمایش لیست دشمن"),
            ("پاک کردن لیست دشمن", "پاک کردن لیست دشمن"),
        ],
        "parent": "friend_enemy",
    },
}

# ترتیب نمایش دسته‌ها در منوی اصلی پنل (فقط سطح ۱، زیرمنوها اینجا نیستن)
PANEL_CATEGORY_ORDER = [
    "clock", "text_mode", "locks", "secretary", "forced_join",
    "automation", "friend_enemy", "tools", "ai_assistant", "premium_emoji",
]


def build_category_commands(owner_id: int, category_key: str):
    """
    برای یک دسته‌ی مشخص، آیتم‌های toggle (بر اساس وضعیت لحظه‌ای owner)
    و آیتم‌های action رو با هم به‌صورت یک لیست واحد
    (key, label, command_text, style) برمی‌گردونه - دقیقاً فرمتی که
    get_all_commands_buttons نیاز داره. style رنگ واقعیِ دکمه رو مشخص
    می‌کنه (success/danger/primary)، بدون هیچ ایموجی‌ای توی متن دکمه.
    """
    cat = PANEL_CATEGORIES.get(category_key)
    if not cat:
        return []

    items = []
    for key, label, on_cmd, off_cmd in cat["toggles"]:
        is_on = db.get_setting(owner_id, key) == "1"
        if is_on:
            items.append((key, f"{label}: روشن", off_cmd, "success"))
        else:
            items.append((key, f"{label}: خاموش", on_cmd, "danger"))

    for label, cmd in cat["actions"]:
        items.append((label, label, cmd, "primary"))

    return items


def build_category_menu():
    """لیست دکمه‌های منوی اصلی پنل (فقط عنوان دسته‌ها)."""
    return [(key, PANEL_CATEGORIES[key]["title"], None) for key in PANEL_CATEGORY_ORDER]




class _FakePanelEvent:
    """
    یک شبیه‌ساز سبک از رویداد پیام Telethon تا بشه دستورات متنی موجود در
    _handle_command رو از طریق کلیک روی دکمه‌ی پنل (به‌جای تایپ واقعی توسط
    کاربر) اجرا کرد. به‌جای ادیت یک پیام واقعی، نتیجه رو به «پیام‌های ذخیره‌شده»
    (Saved Messages) خود کاربر می‌فرسته تا لاگ اجرای دستور رو داشته باشه.
    """

    def __init__(self, client):
        self._client = client
        self.message = None

    async def edit(self, text, **kwargs):
        try:
            await self._client.send_message("me", text)
        except Exception:
            pass

    async def get_reply_message(self):
        return None


async def _execute_panel_command(cl, owner_id: int, command_text: str):
    """دستور متنیِ متناظر با دکمه‌ی کلیک‌شده در پنل رو روی کلاینتِ سلفِ کاربر اجرا می‌کنه."""
    entry = bot_manager._bots.get(owner_id) or {}
    fake_event = _FakePanelEvent(cl)
    try:
        await _handle_command(cl, fake_event, command_text, owner_id, entry)
    except Exception as e:
        print(f"❌ خطا در اجرای دستور پنل ({command_text}): {e}")


# ─── حلقه‌های پس‌زمینه ──────────────────────────────────────────────────────────
async def _clock_loop(cl, owner_id):
    """به‌روزرسانی ساعت نام/بیو با دقت بالا - بدون تاخیر"""
    last_minute = -1
    
    while True:
        try:
            # ✅ زمان ایران
            iran_tz = datetime.timezone(datetime.timedelta(hours=3, minutes=30))
            now = datetime.datetime.now(iran_tz)
            current_minute = now.minute
            
            # ✅ فقط در دقیقه‌های جدید به‌روزرسانی کن
            if current_minute != last_minute:
                last_minute = current_minute
                time_str = f"{now.hour:02d}:{now.minute:02d}"
                
                # اعمال فونت مخصوص ساعت
                styled_time = _apply_clock_font(owner_id, time_str)

                # ساعت پرمیوم: یک ایموجی ساعتِ آنالوگ (مطابق ساعت لحظه‌ای) جلوی زمان
                if db.get_setting(owner_id, "clock_premium_active") == "1":
                    clock_face = _CLOCK_FACE_EMOJIS[now.hour % 12]
                    styled_time = f"{clock_face} {styled_time}"
                
                # به‌روزرسانی نام
                if db.get_setting(owner_id, "clock_name_active") == "1":
                    try:
                        await cl(UpdateProfileRequest(last_name=styled_time[:64]))
                        print(f"⏰ [{owner_id}] ساعت نام به‌روز شد: {styled_time}")
                    except Exception as e:
                        print(f"❌ خطا در به‌روزرسانی نام: {e}")
                
                # به‌روزرسانی بیو
                if db.get_setting(owner_id, "clock_bio_active") == "1":
                    try:
                        await cl(UpdateProfileRequest(about=f"⏰ {styled_time}"[:70]))
                        print(f"⏰ [{owner_id}] ساعت بیو به‌روز شد: {styled_time}")
                    except Exception as e:
                        print(f"❌ خطا در به‌روزرسانی بیو: {e}")
            
            # ✅ چک کردن هر 5 ثانیه برای دقت بالا
            await asyncio.sleep(5)
            
        except Exception as e:
            print(f"❌ خطا در _clock_loop: {e}")
            await asyncio.sleep(10)


async def _typing_loop(cl, owner_id):
    """
    اکشن‌های ۲۴ ساعته: تا وقتی هرکدوم روشن باشن، به‌صورت مداوم وضعیت مربوطه
    («در حال تایپ»، «در حال بازی»، «در حال ضبط ویس»، «در حال ارسال ویدیو»)
    رو در پیوی‌های اخیر کاربر نشون می‌ده. هر کدوم مستقل از بقیه روشن/خاموش می‌شن.
    """
    ACTIONS = [
        ("typing_action_active", "typing"),
        ("gaming_action_active", "game"),
        ("voice_action_active", "record-audio"),
        ("video_action_active", "upload-video"),
    ]
    while True:
        try:
            active_actions = [action for key, action in ACTIONS if db.get_setting(owner_id, key) == "1"]
            if active_actions:
                try:
                    async for dialog in cl.iter_dialogs(limit=30):
                        if not dialog.is_user:
                            continue
                        for key, action in ACTIONS:
                            if db.get_setting(owner_id, key) != "1":
                                continue
                            try:
                                await cl.send_chat_action(dialog.id, action)
                            except Exception:
                                pass
                            await asyncio.sleep(1)
                except Exception as e:
                    print(f"خطا در اکشن‌های ۲۴ ساعته: {e}")
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(5)
        except Exception as e:
            print(f"خطا در _typing_loop: {e}")
            await asyncio.sleep(10)


async def _scheduler_loop(cl, owner_id):
    while True:
        try:
            for p in db.get_pending_scheduled(owner_id):
                try:
                    await cl.send_message(p["chat_id"], p["message"])
                    db.mark_scheduled_sent(p["id"])
                except Exception:
                    pass
        except Exception:
            pass
        await asyncio.sleep(30)

