import threading
import time
import telebot
from telebot import types
import database as db
import config
import datetime
import random
import re

# ─── ورود با کیپد عددی (import از bot.py فقط در صورت وجود) ──────────────────────
try:
    from bot import verify_login_code, verify_login_2fa, has_pending_code_login
    _BOT_LOGIN_AVAILABLE = True
except ImportError:
    _BOT_LOGIN_AVAILABLE = False

# ─── بافر کیپد هر کاربر: {user_id: {"digits": [], "ts": timestamp, "mode": "code"|"2fa"}} ──────
_keypad_buffers: dict = {}
_KEYPAD_TIMEOUT = 120  # ثانیه — بعد از ۲ دقیقه بافر پاک می‌شود

# ─── وقت تهران ───────────────────────────────────────────────────────────────
_TEHRAN_OFFSET = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

def _now_tehran() -> datetime.datetime:
    return datetime.datetime.now(_TEHRAN_OFFSET)

def _fmt_tehran(dt) -> str:
    """تبدیل datetime به رشته فارسی با وقت تهران"""
    if dt is None:
        return "نامشخص"
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    tehran = dt.astimezone(_TEHRAN_OFFSET)
    return tehran.strftime("%Y/%m/%d — %H:%M")

def _remaining_str(dt) -> str:
    """باقی‌مانده زمان تا انقضا به فارسی"""
    if dt is None:
        return "نامشخص"
    if isinstance(dt, str):
        try:
            dt = datetime.datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except Exception:
            return "نامشخص"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = dt - now
    if diff.total_seconds() <= 0:
        return "منقضی شده"
    days = diff.days
    hours = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    if days > 0:
        return f"{days} روز و {hours} ساعت"
    elif hours > 0:
        return f"{hours} ساعت و {minutes} دقیقه"
    else:
        return f"{minutes} دقیقه"

_bot = None
BOT_USERNAME = None
OWNER_TG_ID = 8296865861

# ─── کش ──────────────────────────────────────────────────────────────────────
class SmartCache:
    def __init__(self):
        self._data = {}
        self._timestamps = {}
    
    def get(self, key, default=None):
        if key in self._data and key in self._timestamps:
            ttl = self._get_ttl(key)
            if time.time() - self._timestamps[key] < ttl:
                return self._data[key]
            else:
                del self._data[key]
                del self._timestamps[key]
        return default
    
    def set(self, key, value):
        self._data[key] = value
        self._timestamps[key] = time.time()
    
    def invalidate(self, pattern=None):
        if pattern is None:
            self._data.clear()
            self._timestamps.clear()
        else:
            keys_to_del = [k for k in list(self._data.keys()) if k.startswith(pattern)]
            for k in keys_to_del:
                self._data.pop(k, None)
                self._timestamps.pop(k, None)
    
    def _get_ttl(self, key):
        if key.startswith("membership_"):
            return 900
        if key.startswith("account_"):
            return 300
        if key.startswith("stats_"):
            return 60
        if key.startswith("challenge_"):
            return 120
        return 300

cache = SmartCache()
_owner_states = {}
# ─── شرط‌بندی‌های فعال: bet_id -> {creator_tg_id, opponent_tg_id or None} ────
_active_bets = {}


def get_bot():
    return _bot


def _check_membership_cached(user_id):
    cache_key = f"membership_{user_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        is_member, missing = db.check_user_membership(_bot, user_id)
        result = (is_member, missing)
        cache.set(cache_key, result)
        return result
    except Exception as e:
        print(f"⚠️ خطا در بررسی عضویت: {e}")
        return True, []


def _get_account_cached(tg_id):
    cache_key = f"account_{tg_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    account = db.get_account_by_tg_id(tg_id)
    if account:
        cache.set(cache_key, account)
    return account


def start_token_bot():
    global _bot, BOT_USERNAME

    if not config.BOT_TOKEN:
        print("⚠️ BOT_TOKEN تنظیم نشده — ربات الماس غیرفعال است")
        return

    try:
        _bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=4)
        me = _bot.get_me()
        BOT_USERNAME = me.username
        print(f"🤖 ربات الماس: @{BOT_USERNAME}")
    except Exception as e:
        print(f"❌ خطا در اتصال ربات الماس: {e}")
        _bot = None
        return

    for _ in range(3):
        try:
            _bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            break
        except:
            time.sleep(2)

    # ─── توابع کمکی ───────────────────────────────────────────────────────────
    def send_forced_channels_menu(message, missing_channels):
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in missing_channels:
            ch_clean = ch.lstrip("@")
            markup.add(types.InlineKeyboardButton(f"📢 عضویت در {ch}", url=f"https://t.me/{ch_clean}"))
        markup.add(types.InlineKeyboardButton("✅ بررسی عضویت من", callback_data="check_join"))
        
        channels_list = "\n".join([f"🔸 {ch}" for ch in missing_channels])
        _bot.reply_to(
            message,
            "⛔️ <b>ورود به ربات منوط به عضویت در کانال‌های زیر است:</b>\n\n"
            f"{channels_list}\n\n"
            "👇 روی هر کانال کلیک کنید و Join بزنید، سپس دکمه «بررسی عضویت من» را بزنید:",
            reply_markup=markup
        )

    def require_membership(message):
        if message.chat.type != 'private':
            return True
        is_member, missing = _check_membership_cached(message.from_user.id)
        if not is_member:
            send_forced_channels_menu(message, missing)
            return False
        return True

    def _user_keyboard():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("💎 موجودی", "🎁 هدیه روزانه")
        markup.add("🔗 رفرال", "🛒 خرید الماس")
        markup.add("🎯 ماموریت‌ها")
        return markup

    def _owner_keyboard():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("💎 موجودی", "🎁 هدیه روزانه")
        markup.add("🔗 رفرال", "🛒 خرید الماس")
        markup.add("🎯 ماموریت‌ها")
        markup.add("📢 مدیریت")
        return markup

    def _admin_panel_keyboard():
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📢 چنل‌های اجباری", callback_data="admin_channels"),
            types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users")
        )
        markup.add(
            types.InlineKeyboardButton("🏆 جام جهانی", callback_data="admin_wc"),
            types.InlineKeyboardButton("📅 بازی‌های امروز", callback_data="admin_today_games")
        )
        markup.add(
            types.InlineKeyboardButton("💎 انتقال الماس", callback_data="admin_transfer"),
            types.InlineKeyboardButton("💰 دادن الماس", callback_data="admin_give")
        )
        markup.add(
            types.InlineKeyboardButton("💳 تنظیم شماره کارت", callback_data="admin_set_card"),
            types.InlineKeyboardButton("🧾 پرداخت‌های معلق", callback_data="admin_payments")
        )
        markup.add(
            types.InlineKeyboardButton("📢 پیام عمومی", callback_data="admin_broadcast"),
            types.InlineKeyboardButton("🎯 ماموریت‌ها", callback_data="admin_missions")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
        return markup

    # ══════════════════════════════════════════════════════════════════════════
    # 🎯 دستور شرط بندی — فقط در گروه سلف
    # ══════════════════════════════════════════════════════════════════════════
    SELF_GROUP = getattr(config, 'WORLD_CUP_GROUP', '@Gp_SelfNexo')
    BET_TAX = 0.17

    def _is_self_group(chat):
        """بررسی می‌کند آیا پیام از گروه سلف است"""
        if chat.type not in ('group', 'supergroup'):
            return False
        username = getattr(chat, 'username', None)
        if username and f"@{username.lower()}" == SELF_GROUP.lower():
            return True
        return False

    @_bot.message_handler(
        func=lambda m: m.text and m.text.strip().startswith("شرط بندی "),
        chat_types=['group', 'supergroup']
    )
    def cmd_bet(message):
        try:
            if not _is_self_group(message.chat):
                return

            parts = message.text.strip().split()
            if len(parts) < 3:
                return _bot.reply_to(message, "❗ فرمت: شرط بندی [مقدار]\nمثال: شرط بندی 100")

            try:
                amount = int(parts[2])
                if amount < 1:
                    return _bot.reply_to(message, "❌ مقدار باید بیشتر از ۰ باشد.")
            except ValueError:
                return _bot.reply_to(message, "❌ مقدار باید عدد باشد.")

            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.")

            balance = db.get_token_balance(account["id"])
            if balance < amount:
                return _bot.reply_to(
                    message,
                    f"❌ موجودی کافی ندارید!\nنیاز: {amount} الماس — موجودی: {balance} الماس"
                )

            bet_id = db.create_bet(account["id"], message.from_user.id, amount, message.chat.id)
            if not bet_id:
                return _bot.reply_to(message, "❌ خطا در ساخت شرط‌بندی. دوباره امتحان کنید.")

            _active_bets[bet_id] = {
                "creator_tg_id": message.from_user.id,
                "opponent_tg_id": None,
            }

            creator_name = (
                f"@{message.from_user.username}" if message.from_user.username
                else message.from_user.first_name
            )
            payout = round(amount * 2 * (1 - BET_TAX))

            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton(
                    "⚔️ ورود به شرط‌بندی",
                    callback_data=f"join_bet_{bet_id}"
                )
            )

            msg = _bot.reply_to(
                message,
                f"🎲 <b>شرط‌بندی باز شد!</b>\n\n"
                f"👤 سازنده: {creator_name}\n"
                f"💎 مبلغ: <b>{amount} الماس</b>\n"
                f"🏆 جایزه برنده: <b>{payout} الماس</b> (بعد از ۱۷٪ مالیات)\n\n"
                f"⏳ منتظر حریف...\n"
                f"(اولین نفری که دکمه بزند وارد می‌شود)",
                reply_markup=markup
            )
            db.update_bet_message(bet_id, msg.message_id)

            # تایمر ۵ دقیقه — اگر کسی وارد نشد، لغو و برگشت موجودی
            threading.Timer(300, _auto_cancel_bet, args=[bet_id, message.chat.id, msg.message_id]).start()

        except Exception as e:
            print(f"❌ خطا در cmd_bet: {e}")
            _bot.reply_to(message, f"❌ خطا: {e}")

    # ── Callback: ورود به شرط‌بندی ─────────────────────────────────────────────
    @_bot.callback_query_handler(func=lambda call: call.data.startswith("join_bet_"))
    def callback_join_bet(call):
        try:
            bet_id = int(call.data.split("_")[2])

            # بررسی حافظه محلی اول (سریع‌تر)
            bet_mem = _active_bets.get(bet_id)
            if bet_mem is None:
                return _bot.answer_callback_query(call.id, "❌ این شرط‌بندی یافت نشد یا منقضی شده.", show_alert=True)

            if bet_mem["opponent_tg_id"] is not None:
                return _bot.answer_callback_query(call.id, "❌ این شرط‌بندی قبلاً تکمیل شده است.", show_alert=True)

            if bet_mem["creator_tg_id"] == call.from_user.id:
                return _bot.answer_callback_query(call.id, "❌ شما سازنده این شرط هستید! منتظر حریف باشید.", show_alert=True)

            account = _get_account_cached(call.from_user.id)
            if not account:
                return _bot.answer_callback_query(call.id, "❌ ابتدا در پنل وب ثبت‌نام کنید.", show_alert=True)

            # ورود به دیتابیس (کسر موجودی نفر دوم + آپدیت وضعیت)
            success, msg_txt = db.join_bet(bet_id, account["id"], call.from_user.id)
            if not success:
                return _bot.answer_callback_query(call.id, msg_txt, show_alert=True)

            # علامت‌گذاری در حافظه
            bet_mem["opponent_tg_id"] = call.from_user.id

            opponent_name = (
                f"@{call.from_user.username}" if call.from_user.username
                else call.from_user.first_name
            )
            _bot.answer_callback_query(call.id, "✅ وارد شرط‌بندی شدید! بازی شروع می‌شود...", show_alert=True)

            bet = db.get_bet(bet_id)
            if not bet:
                return

            # اجرای شرط و انتخاب برنده
            ok, winner, payout = db.finish_bet(bet_id)
            if not ok:
                return

            # پیدا کردن نام برنده
            winner_tg_id = winner["tg_id"]
            try:
                winner_chat = _bot.get_chat(winner_tg_id)
                winner_name = (
                    f"@{winner_chat.username}" if winner_chat.username
                    else winner_chat.first_name
                )
            except Exception:
                winner_name = str(winner_tg_id)

            amount = bet["amount"]
            total = amount * 2
            tax = round(total * BET_TAX)

            result_text = (
                f"🎉 <b>شرط‌بندی به پایان رسید!</b>\n\n"
                f"⚔️ حریف: {opponent_name}\n"
                f"💎 مبلغ هر نفر: {amount} الماس\n"
                f"💰 مجموع: {total} الماس\n"
                f"🏛 مالیات (۱۷٪): {tax} الماس\n\n"
                f"🏆 <b>برنده: {winner_name}</b>\n"
                f"💎 <b>جایزه: {payout} الماس</b>"
            )

            # ویرایش پیام اصلی
            try:
                _bot.edit_message_text(
                    result_text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
            except Exception:
                _bot.send_message(call.message.chat.id, result_text)

            # اطلاع به برنده در پیوی
            try:
                _bot.send_message(
                    winner_tg_id,
                    f"🎉 <b>تبریک! شرط‌بندی را بردید!</b>\n💎 <b>{payout} الماس</b> به حسابتان واریز شد."
                )
            except Exception:
                pass

            # اطلاع به بازنده
            loser_tg_id = (
                bet["creator_tg_id"] if winner_tg_id == bet["opponent_tg_id"]
                else bet["opponent_tg_id"]
            )
            try:
                _bot.send_message(
                    loser_tg_id,
                    f"😔 متأسفانه این بار نبردید.\n💎 {amount} الماس از حسابتان کسر شد."
                )
            except Exception:
                pass

            _active_bets.pop(bet_id, None)

        except Exception as e:
            print(f"❌ خطا در callback_join_bet: {e}")
            try:
                _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:100]}", show_alert=True)
            except Exception:
                pass

    # ── لغو خودکار شرط (تایمر ۵ دقیقه) ────────────────────────────────────────
    def _auto_cancel_bet(bet_id, chat_id, message_id):
        try:
            bet_mem = _active_bets.get(bet_id)
            if bet_mem is None or bet_mem["opponent_tg_id"] is not None:
                return  # شرط تکمیل شده

            db.cancel_bet(bet_id)
            _active_bets.pop(bet_id, None)

            try:
                _bot.edit_message_text(
                    "⏰ <b>شرط‌بندی لغو شد!</b>\n\nهیچ حریفی وارد نشد.\n💎 مبلغ به سازنده بازگشت داده شد.",
                    chat_id=chat_id,
                    message_id=message_id
                )
            except Exception:
                _bot.send_message(chat_id, "⏰ یک شرط‌بندی به دلیل نبود حریف لغو شد.")
        except Exception as e:
            print(f"❌ خطا در _auto_cancel_bet: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # 💰 دستور موجودی در گروه
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(func=lambda m: m.text and m.text == "موجودی", chat_types=['group', 'supergroup'])
    def cmd_balance_group(message):
        try:
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.")
            
            stats = db.get_token_stats(account["id"])
            _bot.reply_to(
                message,
                f"💎 <b>موجودی شما:</b>\n\n"
                f"💰 الماس: <b>{stats['balance']}</b>\n"
                f"📊 کل دریافتی: <b>{stats['total_earned']}</b>"
            )
        except Exception as e:
            print(f"❌ خطا در cmd_balance_group: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # 💎 انتقال الماس
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(func=lambda m: m.text and m.text.startswith("انتقال "), chat_types=['private', 'group', 'supergroup'])
    def cmd_transfer(message):
        try:
            parts = message.text.split()

            # ── حالت گروه مدیریت: ریپلای روی پیام کاربر + «انتقال [عدد]» ──────
            if len(parts) == 2 and message.reply_to_message:
                target_user = message.reply_to_message.from_user
                if not target_user or target_user.is_bot:
                    return _bot.reply_to(message, "❌ نمی‌توان به این کاربر الماس انتقال داد.")

                try:
                    amount = int(parts[1])
                    if amount < 1:
                        return _bot.reply_to(message, "❌ مقدار باید بیشتر از 0 باشد.")
                except ValueError:
                    return _bot.reply_to(message, "❌ مقدار باید عدد باشد.")

                if target_user.id == message.from_user.id:
                    return _bot.reply_to(message, "❌ نمی‌توانید به خودتان الماس انتقال دهید.")

                from_account = _get_account_cached(message.from_user.id)
                if not from_account:
                    return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.")

                to_account = db.get_account_by_tg_id(target_user.id)
                if not to_account:
                    return _bot.reply_to(message, "❌ این کاربر در پنل وب ثبت‌نام نکرده است.")

                success, msg = db.transfer_diamonds(from_account["id"], to_account["id"], amount)

                if success:
                    cache.invalidate(f"account_{message.from_user.id}")
                    to_tg_id = db.get_telegram_id_by_owner(to_account["id"])
                    if to_tg_id:
                        try:
                            _bot.send_message(
                                to_tg_id,
                                f"💎 <b>{amount} الماس</b> از @{message.from_user.username or 'کاربر'} دریافت کردید!"
                            )
                        except Exception:
                            pass

                return _bot.reply_to(message, msg)

            # ── حالت معمول: «انتقال [یوزرنیم] [عدد]» ─────────────────────────
            if len(parts) < 3:
                return _bot.reply_to(message, "❗ فرمت: انتقال [یوزرنیم] [تعداد]\nمثال: انتقال @ali 10\nیا روی پیام کاربر ریپلای کنید و بنویسید: انتقال [تعداد]")
            
            username = parts[1].lstrip("@")
            try:
                amount = int(parts[2])
                if amount < 1:
                    return _bot.reply_to(message, "❌ مقدار باید بیشتر از 0 باشد.")
            except:
                return _bot.reply_to(message, "❌ مقدار باید عدد باشد.")
            
            from_account = _get_account_cached(message.from_user.id)
            if not from_account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.")
            
            to_account = db.get_account_by_username(username)
            if not to_account:
                return _bot.reply_to(message, f"❌ کاربر '{username}' یافت نشد.")
            
            if to_account["id"] == from_account["id"]:
                return _bot.reply_to(message, "❌ نمی‌توانید به خودتان الماس انتقال دهید.")
            
            success, msg = db.transfer_diamonds(from_account["id"], to_account["id"], amount)
            
            if success:
                cache.invalidate(f"account_{message.from_user.id}")
                to_tg_id = db.get_telegram_id_by_owner(to_account["id"])
                if to_tg_id:
                    try:
                        _bot.send_message(
                            to_tg_id,
                            f"💎 <b>{amount} الماس</b> از @{message.from_user.username or 'کاربر'} دریافت کردید!"
                        )
                    except:
                        pass
            
            _bot.reply_to(message, msg)
            
        except Exception as e:
            print(f"❌ خطا در cmd_transfer: {e}")
            _bot.reply_to(message, f"❌ خطا: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # ⚽ سیستم جام جهانی — football-data.org
    # ══════════════════════════════════════════════════════════════════════════

    # کش محلی نتایج API (برای کاهش مصرف)
    _wc_api_cache = {"matches": [], "results": {}, "last_fetch": 0, "last_result_fetch": 0}
    # وضعیت انتخاب تیم کاربران: tg_id -> {challenge_id, selected_option}
    _wc_pending_bet = {}

    IRAN_TZ = datetime.timezone(datetime.timedelta(hours=3, minutes=30))

    def _wc_utc_to_iran(dt: datetime.datetime) -> datetime.datetime:
        """تبدیل datetime (UTC، naive یا aware) به ساعت ایران (UTC+3:30)"""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(IRAN_TZ)

    def _wc_api_get(endpoint: str) -> dict:
        """فراخوانی API football-data.org"""
        import urllib.request, urllib.error, json as _json
        api_key = getattr(config, "FOOTBALL_API_KEY", "")
        if not api_key:
            print("⚠️ FOOTBALL_API_KEY تنظیم نشده — درخواست به Football API ارسال نشد.")
            return {}
        url = f"https://api.football-data.org/v4/{endpoint}"
        req = urllib.request.Request(url, headers={"X-Auth-Token": api_key})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return _json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode()[:300]
            except Exception:
                pass
            print(f"❌ Football API HTTP {e.code} [{endpoint}]: {body}")
            return {}
        except Exception as e:
            print(f"❌ Football API error [{endpoint}]: {e}")
            return {}

    def _wc_get_matches() -> list:
        """دریافت بازی‌های آینده از API (با کش ۱۰ دقیقه)"""
        now = time.time()
        if now - _wc_api_cache["last_fetch"] < 600 and _wc_api_cache["matches"]:
            return _wc_api_cache["matches"]
        comp = getattr(config, "WC_COMPETITION", "WC")
        data = _wc_api_get(f"competitions/{comp}/matches?status=SCHEDULED")
        matches = data.get("matches", [])
        _wc_api_cache["matches"] = matches
        _wc_api_cache["last_fetch"] = now
        return matches

    def _wc_get_today_matches() -> list:
        """دریافت بازی‌های امروز (هر وضعیتی) — بدون کش، برای دکمه «بازی‌های امروز»"""
        comp = getattr(config, "WC_COMPETITION", "WC")
        today_str = datetime.datetime.now(IRAN_TZ).strftime("%Y-%m-%d")
        data = _wc_api_get(f"competitions/{comp}/matches?dateFrom={today_str}&dateTo={today_str}")
        return data.get("matches", [])

    def _wc_get_finished_matches() -> list:
        """دریافت بازی‌های تمام‌شده (با کش ۵ دقیقه)"""
        now = time.time()
        if now - _wc_api_cache["last_result_fetch"] < 300:
            return _wc_api_cache.get("finished", [])
        comp = getattr(config, "WC_COMPETITION", "WC")
        data = _wc_api_get(f"competitions/{comp}/matches?status=FINISHED")
        finished = data.get("matches", [])
        _wc_api_cache["finished"] = finished
        _wc_api_cache["last_result_fetch"] = now
        return finished

    def _wc_determine_winner(match: dict) -> str:
        """تعیین برنده از نتیجه بازی"""
        score = match.get("score", {})
        winner = score.get("winner")  # HOME_TEAM / AWAY_TEAM / DRAW
        if winner == "HOME_TEAM":
            return "team1"
        elif winner == "AWAY_TEAM":
            return "team2"
        elif winner == "DRAW":
            return "draw"
        return ""

    def _wc_send_challenge_to_channel(challenge_id: int, team1: str, team2: str, match_time_str: str):
        """ارسال چالش به کانال"""
        channel = getattr(config, "WC_CHANNEL_ID", "")
        if not channel:
            print("⚠️ WC_CHANNEL_ID تنظیم نشده! چالش جام جهانی به هیچ کانالی ارسال نمی‌شود.")
            return
        # اگر آیدی کانال به‌صورت عددی (مثل -1001234567) ست شده، به int تبدیل می‌کنیم
        chat_target = channel
        if isinstance(channel, str) and channel.lstrip("-").isdigit():
            chat_target = int(channel)

        min_bet = getattr(config, "WC_MIN_BET", 10)
        max_bet = getattr(config, "WC_MAX_BET", 5000)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🔵 {team1}", callback_data=f"wc_pick_{challenge_id}_team1"),
            types.InlineKeyboardButton("🤝 مساوی",    callback_data=f"wc_pick_{challenge_id}_draw"),
            types.InlineKeyboardButton(f"🔴 {team2}", callback_data=f"wc_pick_{challenge_id}_team2"),
        )
        now_tehran = _now_tehran().strftime("%Y/%m/%d — %H:%M")
        text = (
            f"⚽️ <b>چالش جام جهانی ۲۰۲۶</b>\n\n"
            f"🆚 <b>{team1}</b>  vs  <b>{team2}</b>\n"
            f"⏰ زمان بازی: <b>{match_time_str}</b>\n"
            f"🕐 ارسال در: {now_tehran} (تهران)\n\n"
            f"💎 محدوده شرط: {min_bet:,} – {max_bet:,} الماس\n"
            f"🏆 برندگان ۲ برابر مبلغ شرط دریافت می‌کنند!\n\n"
            f"👇 روی تیم مورد نظرت کلیک کن:"
        )
        try:
            msg = _bot.send_message(chat_target, text, reply_markup=markup)
            db.set_wc_channel_msg(challenge_id, msg.message_id)
            print(f"✅ چالش به کانال {chat_target} ارسال شد (msg_id={msg.message_id})")
        except Exception as e:
            print(f"❌ ارسال چالش به کانال {chat_target} ناموفق بود: {e}\n"
                  f"   بررسی کنید که ربات ادمین کانال باشد و WC_CHANNEL_ID درست تنظیم شده باشد (مثل @channel یا -100xxxxxxxxxx).")

    def _wc_auto_fetch_and_create():
        """بررسی بازی‌های جدید و ساخت چالش خودکار"""
        try:
            matches = _wc_get_matches()
            for m in matches:
                match_id = str(m.get("id", ""))
                if not match_id or db.wc_challenge_exists(match_id):
                    continue

                home_team = m.get("homeTeam", {})
                away_team = m.get("awayTeam", {})

                # نام تیم را از چند فیلد مختلف امتحان می‌کنیم
                home = (home_team.get("shortName") or home_team.get("name") or "").strip()
                away = (away_team.get("shortName") or away_team.get("name") or "").strip()

                # اگر هنوز تیم‌ها مشخص نشده‌اند (مرحله حذفی) رد می‌کنیم
                if not home or not away:
                    continue

                utc_date = m.get("utcDate", "")
                try:
                    dt = datetime.datetime.strptime(utc_date, "%Y-%m-%dT%H:%M:%SZ")
                    # فقط بازی‌هایی که حداقل ۳۰ دقیقه دیگر شروع می‌شوند
                    if dt < datetime.datetime.utcnow() + datetime.timedelta(minutes=30):
                        continue
                    dt_iran = _wc_utc_to_iran(dt)
                    match_time_str = dt_iran.strftime("%Y-%m-%d %H:%M") + " به وقت ایران"
                except Exception:
                    match_time_str = utc_date
                    dt = utc_date

                challenge_id = db.create_wc_challenge(match_id, home, away, dt)
                if challenge_id:
                    _wc_send_challenge_to_channel(challenge_id, home, away, match_time_str)
                    print(f"✅ چالش جدید ساخته شد: {home} vs {away} (ID: {challenge_id})")
                    time.sleep(0.3)  # جلوگیری از flood در ارسال به کانال
        except Exception as e:
            print(f"❌ _wc_auto_fetch_and_create: {e}")

    def _wc_auto_check_results():
        """بررسی نتایج بازی‌های تمام‌شده و اعلام برنده"""
        try:
            pending = db.get_pending_wc_challenges()
            if not pending:
                return
            finished = _wc_get_finished_matches()
            finished_ids = {str(m["id"]): m for m in finished}
            channel = getattr(config, "WC_CHANNEL_ID", "")

            for ch in pending:
                match_id = str(ch.get("match_id", ""))
                if match_id not in finished_ids:
                    continue
                match = finished_ids[match_id]
                winner_option = _wc_determine_winner(match)
                if not winner_option:
                    continue

                paid = db.finish_wc_challenge(ch["id"], winner_option)

                option_fa = {"team1": ch["team1"], "team2": ch["team2"], "draw": "مساوی"}.get(winner_option, winner_option)
                result_text = (
                    f"🏁 <b>پایان چالش!</b>\n\n"
                    f"⚽️ {ch['team1']} vs {ch['team2']}\n"
                    f"🏆 نتیجه: <b>{option_fa}</b>\n\n"
                    f"✅ برندگان ۲ برابر مبلغ شرطشان دریافت کردند!"
                )
                if channel and ch.get("channel_msg_id"):
                    try:
                        _bot.edit_message_text(result_text, chat_id=channel, message_id=ch["channel_msg_id"])
                    except Exception:
                        try:
                            _bot.send_message(channel, result_text)
                        except Exception:
                            pass

                # اطلاع رسانی به برندگان در پیوی
                for winner in paid:
                    try:
                        _bot.send_message(
                            winner["user_tg_id"],
                            f"🎉 <b>تبریک!</b> شرط‌بندی {ch['team1']} vs {ch['team2']} را بردید!\n"
                            f"💎 <b>{winner['payout']} الماس</b> به حسابتان واریز شد."
                        )
                    except Exception:
                        pass
        except Exception as e:
            print(f"❌ _wc_auto_check_results: {e}")

    def _wc_scheduler():
        """
        حلقه زمانی:
        - هر ۱۵ دقیقه بازی‌های آینده چک می‌شوند
        - اگه بازی ۱ ساعت دیگه شروع بشه و چالشش ارسال نشده → همون لحظه می‌فرسته
        - نتایج بازی‌های تموم‌شده هم چک می‌شه
        """
        POLL = 900  # 15 دقیقه
        SEND_BEFORE_SECONDS = 3600  # 1 ساعت قبل از شروع

        while True:
            try:
                # ─── چک بازی‌های آینده برای ارسال ۱ ساعت قبل ─────────────
                comp = getattr(config, "WC_COMPETITION", "WC")
                data = _wc_api_get(f"competitions/{comp}/matches?status=SCHEDULED,TIMED")
                matches = data.get("matches", [])
                now_utc = datetime.datetime.utcnow()

                for m in matches:
                    match_id = str(m.get("id", ""))
                    if not match_id:
                        continue

                    utc_date = m.get("utcDate", "")
                    try:
                        dt = datetime.datetime.strptime(utc_date, "%Y-%m-%dT%H:%M:%SZ")
                    except Exception:
                        continue

                    seconds_until = (dt - now_utc).total_seconds()

                    # فقط بازی‌هایی که ۱ ساعت مانده تا شروعشون (با تلرانس ۱۵ دقیقه)
                    if not (0 < seconds_until <= SEND_BEFORE_SECONDS + POLL):
                        continue

                    if db.wc_challenge_exists(match_id):
                        continue  # قبلاً ارسال شده

                    home = (m.get("homeTeam", {}).get("shortName") or
                            m.get("homeTeam", {}).get("name") or "").strip()
                    away = (m.get("awayTeam", {}).get("shortName") or
                            m.get("awayTeam", {}).get("name") or "").strip()

                    if not home or not away:
                        continue  # تیم مشخص نشده

                    try:
                        dt_tehran = _wc_utc_to_iran(dt)
                        match_time_str = dt_tehran.strftime("%Y/%m/%d — %H:%M") + " (تهران)"
                    except Exception:
                        match_time_str = utc_date

                    challenge_id = db.create_wc_challenge(match_id, home, away, dt)
                    if challenge_id:
                        _wc_send_challenge_to_channel(challenge_id, home, away, match_time_str)
                        print(f"✅ چالش ۱ ساعت قبل ارسال شد: {home} vs {away}")
                    time.sleep(0.5)

                # ─── چک نتایج بازی‌های تموم‌شده ─────────────────────────────
                _wc_auto_check_results()

            except Exception as e:
                print(f"❌ _wc_scheduler: {e}")
            time.sleep(POLL)

    # اجرای scheduler در Thread جداگانه
    _wc_thread = threading.Thread(target=_wc_scheduler, daemon=True)
    _wc_thread.start()

    # ── تست اولیه دسترسی به کانال جام جهانی ─────────────────────────────────
    _wc_channel_cfg = getattr(config, "WC_CHANNEL_ID", "")
    if not _wc_channel_cfg:
        print("⚠️ WC_CHANNEL_ID تنظیم نشده — چالش‌های جام جهانی به هیچ کانالی ارسال نمی‌شوند.")
    else:
        _wc_target = int(_wc_channel_cfg) if str(_wc_channel_cfg).lstrip("-").isdigit() else _wc_channel_cfg
        try:
            chat_info = _bot.get_chat(_wc_target)
            member = _bot.get_chat_member(_wc_target, _bot.get_me().id)
            if member.status not in ("administrator", "creator"):
                print(f"⚠️ ربات در کانال {_wc_target} ادمین نیست — ارسال پیام به کانال شکست خواهد خورد.")
            else:
                print(f"✅ دسترسی به کانال جام جهانی تأیید شد: {getattr(chat_info, 'title', _wc_target)}")
        except Exception as e:
            print(f"❌ ربات نتوانست به کانال {_wc_target} دسترسی پیدا کند: {e}\n"
                  f"   بررسی کنید ربات در کانال عضو/ادمین باشد و WC_CHANNEL_ID صحیح باشد.")
    if not getattr(config, "FOOTBALL_API_KEY", ""):
        print("⚠️ FOOTBALL_API_KEY تنظیم نشده — هیچ بازی‌ای از Football API دریافت نمی‌شود.")

    # ── Callback: کاربر روی تیم کلیک کرد ────────────────────────────────────
    @_bot.callback_query_handler(func=lambda call: call.data.startswith("wc_pick_"))
    def callback_wc_pick(call):
        try:
            _, _, cid, option = call.data.split("_", 3)
            challenge_id = int(cid)
            challenge = db.get_wc_challenge(challenge_id)
            if not challenge or challenge["status"] != "pending":
                return _bot.answer_callback_query(call.id, "❌ این چالش دیگر فعال نیست.", show_alert=True)

            account = _get_account_cached(call.from_user.id)
            if not account:
                return _bot.answer_callback_query(call.id, "❌ ابتدا در پنل وب ثبت‌نام کنید.", show_alert=True)

            min_bet = getattr(config, "WC_MIN_BET", 10)
            max_bet = getattr(config, "WC_MAX_BET", 5000)
            option_fa = {"team1": challenge["team1"], "team2": challenge["team2"], "draw": "مساوی"}.get(option, option)

            # ذخیره انتخاب موقت
            _wc_pending_bet[call.from_user.id] = {
                "challenge_id": challenge_id,
                "selected_option": option,
                "account_id": account["id"],
            }

            _bot.answer_callback_query(call.id, f"✅ انتخاب: {option_fa}", show_alert=False)
            try:
                _bot.send_message(
                    call.from_user.id,
                    f"⚽️ انتخاب شما: <b>{option_fa}</b>\n\n"
                    f"💎 مبلغ شرط را وارد کنید ({min_bet} تا {max_bet} الماس):\n"
                    f"مثال: <code>شرکت 200</code>"
                )
            except Exception:
                # اگر چت خصوصی باز نیست
                _bot.answer_callback_query(
                    call.id,
                    f"✅ انتخاب: {option_fa}\n\n"
                    f"برای ثبت شرط، به ربات پیام بده:\nشرکت [مبلغ]\nمثال: شرکت 200",
                    show_alert=True
                )
        except Exception as e:
            print(f"❌ callback_wc_pick: {e}")

    # ── Handler: کاربر مبلغ شرط را وارد کرد ────────────────────────────────
    @_bot.message_handler(func=lambda m: m.text and (m.text.strip().startswith("شرکت ") or (m.from_user.id in _wc_pending_bet and m.text.strip().isdigit())) and m.chat.type == "private")
    def cmd_wc_join(message):
        try:
            tg_id = message.from_user.id
            pending = _wc_pending_bet.get(tg_id)
            if not pending:
                return _bot.reply_to(message, "❌ ابتدا روی تیم مورد نظر در کانال کلیک کنید.")

            text = message.text.strip()
            # قبول هم "شرکت 200" و هم مستقیم "200"
            if text.startswith("شرکت "):
                num_str = text[len("شرکت "):].strip()
            else:
                num_str = text

            try:
                amount = int(num_str)
            except (ValueError, AttributeError):
                return _bot.reply_to(message, "❌ لطفاً یک عدد وارد کنید.\nمثال: <code>200</code>")

            min_bet = getattr(config, "WC_MIN_BET", 10)
            max_bet = getattr(config, "WC_MAX_BET", 5000)
            if amount < min_bet or amount > max_bet:
                return _bot.reply_to(message, f"❌ مبلغ باید بین {min_bet:,} و {max_bet:,} الماس باشد.")

            challenge_id = pending["challenge_id"]
            selected_option = pending["selected_option"]
            account_id = pending["account_id"]

            challenge = db.get_wc_challenge(challenge_id)
            if not challenge:
                _wc_pending_bet.pop(tg_id, None)
                return _bot.reply_to(message, "❌ چالش یافت نشد یا منقضی شده.")

            option_fa = {"team1": challenge["team1"], "team2": challenge["team2"], "draw": "مساوی"}.get(selected_option, selected_option)
            success, msg_txt = db.join_wc_challenge(challenge_id, account_id, tg_id, selected_option, amount)
            _wc_pending_bet.pop(tg_id, None)

            if success:
                balance = db.get_token_balance(account_id)
                _bot.reply_to(
                    message,
                    f"✅ <b>شرط ثبت شد!</b>\n\n"
                    f"⚽️ {challenge['team1']} vs {challenge['team2']}\n"
                    f"🎯 انتخاب: <b>{option_fa}</b>\n"
                    f"💎 مبلغ: <b>{amount:,} الماس</b>\n"
                    f"💰 موجودی باقی‌مانده: <b>{balance:,} الماس</b>\n\n"
                    f"🏆 در صورت برد، <b>{amount * 2:,} الماس</b> دریافت می‌کنید!"
                )
            else:
                _bot.reply_to(message, msg_txt)
        except Exception as e:
            print(f"❌ cmd_wc_join: {e}")
            _bot.reply_to(message, f"❌ خطا: {e}")

    # ── Callback قدیمی bet_wc_ (سازگاری) ────────────────────────────────────
    @_bot.callback_query_handler(func=lambda call: call.data.startswith("bet_wc_"))
    def callback_bet_wc(call):
        try:
            parts = call.data.split("_", 3)
            challenge_id = int(parts[2])
            team_choice = parts[3]
            challenge = db.get_wc_challenge(challenge_id)
            if not challenge or challenge["status"] != "pending":
                return _bot.answer_callback_query(call.id, "❌ این چالش فعال نیست.", show_alert=True)
            account = _get_account_cached(call.from_user.id)
            if not account:
                return _bot.answer_callback_query(call.id, "❌ ابتدا در پنل وب ثبت‌نام کنید.", show_alert=True)
            _wc_pending_bet[call.from_user.id] = {
                "challenge_id": challenge_id,
                "selected_option": team_choice,
                "account_id": account["id"],
            }
            _bot.answer_callback_query(call.id, f"✅ انتخاب ثبت شد! حالا مبلغ رو بنویس:\nشرکت [مبلغ]", show_alert=True)
        except Exception as e:
            print(f"❌ خطا در callback_bet_wc: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # /start
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(commands=["start"])
    def cmd_start(message):
        try:
            tg_id = message.from_user.id
            parts = message.text.strip().split()
            ref_code = parts[1] if len(parts) > 1 else None

            if ref_code and ref_code.startswith("ref_"):
                try:
                    referrer_id = int(ref_code[4:])
                    threading.Thread(target=_process_referral_async, args=(referrer_id, tg_id), daemon=True).start()
                except Exception:
                    pass

            is_member, missing = _check_membership_cached(tg_id)
            if not is_member:
                send_forced_channels_menu(message, missing)
                return

            account = _get_account_cached(tg_id)
            site_url = getattr(config, "SITE_URL", "")

            if not account:
                markup = types.InlineKeyboardMarkup()
                if site_url:
                    markup.add(types.InlineKeyboardButton("🌐 ورود به پنل وب", url=site_url))
                _bot.reply_to(message,
                    "👋 <b>سلام!</b>\n\n"
                    "برای استفاده از ربات:\n"
                    "1️⃣ در پنل وب ثبت‌نام کنید\n"
                    "2️⃣ حساب تلگرام را وصل کنید\n"
                    "3️⃣ دوباره /start بزنید",
                    reply_markup=markup if site_url else None)
                return

            # سلف رایگان برای کاربر جدید
            threading.Thread(target=_grant_free_trial, args=[account["id"], tg_id], daemon=True).start()

            stats = db.get_token_stats(account["id"])
            sub = db.get_subscription(account["id"])

            now_tehran = _now_tehran().strftime("%Y/%m/%d — %H:%M")

            # وضعیت اشتراک
            if sub:
                sub_exp = sub.get("expires_at")
                plan_fa = {"weekly": "هفتگی", "monthly": "ماهانه", "bimonthly": "دو ماهه", "free_trial": "رایگان"}.get(sub.get("plan", ""), sub.get("plan", ""))
                import datetime as _dt
                exp_dt = sub_exp
                if isinstance(exp_dt, str):
                    exp_dt = _dt.datetime.fromisoformat(exp_dt.replace("Z", "+00:00"))
                if exp_dt and exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=_dt.timezone.utc)
                is_active = exp_dt and exp_dt > _dt.datetime.now(_dt.timezone.utc)
                sub_status = (
                    f"✅ فعال — پلن {plan_fa}\n"
                    f"   📅 انقضا: {_fmt_tehran(sub_exp)}\n"
                    f"   ⏳ باقی‌مانده: {_remaining_str(sub_exp)}"
                ) if is_active else "❌ اشتراک ندارید"
            else:
                sub_status = "❌ اشتراک ندارید"

            if message.chat.type == 'private':
                markup = _owner_keyboard() if tg_id == OWNER_TG_ID else _user_keyboard()
            else:
                markup = None

            _bot.reply_to(
                message,
                f"👋 سلام <b>{account['username']}</b>!\n\n"
                f"🕐 وقت تهران: <b>{now_tehran}</b>\n\n"
                f"💎 موجودی الماس: <b>{stats['balance']}</b>\n"
                f"📊 کل دریافتی: <b>{stats['total_earned']}</b>\n\n"
                f"📦 اشتراک سلف:\n{sub_status}",
                reply_markup=markup
            )

            if message.chat.type == 'private':
                sponsors = getattr(config, 'SPONSORS', [])
                if sponsors:
                    sponsors_text = "🤝 <b>اسپانسرهای رسمی پروژه:</b>\n"
                    for sp in sponsors:
                        sponsors_text += f"🔸 @{sp['username']}\n"
                    sponsors_text += f"\n👑 <b>مالک و پشتیبانی:</b> @{config.OWNER_USERNAME}"
                    _bot.send_message(message.chat.id, sponsors_text)
        except Exception as e:
            print(f"❌ خطا در cmd_start: {e}")

    def _grant_free_trial(account_id: int, tg_id: int):
        """یک روز سلف رایگان برای کاربران جدید"""
        try:
            existing = db.get_subscription(account_id)
            if existing:
                return  # قبلاً اشتراک داشته
            expires = db.set_subscription(account_id, "free_trial", 1)
            if expires:
                exp_str = _fmt_tehran(expires)
                try:
                    _bot.send_message(
                        tg_id,
                        f"🎁 <b>یک روز سلف رایگان هدیه گرفتید!</b>\n\n"
                        f"⏰ انقضا: <b>{exp_str}</b> (وقت تهران)\n\n"
                        f"برای تمدید، از منوی 🛒 خرید استفاده کنید."
                    )
                except Exception:
                    pass
                # تایمر اطلاع‌رسانی انقضا
                threading.Timer(86400, _notify_subscription_expired, args=[account_id, tg_id]).start()
        except Exception as e:
            print(f"❌ _grant_free_trial: {e}")

    def _notify_subscription_expired(account_id: int, tg_id: int):
        """اطلاع‌رسانی پایان اشتراک"""
        try:
            sub = db.get_subscription(account_id)
            if not sub:
                return
            exp = sub.get("expires_at")
            if isinstance(exp, str):
                exp = datetime.datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=datetime.timezone.utc)
            if exp > datetime.datetime.now(datetime.timezone.utc):
                return  # هنوز فعاله
            site_url = getattr(config, "SITE_URL", "")
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🛒 تمدید اشتراک", callback_data="pur_sub_diamond"))
            if site_url:
                markup.add(types.InlineKeyboardButton("🌐 پنل وب", url=site_url))
            try:
                _bot.send_message(
                    tg_id,
                    "⏰ <b>اشتراک سلف شما به پایان رسید!</b>\n\n"
                    "برای ادامه استفاده از سلف‌بات، اشتراک خود را تمدید کنید. 👇",
                    reply_markup=markup
                )
            except Exception:
                pass
        except Exception as e:
            print(f"❌ _notify_subscription_expired: {e}")

    def _start_subscription_checker():
        """هر ۳۰ دقیقه اشتراک‌های نزدیک به انقضا رو چک می‌کنه"""
        def _checker():
            while True:
                try:
                    time.sleep(1800)  # 30 دقیقه
                    _check_expiring_subscriptions()
                except Exception as e:
                    print(f"❌ subscription checker: {e}")
        threading.Thread(target=_checker, daemon=True).start()

    def _check_expiring_subscriptions():
        try:
            import psycopg2
            from database_supabase import execute_query
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            soon = now_utc + datetime.timedelta(hours=2)
            rows = execute_query(
                "SELECT owner_id, expires_at FROM amel_subscriptions WHERE status IS DISTINCT FROM 'notified' AND expires_at BETWEEN %s AND %s",
                (now_utc, soon), fetch_all=True
            )
            for row in (rows or []):
                owner_id_val = row["owner_id"]
                tg_id = db.get_telegram_id_by_owner(owner_id_val)
                if not tg_id:
                    continue
                exp = row["expires_at"]
                remaining = _remaining_str(exp)
                try:
                    _bot.send_message(
                        tg_id,
                        f"⚠️ <b>اشتراک شما در حال انقضاست!</b>\n\n"
                        f"⏰ باقی‌مانده: <b>{remaining}</b>\n\n"
                        f"برای تمدید همین الان اقدام کنید 👇",
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("🛒 تمدید اشتراک", callback_data="pur_sub_diamond")
                        )
                    )
                    execute_query(
                        "UPDATE amel_subscriptions SET status='notified' WHERE owner_id=%s",
                        (owner_id_val,)
                    )
                except Exception:
                    pass
        except Exception as e:
            print(f"❌ _check_expiring_subscriptions: {e}")

    _start_subscription_checker()

    def _process_referral_async(referrer_id, tg_id):
        try:
            if db.process_referral(referrer_id, tg_id):
                referrer_tg = db.get_telegram_id_by_owner(referrer_id)
                if referrer_tg and _bot:
                    _bot.send_message(referrer_tg, 
                        f"🎉 یک نفر با لینک شما عضو شد!\n"
                        f"<b>+{config.REFERRAL_TOKENS} الماس</b> دریافت کردید 💎")
        except Exception as e:
            print(f"❌ خطا در رفرال: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Callback: بررسی عضویت
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.callback_query_handler(func=lambda call: call.data == "check_join")
    def callback_check_join(call):
        try:
            cache.invalidate(f"membership_{call.from_user.id}")
            is_member, missing = _check_membership_cached(call.from_user.id)
            if is_member:
                _bot.answer_callback_query(call.id, "عضویت تأیید شد! ✅")
                try: 
                    _bot.delete_message(call.message.chat.id, call.message.message_id)
                except: 
                    pass
                cmd_start(call.message)
            else:
                _bot.answer_callback_query(call.id, f"هنوز در {len(missing)} کانال عضو نشده‌اید! ❌", show_alert=True)
        except Exception as e:
            print(f"❌ خطا در callback_check_join: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # دکمه‌های منوی اصلی
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(func=lambda m: m.text == "💎 موجودی", chat_types=['private'])
    def cmd_balance(message):
        try:
            if not require_membership(message): 
                return
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())
            
            stats = db.get_token_stats(account["id"])
            ref_count = db.get_referral_count(account["id"])
            token_price = getattr(config, 'TOKEN_PRICE_TOMAN', 200)
            
            _bot.reply_to(message,
                f"💎 <b>موجودی الماس</b>\n\n"
                f"💰 فعلی: <b>{stats['balance']}</b>\n"
                f"📊 کل: <b>{stats['total_earned']}</b>\n"
                f"👥 رفرال: <b>{ref_count}</b> نفر\n"
                f"💵 قیمت هر الماس: <b>{token_price} تومان</b>",
                reply_markup=_owner_keyboard() if message.from_user.id == OWNER_TG_ID else _user_keyboard())
        except Exception as e:
            print(f"❌ خطا در cmd_balance: {e}")

    @_bot.message_handler(func=lambda m: m.text == "🎁 هدیه روزانه", chat_types=['private'])
    def cmd_daily(message):
        try:
            if not require_membership(message): 
                return
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())
            
            success, msg = db.claim_daily_token(account["id"])
            cache.invalidate(f"account_{message.from_user.id}")
            
            if success:
                stats = db.get_token_stats(account["id"])
                _bot.reply_to(message, f"{msg}\n\n💎 موجودی جدید: <b>{stats['balance']}</b>", reply_markup=_user_keyboard())
            else:
                _bot.reply_to(message, msg, reply_markup=_user_keyboard())
        except Exception as e:
            print(f"❌ خطا در cmd_daily: {e}")

    @_bot.message_handler(func=lambda m: m.text == "🔗 رفرال", chat_types=['private'])
    def cmd_referral(message):
        try:
            if not require_membership(message): 
                return
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())
            
            link = f"https://t.me/{BOT_USERNAME}?start=ref_{account['id']}"
            ref_count = db.get_referral_count(account["id"])
            token_price = getattr(config, 'TOKEN_PRICE_TOMAN', 200)
            referral_value = config.REFERRAL_TOKENS * token_price
            
            _bot.reply_to(message,
                f"🔗 <b>لینک رفرال شما:</b>\n<code>{link}</code>\n\n"
                f"👥 تعداد: <b>{ref_count}</b>\n"
                f"🎁 پاداش: <b>{config.REFERRAL_TOKENS} الماس</b> (معادل {referral_value} تومان)",
                reply_markup=_user_keyboard())
        except Exception as e:
            print(f"❌ خطا در cmd_referral: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # 🎯 سیستم ماموریت‌ها — عضویت در کانال‌ها برای دریافت جایزه
    # ══════════════════════════════════════════════════════════════════════════
    def _mission_keyboard(channels):
        markup = types.InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            ch_clean = ch.lstrip("@")
            markup.add(types.InlineKeyboardButton(f"🔗 عضویت در {ch}", url=f"https://t.me/{ch_clean}"))
        markup.add(types.InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_mission"))
        return markup

    def _check_mission_membership(user_id, channels):
        """بررسی واقعی عضویت کاربر در تمام کانال‌های ماموریت (جلوگیری از تقلب)."""
        missing = []
        for ch in channels:
            try:
                member = _bot.get_chat_member(ch, user_id)
                if member.status not in ('member', 'administrator', 'creator'):
                    missing.append(ch)
            except Exception:
                missing.append(ch)
        return len(missing) == 0, missing

    @_bot.message_handler(func=lambda m: m.text == "🎯 ماموریت‌ها", chat_types=['private'])
    def cmd_missions(message):
        try:
            if not require_membership(message):
                return
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())

            channels = db.get_mission_channels()
            reward = int(db.get_global_setting("mission_reward", str(getattr(config, "MISSION_DEFAULT_REWARD", 0))) or 0)

            if not channels:
                return _bot.reply_to(message, "📭 در حال حاضر ماموریت فعالی وجود ندارد.", reply_markup=_user_keyboard())

            if db.has_claimed_mission(account["id"]):
                return _bot.reply_to(message, "✅ شما قبلاً جایزهٔ این ماموریت را دریافت کرده‌اید.\n\n🔔 منتظر ماموریت‌های بعدی باشید!", reply_markup=_user_keyboard())

            channels_list = "\n".join([f"🔸 {ch}" for ch in channels])
            _bot.reply_to(message,
                f"🎯 <b>ماموریت ویژه!</b>\n\n"
                f"عضو کانال‌های زیر شو و <b>{reward} الماس</b> جایزه بگیر:\n\n"
                f"{channels_list}\n\n"
                f"👇 ابتدا عضو شو، سپس «بررسی عضویت» را بزن:",
                reply_markup=_mission_keyboard(channels))
        except Exception as e:
            print(f"❌ خطا در cmd_missions: {e}")

    @_bot.callback_query_handler(func=lambda call: call.data == "check_mission")
    def callback_check_mission(call):
        try:
            account = _get_account_cached(call.from_user.id)
            if not account:
                return _bot.answer_callback_query(call.id, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", show_alert=True)

            if db.has_claimed_mission(account["id"]):
                return _bot.answer_callback_query(call.id, "✅ شما قبلاً جایزه را دریافت کرده‌اید.", show_alert=True)

            channels = db.get_mission_channels()
            if not channels:
                return _bot.answer_callback_query(call.id, "📭 ماموریت فعالی وجود ندارد.", show_alert=True)

            is_member, missing = _check_mission_membership(call.from_user.id, channels)
            if not is_member:
                return _bot.answer_callback_query(call.id, "❌ شما هنوز ماموریت را کامل نکرده‌اید.", show_alert=True)

            reward = int(db.get_global_setting("mission_reward", str(getattr(config, "MISSION_DEFAULT_REWARD", 0))) or 0)
            success, msg = db.claim_mission_reward(account["id"], reward)
            cache.invalidate(f"account_{call.from_user.id}")
            _bot.answer_callback_query(call.id, "🎉 جایزه دریافت شد!" if success else "❌ خطا", show_alert=True)
            if success:
                _bot.send_message(call.message.chat.id, msg, reply_markup=_user_keyboard())
        except Exception as e:
            print(f"❌ خطا در callback_check_mission: {e}")
            try:
                _bot.answer_callback_query(call.id, "❌ خطا، دوباره تلاش کنید", show_alert=True)
            except:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # 🛒 سیستم خرید و اشتراک
    # ══════════════════════════════════════════════════════════════════════════

    # ── تعریف پلن‌ها ──────────────────────────────────────────────────────────
    MONTHLY_TOMAN   = 90_000
    PLANS = {
        "weekly":    {"fa": "هفتگی",    "days": 7,  "toman": MONTHLY_TOMAN // 4,  "diamonds": 100},
        "monthly":   {"fa": "ماهانه",   "days": 30, "toman": MONTHLY_TOMAN,        "diamonds": 360},
        "bimonthly": {"fa": "دو ماهه",  "days": 60, "toman": MONTHLY_TOMAN * 2,   "diamonds": 700},
    }
    DIAMOND_RATE    = 250   # هر الماس = ۲۵۰ تومان (۱۰۰ الماس = ۲۵,۰۰۰ تومان)
    DIAMOND_MIN_BUY = 100   # حداقل خرید الماس

    # وضعیت موقت کاربران برای خرید
    _purchase_states = {}  # tg_id -> {step, data}

    def _get_card_number():
        return db.get_global_setting("card_number", "----")

    def _purchase_main_keyboard():
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("💎 خرید اشتراک با الماس",   callback_data="pur_sub_diamond"),
            types.InlineKeyboardButton("💳 خرید اشتراک با کارت",    callback_data="pur_sub_card"),
            types.InlineKeyboardButton("🛍 خرید الماس",              callback_data="pur_buy_diamond"),
        )
        return markup

    def _plans_keyboard(prefix: str):
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, p in PLANS.items():
            markup.add(types.InlineKeyboardButton(
                f"{p['fa']} — {p['toman']:,} تومان / {p['diamonds']} الماس",
                callback_data=f"{prefix}_{key}"
            ))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_back"))
        return markup

    @_bot.message_handler(func=lambda m: m.text and m.text.strip() in ("🛒 خرید الماس", "🛒 خرید"), chat_types=['private'])
    def cmd_buy(message):
        try:
            if not require_membership(message):
                return
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "❌ ابتدا در پنل وب ثبت‌نام کنید.")
            balance = db.get_token_balance(account["id"])
            _bot.reply_to(message,
                f"🛒 <b>منوی خرید</b>\n\n"
                f"💎 موجودی فعلی شما: <b>{balance} الماس</b>\n\n"
                f"یکی از گزینه‌های زیر را انتخاب کنید:",
                reply_markup=_purchase_main_keyboard())
        except Exception as e:
            print(f"❌ خطا در cmd_buy: {e}")

    # ── Callback اصلی خرید ────────────────────────────────────────────────────
    @_bot.callback_query_handler(func=lambda call: call.data.startswith("pur_"))
    def callback_purchase(call):
        try:
            data = call.data
            tg_id = call.from_user.id
            account = _get_account_cached(tg_id)
            if not account:
                return _bot.answer_callback_query(call.id, "❌ ابتدا در پنل وب ثبت‌نام کنید.", show_alert=True)

            # ── بازگشت ──────────────────────────────────────────────────────
            if data == "pur_back":
                balance = db.get_token_balance(account["id"])
                _purchase_states.pop(tg_id, None)
                return _bot.edit_message_text(
                    f"🛒 <b>منوی خرید</b>\n\n💎 موجودی: <b>{balance} الماس</b>\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    reply_markup=_purchase_main_keyboard()
                )

            # ── اشتراک با الماس ─────────────────────────────────────────────
            elif data == "pur_sub_diamond":
                balance = db.get_token_balance(account["id"])
                text = (
                    f"💎 <b>خرید اشتراک با الماس</b>\n\n"
                    f"موجودی شما: <b>{balance} الماس</b>\n\n"
                    f"یک پلن را انتخاب کنید:"
                )
                _bot.edit_message_text(text, chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_plans_keyboard("pur_sdiam"))
                _bot.answer_callback_query(call.id)

            elif data.startswith("pur_sdiam_"):
                plan_key = data.split("_", 2)[2]
                plan = PLANS.get(plan_key)
                if not plan:
                    return _bot.answer_callback_query(call.id, "❌ پلن نامعتبر", show_alert=True)
                balance = db.get_token_balance(account["id"])
                cost = plan["diamonds"]
                if balance < cost:
                    need = cost - balance
                    return _bot.edit_message_text(
                        f"❌ <b>موجودی کافی نیست!</b>\n\n"
                        f"💎 موجودی: {balance} الماس\n"
                        f"💎 نیاز: {cost} الماس\n"
                        f"💎 کمبود: {need} الماس\n\n"
                        f"💡 برای کسب الماس:\n"
                        f"• دریافت هدیه روزانه 🎁\n"
                        f"• دعوت دوستان 🔗\n"
                        f"• خرید الماس 🛍",
                        chat_id=call.message.chat.id, message_id=call.message.message_id,
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("🛍 خرید الماس", callback_data="pur_buy_diamond"),
                            types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_sub_diamond")
                        )
                    )
                # کسر الماس و فعال‌سازی
                db.deduct_tokens(account["id"], cost)
                expires = db.set_subscription(account["id"], plan_key, plan["days"])
                exp_str = expires.strftime("%Y-%m-%d") if expires else "نامشخص"
                _bot.edit_message_text(
                    f"✅ <b>اشتراک {plan['fa']} فعال شد!</b>\n\n"
                    f"💎 {cost} الماس کسر شد\n"
                    f"📅 انقضا: <b>{exp_str}</b>",
                    chat_id=call.message.chat.id, message_id=call.message.message_id
                )
                _bot.answer_callback_query(call.id, f"✅ اشتراک {plan['fa']} فعال شد!", show_alert=True)

            # ── اشتراک با کارت ──────────────────────────────────────────────
            elif data == "pur_sub_card":
                _bot.edit_message_text(
                    "💳 <b>خرید اشتراک با کارت</b>\n\nیک پلن را انتخاب کنید:",
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    reply_markup=_plans_keyboard("pur_scard")
                )
                _bot.answer_callback_query(call.id)

            elif data.startswith("pur_scard_"):
                plan_key = data.split("_", 2)[2]
                plan = PLANS.get(plan_key)
                if not plan:
                    return _bot.answer_callback_query(call.id, "❌ پلن نامعتبر", show_alert=True)
                card = _get_card_number()
                payment_id = db.create_payment(
                    account["id"], tg_id, "subscription",
                    plan=plan_key, toman_amount=plan["toman"]
                )
                _purchase_states[tg_id] = {"step": "waiting_receipt_sub", "payment_id": payment_id}
                _bot.edit_message_text(
                    f"💳 <b>پرداخت اشتراک {plan['fa']}</b>\n\n"
                    f"💰 مبلغ: <b>{plan['toman']:,} تومان</b>\n"
                    f"💳 شماره کارت: <code>{card}</code>\n"
                    f"👤 به نام: <b>غفاری</b>\n\n"
                    f"بعد از واریز، تصویر رسید را ارسال کنید 👇",
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_sub_card")
                    )
                )
                _bot.answer_callback_query(call.id)

            # ── خرید الماس ──────────────────────────────────────────────────
            elif data == "pur_buy_diamond":
                card = _get_card_number()
                _purchase_states[tg_id] = {"step": "waiting_diamond_amount"}
                _bot.edit_message_text(
                    f"🛍 <b>خرید الماس</b>\n\n"
                    f"💎 نرخ: هر ۱۰۰ الماس = <b>{100 * DIAMOND_RATE:,} تومان</b>\n"
                    f"📌 حداقل خرید: <b>{DIAMOND_MIN_BUY} الماس</b>\n\n"
                    f"چه تعداد الماس می‌خوای؟ (عدد بنویس)\n"
                    f"مثال: <code>200</code>",
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_back")
                    )
                )
                _bot.answer_callback_query(call.id)

            # ── تأیید/رد پرداخت توسط ادمین ─────────────────────────────────
            elif data.startswith("pur_approve_") or data.startswith("pur_reject_"):
                if tg_id != OWNER_TG_ID:
                    return _bot.answer_callback_query(call.id, "❌ فقط مالک دسترسی دارد", show_alert=True)
                action = "approve" if data.startswith("pur_approve_") else "reject"
                payment_id = int(data.split("_")[2])
                payment = db.get_payment(payment_id)
                if not payment:
                    return _bot.answer_callback_query(call.id, "❌ پرداخت یافت نشد", show_alert=True)
                if payment["status"] != "pending":
                    return _bot.answer_callback_query(call.id, "⚠️ این پرداخت قبلاً پردازش شده", show_alert=True)

                if action == "approve":
                    db.update_payment(payment_id, status="approved")
                    user_account = db.get_account(payment["owner_id"])

                    if payment["type"] == "subscription":
                        plan_key = payment["plan"]
                        plan = PLANS.get(plan_key, {})
                        expires = db.set_subscription(payment["owner_id"], plan_key, plan.get("days", 30))
                        exp_str = expires.strftime("%Y-%m-%d") if expires else "نامشخص"
                        try:
                            _bot.send_message(
                                payment["tg_id"],
                                f"✅ <b>پرداخت تأیید شد!</b>\n\n"
                                f"🎉 اشتراک {plan.get('fa','')} شما فعال شد\n"
                                f"📅 انقضا: <b>{exp_str}</b>"
                            )
                        except Exception: pass

                    elif payment["type"] == "diamond":
                        amount = payment["diamond_amount"]
                        db.add_tokens(payment["owner_id"], amount)
                        try:
                            _bot.send_message(
                                payment["tg_id"],
                                f"✅ <b>پرداخت تأیید شد!</b>\n\n"
                                f"💎 <b>{amount} الماس</b> به حسابتان اضافه شد!"
                            )
                        except Exception: pass

                    _bot.edit_message_reply_markup(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("✅ تأیید شد", callback_data="noop")
                        )
                    )
                    _bot.answer_callback_query(call.id, "✅ پرداخت تأیید شد!", show_alert=True)

                else:  # reject
                    db.update_payment(payment_id, status="rejected")
                    try:
                        _bot.send_message(
                            payment["tg_id"],
                            "❌ <b>پرداخت شما رد شد.</b>\n\nلطفاً با پشتیبانی تماس بگیرید."
                        )
                    except Exception: pass
                    _bot.edit_message_reply_markup(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=types.InlineKeyboardMarkup().add(
                            types.InlineKeyboardButton("❌ رد شد", callback_data="noop")
                        )
                    )
                    _bot.answer_callback_query(call.id, "❌ پرداخت رد شد", show_alert=True)

            elif data == "noop":
                _bot.answer_callback_query(call.id)

        except Exception as e:
            print(f"❌ خطا در callback_purchase: {e}")
            _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:80]}", show_alert=True)

    # ── دریافت پیام‌های مرتبط با خرید (مبلغ الماس + رسید) ───────────────────
    @_bot.message_handler(
        func=lambda m: m.from_user.id in _purchase_states and m.chat.type == "private",
        content_types=["text", "photo", "document"]
    )
    def handle_purchase_state(message):
        try:
            tg_id = message.from_user.id
            state = _purchase_states.get(tg_id, {})
            step = state.get("step")
            account = _get_account_cached(tg_id)
            if not account:
                return

            # ── کاربر تعداد الماس رو نوشت ───────────────────────────────
            if step == "waiting_diamond_amount":
                try:
                    amount = int(message.text.strip())
                except (ValueError, AttributeError):
                    return _bot.reply_to(message, "❌ لطفاً یک عدد معتبر وارد کنید.")
                if amount < DIAMOND_MIN_BUY:
                    return _bot.reply_to(message, f"❌ حداقل {DIAMOND_MIN_BUY} الماس باید خرید.")
                toman = amount * DIAMOND_RATE
                card = _get_card_number()
                payment_id = db.create_payment(
                    account["id"], tg_id, "diamond",
                    diamond_amount=amount, toman_amount=toman
                )
                _purchase_states[tg_id] = {"step": "waiting_receipt_diamond", "payment_id": payment_id}
                _bot.reply_to(message,
                    f"🛍 <b>خرید {amount} الماس</b>\n\n"
                    f"💰 مبلغ: <b>{toman:,} تومان</b>\n"
                    f"💳 شماره کارت: <code>{card}</code>\n"
                    f"👤 به نام: <b>غفاری</b>\n\n"
                    f"بعد از واریز، تصویر رسید را ارسال کنید 👇",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("❌ لغو", callback_data="pur_back")
                    )
                )

            # ── کاربر رسید فرستاد ────────────────────────────────────────
            elif step in ("waiting_receipt_sub", "waiting_receipt_diamond"):
                payment_id = state.get("payment_id")
                if not payment_id:
                    return

                # دریافت file_id
                file_id = None
                if message.photo:
                    file_id = message.photo[-1].file_id
                elif message.document:
                    file_id = message.document.file_id
                else:
                    return _bot.reply_to(message, "❌ لطفاً تصویر رسید را ارسال کنید.")

                db.update_payment(payment_id, receipt_file_id=file_id)
                payment = db.get_payment(payment_id)

                # ارسال به ادمین
                username = message.from_user.username
                user_display = f"@{username}" if username else str(tg_id)

                if step == "waiting_receipt_sub":
                    plan = PLANS.get(payment.get("plan", ""), {})
                    desc = f"اشتراک {plan.get('fa', '')} — {payment.get('toman_amount', 0):,} تومان"
                else:
                    desc = f"خرید {payment.get('diamond_amount', 0)} الماس — {payment.get('toman_amount', 0):,} تومان"

                admin_text = (
                    f"🧾 <b>رسید جدید</b>\n\n"
                    f"👤 کاربر: {user_display}\n"
                    f"🆔 تلگرام: <code>{tg_id}</code>\n"
                    f"📦 نوع: {desc}\n"
                    f"🔢 شناسه پرداخت: <code>{payment_id}</code>"
                )
                admin_markup = types.InlineKeyboardMarkup(row_width=2)
                admin_markup.add(
                    types.InlineKeyboardButton("✅ تأیید", callback_data=f"pur_approve_{payment_id}"),
                    types.InlineKeyboardButton("❌ رد",   callback_data=f"pur_reject_{payment_id}")
                )
                try:
                    admin_msg = _bot.send_photo(
                        OWNER_TG_ID, file_id,
                        caption=admin_text,
                        reply_markup=admin_markup
                    )
                    db.update_payment(payment_id, admin_msg_id=admin_msg.message_id)
                except Exception as e:
                    print(f"❌ ارسال رسید به ادمین: {e}")

                _purchase_states.pop(tg_id, None)
                _bot.reply_to(message,
                    "✅ <b>رسید دریافت شد!</b>\n\n"
                    "⏳ پس از تأیید توسط ادمین، اشتراک/الماس شما فعال می‌شود.\n"
                    "معمولاً کمتر از ۳۰ دقیقه طول می‌کشد."
                )

        except Exception as e:
            print(f"❌ خطا در handle_purchase_state: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # 📢 پنل مدیریت مالک
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(func=lambda m: m.text == "📢 مدیریت", chat_types=['private'])
    def cmd_admin_panel(message):
        if message.from_user.id != OWNER_TG_ID:
            return
        _bot.reply_to(message, 
            "📢 <b>پنل مدیریت مالک</b>\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
            reply_markup=_admin_panel_keyboard())

    # ══════════════════════════════════════════════════════════════════════════
    # 🎯 Callback handler پنل مدیریت
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.callback_query_handler(func=lambda call: call.data.startswith("admin_") or call.data.startswith("rmch_") or call.data.startswith("wcwin_") or call.data.startswith("wc_") or call.data.startswith("rmmc_") or call.data == "addch_prompt")
    def callback_admin(call):
        if call.from_user.id != OWNER_TG_ID:
            return _bot.answer_callback_query(call.id, "❌ فقط مالک دسترسی دارد", show_alert=True)
        
        try:
            data = call.data
            
            if data == "admin_panel" or data == "admin_back":
                _bot.edit_message_text(
                    "📢 <b>پنل مدیریت مالک</b>\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=_admin_panel_keyboard()
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data == "admin_channels":
                channels = db.get_forced_channels()
                markup = types.InlineKeyboardMarkup(row_width=1)
                if channels:
                    text = "📢 <b>چنل‌های اجباری فعلی:</b>\n\n"
                    for ch in channels:
                        text += f"🔸 <code>{ch}</code>\n"
                        ch_clean = ch.lstrip("@")
                        markup.add(types.InlineKeyboardButton(f"❌ حذف {ch}", callback_data=f"rmch_{ch_clean}"))
                else:
                    text = "📋 لیست چنل‌ها خالی است.\n\n"
                text += "\nبرای افزودن چنل جدید از دکمه زیر استفاده کنید:"
                markup.add(types.InlineKeyboardButton("➕ افزودن چنل جدید", callback_data="addch_prompt"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                _bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data.startswith("rmch_"):
                ch = data[5:]
                if not ch.startswith("@"):
                    ch = "@" + ch
                if db.remove_forced_channel(ch):
                    cache.invalidate("membership_")
                    _bot.answer_callback_query(call.id, f"✅ چنل {ch} حذف شد")
                    call.data = "admin_channels"
                    callback_admin(call)
                else:
                    _bot.answer_callback_query(call.id, "❌ خطا در حذف")
                return
            
            elif data == "addch_prompt":
                _owner_states[call.from_user.id] = {"state": "waiting_channel"}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_panel"))
                _bot.edit_message_text(
                    "📝 آیدی چنل را ارسال کنید (با @ شروع شود):\n\nمثال: <code>@mychannel</code>",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data == "admin_users":
                accounts = db.get_all_accounts()
                if not accounts:
                    text = "هیچ کاربری ثبت نشده."
                else:
                    import datetime as _dt
                    now_utc = _dt.datetime.now(_dt.timezone.utc)
                    lines = [f"👥 <b>کاربران ({len(accounts)} نفر):</b>\n\n"]
                    for acc in accounts[:30]:
                        bal = db.get_token_balance(acc["id"])
                        expiry = acc.get("plan_expiry")
                        if expiry:
                            if isinstance(expiry, str):
                                try:
                                    expiry = _dt.datetime.fromisoformat(expiry.replace("Z", "+00:00"))
                                except Exception:
                                    expiry = None
                        if expiry:
                            if expiry.tzinfo is None:
                                expiry = expiry.replace(tzinfo=_dt.timezone.utc)
                            remaining = expiry - now_utc
                            if remaining.total_seconds() > 0:
                                days = int(remaining.total_seconds() // 86400)
                                hrs = int((remaining.total_seconds() % 86400) // 3600)
                                plan_txt = f"✅ فعال ({days}ر {hrs}س مانده)"
                            else:
                                plan_txt = "🔴 منقضی"
                        else:
                            plan_txt = "♾️ نامحدود"
                        lines.append(f"• <b>{acc['username']}</b> — 💎{bal} — {plan_txt}")
                    text = "\n".join(lines)
                    if len(accounts) > 30:
                        text += f"\n\n... و {len(accounts)-30} کاربر دیگر"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                _bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data == "admin_wc":
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(types.InlineKeyboardButton("➕ ایجاد چالش جدید", callback_data="wc_new"))
                markup.add(types.InlineKeyboardButton("📋 چالش‌های فعال", callback_data="wc_list"))
                markup.add(types.InlineKeyboardButton("👥 شرکت‌کنندگان", callback_data="wc_participants"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                _bot.edit_message_text(
                    "🏆 <b>مدیریت چالش‌های جام جهانی</b>\n\nیک گزینه را انتخاب کنید:",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return

            elif data == "wc_participants":
                participants = db.get_all_wc_participants(50)
                total = db.get_wc_participant_count()
                if not participants:
                    text = "📭 هنوز هیچ شرکت‌کننده‌ای ثبت نشده."
                else:
                    text = f"👥 <b>شرکت‌کنندگان جام جهانی</b> (کل: {total} — {len(participants)} مورد آخر)\n\n"
                    for p in participants:
                        uname = f"@{p['username']}" if p.get('username') else "—"
                        match_label = f"{p.get('team1','?')} vs {p.get('team2','?')}" if p.get('team1') else f"چالش #{p.get('challenge_id','?')}"
                        text += (
                            f"🔸 <b>{uname}</b> (ID: <code>{p['user_tg_id']}</code>)\n"
                            f"   🆚 {match_label} → {p['selected_option']} | 💎{p['amount']}\n"
                            f"   🕐 {_fmt_tehran(p['created_at'])}\n\n"
                        )
                    if len(text) > 3800:
                        text = text[:3800] + "\n…(فهرست کوتاه شد)"
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_wc"))
                _bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data == "wc_new":
                _owner_states[call.from_user.id] = {"state": "wc_team1", "data": {}}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_wc"))
                _bot.edit_message_text(
                    "🏆 <b>ایجاد چالش جدید</b>\n\n"
                    "📝 مرحله ۱ از ۴:\nنام <b>تیم اول</b> را ارسال کنید:\n\nمثال: <code>ایران</code>",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data == "wc_list":
                challenges = db.get_active_challenges()
                if not challenges:
                    text = "📋 هیچ چالش فعالی وجود ندارد."
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_wc"))
                else:
                    text = "🏆 <b>چالش‌های فعال:</b>\n\n"
                    markup = types.InlineKeyboardMarkup(row_width=2)
                    for c in challenges:
                        text += f"<b>ID {c['id']}:</b> {c['team1']} vs {c['team2']}\n"
                        text += f"⏰ {c['match_time']} | 💎 {c['bet_amount']}\n\n"
                        markup.add(
                            types.InlineKeyboardButton(f"✅ {c['team1']}", callback_data=f"wcwin_{c['id']}_{c['team1']}"),
                            types.InlineKeyboardButton(f"✅ {c['team2']}", callback_data=f"wcwin_{c['id']}_{c['team2']}")
                        )
                    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_wc"))
                _bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data.startswith("wcwin_"):
                parts = data.split("_", 2)
                challenge_id = int(parts[1])
                winner_team = parts[2]
                db.set_challenge_winner(challenge_id, winner_team)
                success, results = db.settle_challenge_bets(challenge_id)
                if success:
                    won_count = sum(1 for r in results if r["result"] == "won")
                    lost_count = sum(1 for r in results if r["result"] == "lost")
                    _bot.answer_callback_query(call.id, f"✅ برنده: {winner_team}\n🏆 {won_count} برنده | ❌ {lost_count} بازنده", show_alert=True)
                    for r in results:
                        if r["result"] == "won":
                            try:
                                _bot.send_message(r["user_tg_id"], f"🎉 تبریک! شرط شما درست بود.\n💎 <b>{r['amount']} الماس</b> دریافت کردید.")
                            except: 
                                pass
                else:
                    _bot.answer_callback_query(call.id, f"❌ خطا: {results}", show_alert=True)
                return
            
            elif data == "admin_today_games":
                _bot.answer_callback_query(call.id, "⏳ در حال دریافت بازی‌های امروز...")
                try:
                    today_matches = _wc_get_today_matches()
                except Exception as e:
                    today_matches = None
                    print(f"❌ خطا در دریافت بازی‌های امروز: {e}")

                if today_matches is None:
                    text = "❌ خطا در ارتباط با Football API.\nلاگ سرور را بررسی کنید."
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                    try:
                        _bot.edit_message_text(text, chat_id=call.message.chat.id,
                            message_id=call.message.message_id, reply_markup=markup)
                    except Exception:
                        _bot.send_message(call.message.chat.id, text, reply_markup=markup)
                    return

                if not getattr(config, "FOOTBALL_API_KEY", ""):
                    text = "⚠️ FOOTBALL_API_KEY تنظیم نشده است."
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                    _bot.edit_message_text(text, chat_id=call.message.chat.id,
                        message_id=call.message.message_id, reply_markup=markup)
                    return

                if not today_matches:
                    text = "📭 امروز بازی‌ای ثبت نشده."
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                    _bot.edit_message_text(text, chat_id=call.message.chat.id,
                        message_id=call.message.message_id, reply_markup=markup)
                    return

                # ساخت لیست بازی‌ها با دکمه ارسال برای هر کدام
                status_fa = {
                    "SCHEDULED": "⏳", "TIMED": "⏳",
                    "LIVE": "🔴", "IN_PLAY": "🔴", "PAUSED": "⏸️",
                    "FINISHED": "✅", "POSTPONED": "📌",
                    "SUSPENDED": "⛔️", "CANCELLED": "❌",
                }
                lines = ["📅 <b>بازی‌های امروز — جام جهانی</b>\n"]
                markup = types.InlineKeyboardMarkup(row_width=1)

                for m in today_matches:
                    match_id = str(m.get("id", ""))
                    home = (m.get("homeTeam", {}).get("shortName") or
                            m.get("homeTeam", {}).get("name") or "؟")
                    away = (m.get("awayTeam", {}).get("shortName") or
                            m.get("awayTeam", {}).get("name") or "؟")
                    st = status_fa.get(m.get("status", ""), "❓")
                    utc_date = m.get("utcDate", "")
                    time_str = utc_date
                    try:
                        dt = datetime.datetime.strptime(utc_date, "%Y-%m-%dT%H:%M:%SZ")
                        time_str = _wc_utc_to_iran(dt).strftime("%H:%M")
                    except Exception:
                        pass

                    # نشون می‌ده چالش قبلاً ساخته شده یا نه
                    already = db.wc_challenge_exists(match_id)
                    sent_icon = "📤" if already else "📨"

                    lines.append(f"{st} <b>{home}</b> vs <b>{away}</b> — ⏰{time_str}")
                    markup.add(
                        types.InlineKeyboardButton(
                            f"{sent_icon} ارسال چالش: {home} vs {away}",
                            callback_data=f"wc_sendnow_{match_id}"
                        )
                    )

                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                text = "\n".join(lines)

                try:
                    _bot.edit_message_text(text, chat_id=call.message.chat.id,
                        message_id=call.message.message_id, reply_markup=markup)
                except Exception:
                    _bot.send_message(call.message.chat.id, text, reply_markup=markup)
                return

            elif data.startswith("wc_sendnow_"):
                # ادمین دستی روی دکمه ارسال چالش زد
                match_id = data[len("wc_sendnow_"):]
                _bot.answer_callback_query(call.id, "⏳ در حال ارسال چالش...")
                try:
                    today_matches = _wc_get_today_matches()
                    target = next((m for m in today_matches if str(m.get("id")) == match_id), None)
                    if not target:
                        return _bot.answer_callback_query(call.id, "❌ بازی یافت نشد", show_alert=True)

                    home = (target.get("homeTeam", {}).get("shortName") or
                            target.get("homeTeam", {}).get("name") or "؟")
                    away = (target.get("awayTeam", {}).get("shortName") or
                            target.get("awayTeam", {}).get("name") or "؟")

                    if not home.strip() or not away.strip():
                        return _bot.answer_callback_query(call.id, "❌ نام تیم‌ها هنوز مشخص نیست", show_alert=True)

                    utc_date = target.get("utcDate", "")
                    try:
                        dt = datetime.datetime.strptime(utc_date, "%Y-%m-%dT%H:%M:%SZ")
                        match_time_str = _wc_utc_to_iran(dt).strftime("%Y/%m/%d — %H:%M") + " (تهران)"
                    except Exception:
                        dt = utc_date
                        match_time_str = utc_date

                    # اگه قبلاً ساخته شده فقط دوباره بفرسته
                    if db.wc_challenge_exists(match_id):
                        # چالش موجوده — فقط مجدد به کانال بفرست
                        from database_supabase import execute_query
                        row = execute_query(
                            "SELECT * FROM worldcup_challenges WHERE match_id=%s",
                            (match_id,), fetch_one=True
                        )
                        if row:
                            _wc_send_challenge_to_channel(row["id"], home, away, match_time_str)
                            _bot.answer_callback_query(call.id, "✅ چالش مجدداً ارسال شد!", show_alert=True)
                            return

                    challenge_id = db.create_wc_challenge(match_id, home, away, dt)
                    if challenge_id:
                        _wc_send_challenge_to_channel(challenge_id, home, away, match_time_str)
                        _bot.answer_callback_query(call.id, f"✅ چالش {home} vs {away} ارسال شد!", show_alert=True)
                    else:
                        _bot.answer_callback_query(call.id, "❌ خطا در ساخت چالش", show_alert=True)
                except Exception as e:
                    print(f"❌ wc_sendnow: {e}")
                    _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:80]}", show_alert=True)
                return
            
            elif data == "admin_transfer":
                _owner_states[call.from_user.id] = {"state": "transfer_user", "data": {}}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_panel"))
                _bot.edit_message_text(
                    "💎 <b>انتقال الماس (از طرف سیستم)</b>\n\n"
                    "📝 یوزرنیم کاربر مقصد را ارسال کنید:\n\nمثال: <code>ali</code>",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return
            
            elif data == "admin_give":
                _owner_states[call.from_user.id] = {"state": "give_user", "data": {}}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_panel"))
                _bot.edit_message_text(
                    "💰 <b>دادن الماس به کاربر</b>\n\n"
                    "📝 یوزرنیم کاربر را ارسال کنید:\n\nمثال: <code>ali</code>",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return

            elif data == "admin_set_card":
                cur_card = db.get_global_setting("card_number", "تنظیم نشده")
                _owner_states[call.from_user.id] = {"state": "set_card"}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_panel"))
                _bot.edit_message_text(
                    f"💳 <b>تنظیم شماره کارت</b>\n\n"
                    f"کارت فعلی: <code>{cur_card}</code>\n\n"
                    f"شماره کارت جدید را ارسال کنید:",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return

            elif data == "admin_payments":
                payments = db.get_pending_payments()
                if not payments:
                    _bot.answer_callback_query(call.id, "✅ هیچ پرداخت معلقی وجود ندارد", show_alert=True)
                    return
                lines = [f"🧾 <b>پرداخت‌های معلق ({len(payments)} مورد)</b>\n"]
                for p in payments[:10]:
                    ptype = "اشتراک" if p["type"] == "subscription" else "الماس"
                    lines.append(f"• ID {p['id']} — {ptype} — {p.get('toman_amount',0):,} تومان")
                _bot.answer_callback_query(call.id)
                _bot.send_message(call.message.chat.id, "\n".join(lines))
                return

            # ══════════════════════════════════════════════════════════════════
            # 📢 پیام عمومی (Broadcast)
            # ══════════════════════════════════════════════════════════════════
            elif data == "admin_broadcast":
                _owner_states[call.from_user.id] = {"state": "broadcast_wait"}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_panel"))
                _bot.edit_message_text(
                    "📢 <b>پیام عمومی به همهٔ کاربران</b>\n\n"
                    "پیام خود را ارسال کنید (متن ساده، متن با لینک، یا عکس همراه با کپشن).\n"
                    "می‌توانید از تگ‌های HTML مثل <code>&lt;a href=\"https://...\"&gt;متن&lt;/a&gt;</code> هم استفاده کنید.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return

            # ══════════════════════════════════════════════════════════════════
            # 🎯 مدیریت ماموریت‌ها
            # ══════════════════════════════════════════════════════════════════
            elif data == "admin_missions":
                channels = db.get_mission_channels()
                reward = db.get_global_setting("mission_reward", str(getattr(config, "MISSION_DEFAULT_REWARD", 0)))
                claim_count = db.get_mission_claim_count()
                markup = types.InlineKeyboardMarkup(row_width=1)
                if channels:
                    text = f"🎯 <b>کانال‌های ماموریت فعلی</b> (جایزه: {reward} الماس | {claim_count} نفر دریافت کرده‌اند):\n\n"
                    for ch in channels:
                        text += f"🔸 <code>{ch}</code>\n"
                        ch_clean = ch.lstrip("@")
                        markup.add(types.InlineKeyboardButton(f"❌ حذف {ch}", callback_data=f"rmmc_{ch_clean}"))
                else:
                    text = "📋 هیچ کانال ماموریتی تنظیم نشده.\n\n"
                text += "\nاز دکمه‌های زیر استفاده کنید:"
                markup.add(types.InlineKeyboardButton("➕ افزودن کانال", callback_data="admin_missions_add"))
                markup.add(types.InlineKeyboardButton("💎 تنظیم جایزه", callback_data="admin_missions_setreward"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                _bot.edit_message_text(
                    text,
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return

            elif data == "admin_missions_add":
                _owner_states[call.from_user.id] = {"state": "waiting_mission_channel"}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_missions"))
                _bot.edit_message_text(
                    "📝 آیدی کانال ماموریت را ارسال کنید (با @ شروع شود):\n\nمثال: <code>@mychannel</code>\n\n"
                    "⚠️ ربات باید عضو یا ادمین این کانال باشد تا بتواند عضویت را بررسی کند.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return

            elif data == "admin_missions_setreward":
                cur_reward = db.get_global_setting("mission_reward", str(getattr(config, "MISSION_DEFAULT_REWARD", 0)))
                _owner_states[call.from_user.id] = {"state": "waiting_mission_reward"}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_missions"))
                _bot.edit_message_text(
                    f"💎 <b>تنظیم جایزهٔ ماموریت</b>\n\n"
                    f"جایزهٔ فعلی: <b>{cur_reward} الماس</b>\n\n"
                    f"مقدار جدید (عدد الماس) را ارسال کنید:",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
                return

            elif data.startswith("rmmc_"):
                ch = data[5:]
                if not ch.startswith("@"):
                    ch = "@" + ch
                if db.remove_mission_channel(ch):
                    _bot.answer_callback_query(call.id, f"✅ کانال {ch} حذف شد")
                else:
                    _bot.answer_callback_query(call.id, "❌ خطا در حذف")
                call.data = "admin_missions"
                callback_admin(call)
                return

            else:
                _bot.answer_callback_query(call.id, "❌ گزینه نامعتبر")
        
        except Exception as e:
            print(f"❌ خطا در callback_admin: {e}")
            try:
                _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:100]}", show_alert=True)
            except: 
                pass

    # ══════════════════════════════════════════════════════════════════════════
    # 📨 State handler
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(func=lambda m: m.from_user.id == OWNER_TG_ID and m.from_user.id in _owner_states, content_types=['text', 'photo'], chat_types=['private'])
    def handle_owner_state(message):
        try:
            state_data = _owner_states[message.from_user.id]
            state = state_data["state"]

            # ─── 📢 پیام عمومی: متن یا عکس می‌تواند باشد ─────────────────────────
            if state == "broadcast_wait":
                _owner_states.pop(message.from_user.id, None)
                photo_id = message.photo[-1].file_id if message.content_type == "photo" else None
                caption = (message.caption if message.content_type == "photo" else message.text) or ""
                if not caption and not photo_id:
                    return _bot.reply_to(message, "❌ پیام خالی است.", reply_markup=_owner_keyboard())

                ids = db.get_all_telegram_ids()
                _bot.reply_to(message, f"📤 شروع ارسال پیام عمومی به <b>{len(ids)}</b> کاربر...", reply_markup=_owner_keyboard())

                def _do_broadcast():
                    sent, failed = 0, 0
                    delay = float(getattr(config, "BROADCAST_DELAY_SECONDS", 0.05))
                    for uid in ids:
                        try:
                            if photo_id:
                                _bot.send_photo(uid, photo_id, caption=caption, parse_mode="HTML")
                            else:
                                _bot.send_message(uid, caption, parse_mode="HTML", disable_web_page_preview=False)
                            sent += 1
                        except Exception:
                            failed += 1
                        time.sleep(delay)
                    try:
                        _bot.send_message(
                            OWNER_TG_ID,
                            f"✅ پیام عمومی ارسال شد!\n\n📨 موفق: <b>{sent}</b>\n❌ ناموفق: <b>{failed}</b>",
                            reply_markup=_owner_keyboard()
                        )
                    except Exception:
                        pass

                threading.Thread(target=_do_broadcast, daemon=True).start()
                return

            # برای بقیهٔ state ها فقط متن قابل قبول است
            if message.content_type != "text":
                return _bot.reply_to(message, "❌ لطفاً متن ارسال کنید.")
            text = message.text.strip()
            
            if state == "waiting_channel":
                if not text.startswith("@"):
                    text = "@" + text
                if db.add_forced_channel(text):
                    cache.invalidate("membership_")
                    _bot.reply_to(message, f"✅ چنل <b>{text}</b> اضافه شد.", reply_markup=_owner_keyboard())
                else:
                    _bot.reply_to(message, f"⚠️ خطا یا تکراری است.", reply_markup=_owner_keyboard())
                _owner_states.pop(message.from_user.id, None)
            
            elif state == "wc_team1":
                state_data["data"]["team1"] = text
                state_data["state"] = "wc_team2"
                _bot.reply_to(message, f"✅ تیم اول: <b>{text}</b>\n\n📝 مرحله  از ۴:\nنام <b>تیم دوم</b> را ارسال کنید:")
            
            elif state == "wc_team2":
                state_data["data"]["team2"] = text
                state_data["state"] = "wc_time"
                _bot.reply_to(message, f"✅ تیم دوم: <b>{text}</b>\n\n📝 مرحله  از ۴:\n ساعت بازی را ارسال کنید:\n\nمثال: <code>20:30</code>")
            
            elif state == "wc_time":
                state_data["data"]["time"] = text
                state_data["state"] = "wc_bet"
                _bot.reply_to(message, f"✅ ساعت: <b>{text}</b>\n\n📝 مرحله ۴ از ۴:\n💎 مبلغ شرط (الماس) را ارسال کنید:\n\nمثال: <code>10</code>")
            
            elif state == "wc_bet":
                try:
                    bet_amount = int(text)
                except:
                    return _bot.reply_to(message, "❌ مبلغ باید عدد باشد. دوباره تلاش کنید:")
                
                data = state_data["data"]
                challenge_id = db.create_world_cup_challenge(data["team1"], data["team2"], data["time"], bet_amount)
                
                group = getattr(config, 'WORLD_CUP_GROUP', '@amelselfgap')
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    types.InlineKeyboardButton(f"🔵 {data['team1']}", callback_data=f"bet_wc_{challenge_id}_{data['team1']}"),
                    types.InlineKeyboardButton(f"🔴 {data['team2']}", callback_data=f"bet_wc_{challenge_id}_{data['team2']}")
                )
                
                try:
                    msg = _bot.send_message(group,
                        f"⚽️ <b>چالش جام جهانی!</b>\n\n"
                        f"🆚 <b>{data['team1']}</b> در برابر <b>{data['team2']}</b>\n"
                        f"⏰ ساعت: <b>{data['time']}</b>\n"
                        f"💎 مبلغ شرط: <b>{bet_amount} الماس</b>\n\n"
                        f"کدام تیم برنده می‌شود؟ شرط ببندید!",
                        reply_markup=markup)
                    db.update_challenge_message(challenge_id, msg.message_id, msg.chat.id)
                    _bot.reply_to(message, 
                        f"✅ چالش با موفقیت ایجاد شد!\n\n"
                        f"🆚 {data['team1']} vs {data['team2']}\n"
                        f"⏰ {data['time']} | 💎 {bet_amount}\n"
                        f"📢 ID چالش: <code>{challenge_id}</code>",
                        reply_markup=_owner_keyboard())
                except Exception as e:
                    _bot.reply_to(message, f"❌ خطا در ارسال به گروه: {e}\nمطمئن شوید ربات در {group} ادمین است.", reply_markup=_owner_keyboard())
                
                _owner_states.pop(message.from_user.id, None)
            
            elif state == "transfer_user":
                state_data["data"]["username"] = text.lstrip("@")
                state_data["state"] = "transfer_amount"
                _bot.reply_to(message, f"📝 کاربر: <b>{text}</b>\n\n💎 مبلغ الماس را ارسال کنید:")
            
            elif state == "transfer_amount":
                try:
                    amount = int(text)
                except:
                    return _bot.reply_to(message, "❌ مبلغ باید عدد باشد:")
                
                username = state_data["data"]["username"]
                to_account = db.get_account_by_username(username)
                if not to_account:
                    _bot.reply_to(message, f"❌ کاربر '{username}' یافت نشد.", reply_markup=_owner_keyboard())
                    _owner_states.pop(message.from_user.id, None)
                    return
                
                db.add_tokens(to_account["id"], amount)
                new_balance = db.get_token_balance(to_account["id"])
                
                to_tg_id = db.get_telegram_id_by_owner(to_account["id"])
                if to_tg_id:
                    try:
                        _bot.send_message(to_tg_id, f"🎁 <b>{amount} الماس</b> از طرف سیستم دریافت کردید!\n💎 موجودی جدید: <b>{new_balance}</b>")
                    except: 
                        pass
                
                _bot.reply_to(message, 
                    f"✅ <b>{amount} الماس</b> به <b>{to_account['username']}</b> داده شد.\n💎 موجودی جدید: <b>{new_balance}</b>",
                    reply_markup=_owner_keyboard())
                _owner_states.pop(message.from_user.id, None)
            
            elif state == "give_user":
                state_data["data"]["username"] = text.lstrip("@")
                state_data["state"] = "give_amount"
                _bot.reply_to(message, f"📝 کاربر: <b>{text}</b>\n\n💎 مبلغ الماس را ارسال کنید:")
            
            elif state == "give_amount":
                try:
                    amount = int(text)
                except:
                    return _bot.reply_to(message, "❌ مبلغ باید عدد باشد:")
                
                username = state_data["data"]["username"]
                account = db.get_account_by_username(username)
                if not account:
                    _bot.reply_to(message, f"❌ کاربر '{username}' یافت نشد.", reply_markup=_owner_keyboard())
                    _owner_states.pop(message.from_user.id, None)
                    return
                
                db.add_tokens(account["id"], amount)
                new_balance = db.get_token_balance(account["id"])
                token_price = getattr(config, 'TOKEN_PRICE_TOMAN', 200)
                
                tg_id = db.get_telegram_id_by_owner(account["id"])
                if tg_id:
                    try:
                        _bot.send_message(tg_id, f"🎁 <b>{amount} الماس</b> از طرف مالک دریافت کردید!\n💎 موجودی جدید: <b>{new_balance}</b>")
                    except: 
                        pass
                
                _bot.reply_to(message, 
                    f"✅ <b>{amount}</b> الماس به <b>{account['username']}</b> داده شد.\n"
                    f"💎 موجودی جدید: <b>{new_balance}</b> (معادل {new_balance * token_price} تومان)",
                    reply_markup=_owner_keyboard())
                _owner_states.pop(message.from_user.id, None)

            elif state == "set_card":
                card = text.strip().replace("-", "").replace(" ", "")
                db.set_global_setting("card_number", card)
                _bot.reply_to(message,
                    f"✅ شماره کارت ذخیره شد:\n<code>{card}</code>",
                    reply_markup=_owner_keyboard())
                _owner_states.pop(message.from_user.id, None)

            elif state == "waiting_mission_channel":
                ch = text.strip()
                if not ch.startswith("@"):
                    ch = "@" + ch
                if db.add_mission_channel(ch):
                    _bot.reply_to(message, f"✅ کانال <b>{ch}</b> به لیست ماموریت اضافه شد.", reply_markup=_owner_keyboard())
                else:
                    _bot.reply_to(message, "⚠️ خطا یا کانال تکراری است.", reply_markup=_owner_keyboard())
                _owner_states.pop(message.from_user.id, None)

            elif state == "waiting_mission_reward":
                try:
                    reward = int(text.strip())
                    if reward < 0:
                        raise ValueError
                except Exception:
                    return _bot.reply_to(message, "❌ مقدار باید عدد صحیح و مثبت باشد. دوباره تلاش کنید:")
                db.set_global_setting("mission_reward", str(reward))
                _bot.reply_to(message, f"✅ جایزهٔ ماموریت روی <b>{reward} الماس</b> تنظیم شد.", reply_markup=_owner_keyboard())
                _owner_states.pop(message.from_user.id, None)
        
        except Exception as e:
            print(f"❌ خطا در handle_owner_state: {e}")
            _bot.reply_to(message, f"❌ خطا: {e}", reply_markup=_owner_keyboard())
            _owner_states.pop(message.from_user.id, None)

    # ══════════════════════════════════════════════════════════════════════════
    # ⌨️ کیپد عددی برای ورود — UI کمکی (روش اصلی: پنل وب)
    # ══════════════════════════════════════════════════════════════════════════
    def _numpad_keyboard(digits_so_far: str, mode: str = "code") -> types.InlineKeyboardMarkup:
        display = "•" * len(digits_so_far) if digits_so_far else "—"
        title_row = [types.InlineKeyboardButton(f"🔐 {display}", callback_data="kp_noop")]
        row1 = [types.InlineKeyboardButton(str(i), callback_data=f"kp_digit_{i}") for i in [1, 2, 3]]
        row2 = [types.InlineKeyboardButton(str(i), callback_data=f"kp_digit_{i}") for i in [4, 5, 6]]
        row3 = [types.InlineKeyboardButton(str(i), callback_data=f"kp_digit_{i}") for i in [7, 8, 9]]
        row4 = [
            types.InlineKeyboardButton("⬅️ حذف", callback_data="kp_backspace"),
            types.InlineKeyboardButton("0", callback_data="kp_digit_0"),
            types.InlineKeyboardButton("✔️ تأیید", callback_data="kp_confirm"),
        ]
        markup = types.InlineKeyboardMarkup()
        markup.row(*title_row)
        markup.row(*row1)
        markup.row(*row2)
        markup.row(*row3)
        markup.row(*row4)
        return markup

    def _kp_cleanup_expired():
        """پاکسازی بافرهای منقضی‌شده"""
        now = time.time()
        expired = [uid for uid, buf in _keypad_buffers.items() if now - buf["ts"] > _KEYPAD_TIMEOUT]
        for uid in expired:
            _keypad_buffers.pop(uid, None)

    @_bot.message_handler(commands=["login"], chat_types=["private"])
    def cmd_login_numpad(message):
        """شروع فرآیند ورود با کیپد (روش کمکی — ابتدا شماره را در سایت وارد کنید)"""
        _kp_cleanup_expired()
        if not _BOT_LOGIN_AVAILABLE:
            return _bot.reply_to(message, "⚠️ این قابلیت در محیط فعلی فعال نیست.")
        uid = message.from_user.id
        if not has_pending_code_login(uid):
            return _bot.reply_to(message,
                "📱 ابتدا شمارهٔ تلفن خود را در پنل وب وارد کنید تا کد تأیید ارسال شود.\n\n"
                "بعد از ارسال کد، دوباره /login بزنید.")
        _keypad_buffers[uid] = {"digits": [], "ts": time.time(), "mode": "code"}
        _bot.send_message(uid,
            "🔢 <b>کیپد ورود</b>\n\nکد تأیید دریافت‌شده را با دکمه‌ها وارد کنید:",
            reply_markup=_numpad_keyboard("", "code"))

    @_bot.callback_query_handler(func=lambda call: call.data.startswith("kp_"))
    def callback_keypad(call):
        _kp_cleanup_expired()
        uid = call.from_user.id
        buf = _keypad_buffers.get(uid)
        if not buf:
            return _bot.answer_callback_query(call.id, "⏰ زمان ورود منقضی شد. دوباره /login بزنید.", show_alert=True)

        # بروز‌رسانی timestamp برای جلوگیری از timeout بی‌مورد
        buf["ts"] = time.time()
        data = call.data
        mode = buf.get("mode", "code")
        digits = buf["digits"]

        if data == "kp_noop":
            return _bot.answer_callback_query(call.id)

        elif data.startswith("kp_digit_"):
            digit = data.split("_")[-1]
            if not digit.isdigit():
                return _bot.answer_callback_query(call.id, "❌ ورودی نامعتبر")
            max_len = 8 if mode == "code" else 50
            if len(digits) >= max_len:
                return _bot.answer_callback_query(call.id, "⚠️ طول حداکثر رسید")
            digits.append(digit)
            code_so_far = "".join(digits)
            _bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=_numpad_keyboard(code_so_far, mode)
            )
            _bot.answer_callback_query(call.id)

        elif data == "kp_backspace":
            if digits:
                digits.pop()
            code_so_far = "".join(digits)
            _bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=_numpad_keyboard(code_so_far, mode)
            )
            _bot.answer_callback_query(call.id)

        elif data == "kp_confirm":
            if not digits:
                return _bot.answer_callback_query(call.id, "⚠️ چیزی وارد نشده", show_alert=True)
            code = "".join(digits)
            _keypad_buffers.pop(uid, None)
            _bot.answer_callback_query(call.id, "⏳ در حال بررسی...")
            try:
                # ویرایش پیام — نمایش لودینگ
                _bot.edit_message_text(
                    "⏳ در حال تأیید کد...",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
            except Exception:
                pass

            if not _BOT_LOGIN_AVAILABLE:
                return _bot.send_message(uid, "⚠️ عملیات ورود در این محیط در دسترس نیست.")

            account = db.get_account_by_tg_id(uid)
            if not account:
                return _bot.send_message(uid, "⚠️ اکانت وب‌سایت شما یافت نشد. ابتدا ثبت‌نام کنید.")

            if mode == "code":
                result = verify_login_code(account["id"], code)
                if result.get("ok"):
                    _bot.send_message(uid, "✅ <b>ورود موفق!</b>\nبات شما آماده است.", reply_markup=_user_keyboard() if uid != OWNER_TG_ID else _owner_keyboard())
                elif result.get("need_2fa"):
                    _keypad_buffers[uid] = {"digits": [], "ts": time.time(), "mode": "2fa"}
                    _bot.send_message(uid,
                        "🔐 <b>تأیید دومرحله‌ای</b>\n\nرمز دومرحله‌ای را وارد کنید:",
                        reply_markup=_numpad_keyboard("", "2fa"))
                else:
                    _bot.send_message(uid, f"❌ خطا: {result.get('error', 'کد اشتباه')}\n\nدوباره /login بزنید.")
            elif mode == "2fa":
                result = verify_login_2fa(account["id"], code)
                if result.get("ok"):
                    _bot.send_message(uid, "✅ <b>ورود موفق!</b>\nبات شما آماده است.", reply_markup=_user_keyboard() if uid != OWNER_TG_ID else _owner_keyboard())
                else:
                    _bot.send_message(uid, f"❌ رمز دومرحله‌ای اشتباه: {result.get('error','')}\n\nدوباره تلاش کنید: /login")

    # ══════════════════════════════════════════════════════════════════════════
    # دستورات متنی قدیمی
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(commands=["addchannel", "removechannel", "give", "users", "wc_create", "wc_winner", "transfer"])
    def cmd_text_commands(message):
        if message.from_user.id != OWNER_TG_ID:
            return
        _bot.reply_to(message, 
            "📢 تمام دستورات مدیریتی به پنل دکمه‌ای منتقل شدند.\n\n"
            "روی دکمه <b>📢 مدیریت</b> کلیک کنید.",
            reply_markup=_owner_keyboard())

    # ══════════════════════════════════════════════════════════════════════════
    # ✅ پیام‌های ناشناخته
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(func=lambda m: True, chat_types=['private'])
    def cmd_unknown(message):
        try:
            tg_id = message.from_user.id

            # اگه کاربر در حال شرط‌بندی WC هست → به handler مربوطه بده
            if tg_id in _wc_pending_bet:
                return cmd_wc_join(message)

            # اگه کاربر در حال خرید هست → به handler مربوطه بده
            if tg_id in _purchase_states:
                return handle_purchase_state(message)

            account = _get_account_cached(tg_id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())

            kb = _owner_keyboard() if tg_id == OWNER_TG_ID else _user_keyboard()
            _bot.reply_to(message, "⚠️ دستور نامعتبر. از دکمه‌های زیر استفاده کنید:", reply_markup=kb)
        except Exception as e:
            print(f"❌ خطا در cmd_unknown: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Polling
    # ══════════════════════════════════════════════════════════════════════════
    def _polling_loop():
        while True:
            try:
                _bot.infinity_polling(
                    timeout=20,
                    long_polling_timeout=15,
                    restart_on_change=False,
                    skip_pending=True
                )
            except Exception as e:
                if "409" in str(e):
                    time.sleep(10)
                    try:
                        _bot.delete_webhook(drop_pending_updates=True)
                    except:
                        pass
                else:
                    print(f"⚠️ خطای polling: {e}")
                    time.sleep(3)

    t = threading.Thread(target=_polling_loop, daemon=True)
    t.start()
    print(f"✅ ربات الماس @{BOT_USERNAME} استارت شد")
