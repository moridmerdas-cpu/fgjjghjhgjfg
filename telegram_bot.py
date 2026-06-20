import threading
import time
import telebot
from telebot import types
import database as db
import config
import datetime
import random
import re

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
        if key.startswith("lottery_"):
            return 60
        return 300

cache = SmartCache()
_owner_states = {}
_lottery_players = {}
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
        return markup

    def _owner_keyboard():
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add("💎 موجودی", "🎁 هدیه روزانه")
        markup.add("🔗 رفرال", "🛒 خرید الماس")
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
            types.InlineKeyboardButton("🎲 قرعه‌کشی (مالک)", callback_data="admin_lottery")
        )
        markup.add(
            types.InlineKeyboardButton("💎 انتقال الماس", callback_data="admin_transfer"),
            types.InlineKeyboardButton("💰 دادن الماس", callback_data="admin_give")
        )
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
        return markup

    # ══════════════════════════════════════════════════════════════════════════
    # 📝 دستور قرعه‌کشی
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(func=lambda m: m.text and m.text.startswith("قرعه "), chat_types=['private', 'group', 'supergroup'])
    def cmd_lottery(message):
        try:
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.")
            
            parts = message.text.split()
            if len(parts) < 2:
                return _bot.reply_to(message, "❗ فرمت: قرعه [تعداد الماس]\nمثال: قرعه 100")
            
            try:
                prize = int(parts[1])
                if prize < 1:
                    return _bot.reply_to(message, "❌ مبلغ باید بیشتر از 0 باشد.")
            except:
                return _bot.reply_to(message, "❌ مبلغ باید عدد باشد.")
            
            balance = db.get_token_balance(account["id"])
            if balance < prize:
                return _bot.reply_to(message, f"❌ موجودی کافی ندارید! نیاز به {prize} الماس دارید.\nموجودی فعلی: {balance} الماس")
            
            if not db.deduct_tokens(account["id"], prize):
                return _bot.reply_to(message, "❌ خطا در کسر الماس!")
            
            lottery_id = db.create_lottery(
                chat_id=message.chat.id,
                creator_tg_id=message.from_user.id,
                prize_amount=prize,
                duration_minutes=2,
                entry_fee=prize
            )
            
            _lottery_players[lottery_id] = [message.from_user.id]
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton(
                    f"🎲 شرکت در قرعه‌کشی ({prize} الماس)", 
                    callback_data=f"join_lottery_{lottery_id}"
                )
            )
            
            creator_name = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
            
            msg = _bot.reply_to(
                message,
                f"🎉 <b>قرعه‌کشی!</b>\n\n"
                f"👤 سازنده: {creator_name}\n"
                f"💎 مبلغ ورودی: <b>{prize} الماس</b>\n"
                f"💰 مجموع جایزه: <b>{prize * 2} الماس</b>\n"
                f"👥 شرکت‌کنندگان: ۱ نفر\n\n"
                f"⏳ برای شرکت، روی دکمه زیر کلیک کنید!\n"
                f"(با ورود نفر دوم، قرعه‌کشی انجام می‌شود)",
                reply_markup=markup
            )
            
            db.update_lottery_message(lottery_id, msg.message_id)
            threading.Timer(120, _auto_finish_lottery, args=[lottery_id, message.chat.id]).start()
            
        except Exception as e:
            print(f"❌ خطا در cmd_lottery: {e}")
            _bot.reply_to(message, f"❌ خطا: {e}")

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
            if len(parts) < 3:
                return _bot.reply_to(message, "❗ فرمت: انتقال [یوزرنیم] [تعداد]\nمثال: انتقال @ali 10")
            
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
    # 🎲 Callback: شرکت در قرعه‌کشی
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.callback_query_handler(func=lambda call: call.data.startswith("join_lottery_"))
    def callback_join_lottery(call):
        try:
            lottery_id = int(call.data.split("_")[2])
            lottery = db.get_lottery(lottery_id)
            
            if not lottery or lottery["status"] != "active":
                return _bot.answer_callback_query(call.id, "❌ این قرعه‌کشی فعال نیست یا به پایان رسیده.", show_alert=True)
            
            if lottery_id in _lottery_players and call.from_user.id in _lottery_players[lottery_id]:
                return _bot.answer_callback_query(call.id, "❌ شما قبلاً در این قرعه‌کشی ثبت‌نام کرده‌اید.", show_alert=True)
            
            if lottery["creator_tg_id"] == call.from_user.id:
                return _bot.answer_callback_query(call.id, "❌ شما سازنده قرعه‌کشی هستید! منتظر نفر دوم باشید.", show_alert=True)
            
            account = _get_account_cached(call.from_user.id)
            if not account:
                return _bot.answer_callback_query(call.id, "❌ ابتدا در پنل وب ثبت‌نام کنید.", show_alert=True)
            
            entry_fee = lottery["prize_amount"]
            balance = db.get_token_balance(account["id"])
            
            if balance < entry_fee:
                return _bot.answer_callback_query(
                    call.id, 
                    f"❌ موجودی کافی ندارید! نیاز به {entry_fee} الماس دارید.\nموجودی فعلی: {balance} الماس", 
                    show_alert=True
                )
            
            if not db.deduct_tokens(account["id"], entry_fee):
                return _bot.answer_callback_query(call.id, "❌ خطا در کسر الماس!", show_alert=True)
            
            success, msg = db.join_lottery(lottery_id, call.from_user.id, account["id"], entry_fee)
            
            if success:
                if lottery_id not in _lottery_players:
                    _lottery_players[lottery_id] = []
                _lottery_players[lottery_id].append(call.from_user.id)
                
                _bot.answer_callback_query(
                    call.id, 
                    f"✅ شما با {entry_fee} الماس در قرعه‌کشی ثبت‌نام کردید!\nمجموع جایزه: {entry_fee * 2} الماس", 
                    show_alert=True
                )
                
                if len(_lottery_players[lottery_id]) >= 2:
                    _finish_lottery_immediately(lottery_id, call.message.chat.id)
                else:
                    try:
                        _bot.edit_message_text(
                            f"🎉 <b>قرعه‌کشی!</b>\n\n"
                            f"💎 مبلغ ورودی: <b>{entry_fee} الماس</b>\n"
                            f"💰 مجموع جایزه: <b>{entry_fee * 2} الماس</b>\n"
                            f"👥 شرکت‌کنندگان: {len(_lottery_players[lottery_id])} نفر\n\n"
                            f"⏳ منتظر نفر دوم...",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id
                        )
                    except:
                        pass
            else:
                _bot.answer_callback_query(call.id, msg, show_alert=True)
                
        except Exception as e:
            print(f"❌ خطا در callback_join_lottery: {e}")
            _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:100]}", show_alert=True)

    # ══════════════════════════════════════════════════════════════════════════
    # ⚽ سیستم جام جهانی — football-data.org
    # ══════════════════════════════════════════════════════════════════════════

    # کش محلی نتایج API (برای کاهش مصرف)
    _wc_api_cache = {"matches": [], "results": {}, "last_fetch": 0, "last_result_fetch": 0}
    # وضعیت انتخاب تیم کاربران: tg_id -> {challenge_id, selected_option}
    _wc_pending_bet = {}

    def _wc_api_get(endpoint: str) -> dict:
        """فراخوانی API football-data.org"""
        import urllib.request, json as _json
        api_key = getattr(config, "FOOTBALL_API_KEY", "")
        if not api_key:
            return {}
        url = f"https://api.football-data.org/v4/{endpoint}"
        req = urllib.request.Request(url, headers={"X-Auth-Token": api_key})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return _json.loads(resp.read().decode())
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
            print("⚠️ WC_CHANNEL_ID تنظیم نشده!")
            return
        min_bet = getattr(config, "WC_MIN_BET", 10)
        max_bet = getattr(config, "WC_MAX_BET", 5000)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton(f"🔵 {team1}", callback_data=f"wc_pick_{challenge_id}_team1"),
            types.InlineKeyboardButton("🤝 مساوی",    callback_data=f"wc_pick_{challenge_id}_draw"),
            types.InlineKeyboardButton(f"🔴 {team2}", callback_data=f"wc_pick_{challenge_id}_team2"),
        )
        text = (
            f"⚽️ <b>چالش جام جهانی!</b>\n\n"
            f"🆚 <b>{team1}</b>  vs  <b>{team2}</b>\n"
            f"⏰ زمان بازی: <b>{match_time_str}</b>\n\n"
            f"💎 محدوده شرط: {min_bet} – {max_bet} الماس\n\n"
            f"روی تیم مورد نظرت بزن، سپس مبلغ شرط رو بنویس!"
        )
        try:
            msg = _bot.send_message(channel, text, reply_markup=markup)
            db.set_wc_channel_msg(challenge_id, msg.message_id)
        except Exception as e:
            print(f"❌ ارسال چالش به کانال: {e}")

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
                    if dt < datetime.datetime.utcnow() + datetime.timedelta(minutes=20):
                        continue
                    match_time_str = dt.strftime("%Y-%m-%d %H:%M UTC")
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
        """حلقه زمانی — هر WC_POLL_INTERVAL ثانیه"""
        interval = getattr(config, "WC_POLL_INTERVAL", 600)
        while True:
            _wc_auto_fetch_and_create()
            _wc_auto_check_results()
            time.sleep(interval)

    # اجرای scheduler در Thread جداگانه
    _wc_thread = threading.Thread(target=_wc_scheduler, daemon=True)
    _wc_thread.start()

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
    @_bot.message_handler(func=lambda m: m.text and m.text.strip().startswith("شرکت ") and m.chat.type == "private")
    def cmd_wc_join(message):
        try:
            tg_id = message.from_user.id
            pending = _wc_pending_bet.get(tg_id)
            if not pending:
                return _bot.reply_to(message, "❌ ابتدا روی تیم مورد نظر در کانال کلیک کنید.")

            parts = message.text.strip().split()
            if len(parts) < 2:
                return _bot.reply_to(message, "❌ فرمت: شرکت [مبلغ]\nمثال: شرکت 200")
            try:
                amount = int(parts[1])
            except ValueError:
                return _bot.reply_to(message, "❌ مبلغ باید عدد باشد.")

            min_bet = getattr(config, "WC_MIN_BET", 10)
            max_bet = getattr(config, "WC_MAX_BET", 5000)
            if amount < min_bet or amount > max_bet:
                return _bot.reply_to(message, f"❌ مبلغ باید بین {min_bet} و {max_bet} الماس باشد.")

            challenge_id = pending["challenge_id"]
            selected_option = pending["selected_option"]
            account_id = pending["account_id"]

            challenge = db.get_wc_challenge(challenge_id)
            if not challenge:
                _wc_pending_bet.pop(tg_id, None)
                return _bot.reply_to(message, "❌ چالش یافت نشد.")

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
                    f"💎 مبلغ: <b>{amount} الماس</b>\n"
                    f"💰 موجودی باقی‌مانده: {balance} الماس\n\n"
                    f"🏆 در صورت برد، <b>{amount * 2} الماس</b> دریافت می‌کنید!"
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

    # ─── پایان فوری قرعه‌کشی ──────────────────────────────────────────────────
    def _finish_lottery_immediately(lottery_id, chat_id):
        try:
            lottery = db.get_lottery(lottery_id)
            if not lottery or lottery["status"] != "active":
                return
            
            participants = db.get_lottery_participants(lottery_id)
            if len(participants) < 2:
                return
            
            total_prize = lottery["prize_amount"] * 2
            winner = random.choice(participants)
            
            db.add_tokens(winner["owner_id"], total_prize)
            db.finish_lottery(lottery_id, winner["user_tg_id"], winner["owner_id"])
            
            try:
                winner_account = db.get_account(winner["owner_id"])
                winner_name = winner_account["username"] if winner_account else str(winner["user_tg_id"])
            except:
                winner_name = str(winner["user_tg_id"])
            
            msg_text = (
                f"🎉 <b>قرعه‌کشی به پایان رسید!</b>\n\n"
                f"🏆 برنده: <b>{winner_name}</b>\n"
                f"💎 مجموع جایزه: <b>{total_prize} الماس</b>\n"
                f"👥 شرکت‌کنندگان: {len(participants)} نفر\n\n"
                f"🎊 تبریک به برنده!"
            )
            
            if _bot:
                try:
                    _bot.send_message(chat_id, msg_text)
                    _bot.send_message(
                        winner["user_tg_id"],
                        f"🎉 تبریک! شما برنده قرعه‌کشی شدید!\n💎 <b>{total_prize} الماس</b> به حساب شما واریز شد."
                    )
                    for p in participants:
                        if p["user_tg_id"] != winner["user_tg_id"]:
                            try:
                                _bot.send_message(
                                    p["user_tg_id"],
                                    f"😔 متاسفانه شما برنده قرعه‌کشی نشدید!\n💎 {lottery['prize_amount']} الماس از حساب شما کسر شد."
                                )
                            except:
                                pass
                except Exception as e:
                    print(f"❌ خطا در ارسال پیام: {e}")
            
            _lottery_players.pop(lottery_id, None)
            cache.invalidate(f"lottery_")
            
        except Exception as e:
            print(f"❌ خطا در _finish_lottery_immediately: {e}")

    # ─── تایمر پایان قرعه‌کشی ──────────────────────────────────────────────────
    def _auto_finish_lottery(lottery_id, chat_id):
        try:
            lottery = db.get_lottery(lottery_id)
            if not lottery or lottery["status"] != "active":
                return
            
            participants = db.get_lottery_participants(lottery_id)
            
            if len(participants) < 2:
                db.finish_lottery(lottery_id, None, None)
                
                creator_id = lottery["creator_tg_id"]
                creator_account = db.get_account_by_tg_id(creator_id)
                if creator_account:
                    db.add_tokens(creator_account["id"], lottery["prize_amount"])
                
                if _bot:
                    _bot.send_message(
                        chat_id,
                        f"⏰ قرعه‌کشی لغو شد!\n\n"
                        f"❌ تعداد شرکت‌کنندگان کافی نبود (حداقل ۲ نفر).\n"
                        f"💎 {lottery['prize_amount']} الماس به سازنده برگشت داده شد."
                    )
            
            _lottery_players.pop(lottery_id, None)
            
        except Exception as e:
            print(f"❌ خطا در _auto_finish_lottery: {e}")

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
                except: 
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

            stats = db.get_token_stats(account["id"])
            
            if message.chat.type == 'private':
                markup = _owner_keyboard() if tg_id == OWNER_TG_ID else _user_keyboard()
            else:
                markup = None

            token_price = getattr(config, 'TOKEN_PRICE_TOMAN', 200)
            
            _bot.reply_to(
                message,
                f"👋 سلام <b>{account['username']}</b>!\n\n"
                f"💎 موجودی: <b>{stats['balance']}</b>\n"
                f"📊 کل دریافتی: <b>{stats['total_earned']}</b>\n\n"
                f"⚡ هر <b>{config.TOKENS_PER_SESSION} الماس</b> = <b>{config.SESSION_HOURS} ساعت</b> سلف‌بات\n"
                f"💰 قیمت هر الماس: <b>{token_price} تومان</b>",
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

    @_bot.message_handler(func=lambda m: m.text == "🛒 خرید الماس", chat_types=['private'])
    def cmd_buy(message):
        try:
            if not require_membership(message): 
                return
            account = _get_account_cached(message.from_user.id)
            username_txt = account["username"] if account else str(message.from_user.id)
            
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(types.InlineKeyboardButton("📩 خرید از مالک (@Amele55)", url="https://t.me/Amele55"))
            for sp in getattr(config, 'SPONSORS', []):
                markup.add(types.InlineKeyboardButton(f"🤝 {sp['name']}: @{sp['username']}", url=f"https://t.me/{sp['username']}"))

            token_price = getattr(config, 'TOKEN_PRICE_TOMAN', 200)
            _bot.reply_to(message,
                f"🛒 <b>خرید الماس</b>\n\n"
                f"💰 قیمت هر الماس: <b>{token_price} تومان</b>\n"
                f"👤 یوزرنیم پنل شما: <b>{username_txt}</b>\n\n"
                f"برای خرید، روی دکمه «خرید از مالک» کلیک کنید.",
                reply_markup=markup)
        except Exception as e:
            print(f"❌ خطا در cmd_buy: {e}")

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
    @_bot.callback_query_handler(func=lambda call: call.data.startswith("admin_") or call.data.startswith("rmch_") or call.data.startswith("wcwin_") or call.data.startswith("wc_") or call.data == "addch_prompt")
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
                    lines = [f"👥 <b>کاربران ({len(accounts)} نفر):</b>\n\n"]
                    for acc in accounts[:30]:
                        bal = db.get_token_balance(acc["id"])
                        lines.append(f"• <b>{acc['username']}</b> — 💎{bal}")
                    text = "\n".join(lines)
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
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel"))
                _bot.edit_message_text(
                    "🏆 <b>مدیریت چالش‌های جام جهانی</b>\n\nیک گزینه را انتخاب کنید:",
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
            
            elif data == "admin_lottery":
                _owner_states[call.from_user.id] = {"state": "lottery_amount"}
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="admin_panel"))
                _bot.edit_message_text(
                    "🎲 <b>ایجاد قرعه‌کشی گروهی (مالک)</b>\n\n"
                    "💎 مبلغ جایزه را ارسال کنید (الماس):\n\n"
                    "مثال: <code>100</code>\n\n"
                    "📌 قرعه‌کشی در گروه <code>@amelselfgap</code> ایجاد می‌شود",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup
                )
                _bot.answer_callback_query(call.id)
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
    @_bot.message_handler(func=lambda m: m.from_user.id == OWNER_TG_ID and m.from_user.id in _owner_states, chat_types=['private'])
    def handle_owner_state(message):
        try:
            state_data = _owner_states[message.from_user.id]
            state = state_data["state"]
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
            
            elif state == "lottery_amount":
                try:
                    prize = int(text)
                except:
                    return _bot.reply_to(message, "❌ مبلغ باید عدد باشد:")
                
                group = getattr(config, 'WORLD_CUP_GROUP', '@amelselfgap')
                lottery_id = db.create_lottery(0, OWNER_TG_ID, prize, 2, prize)
                
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton(f"🎲 شرکت در قرعه‌کشی ({prize} الماس)", callback_data=f"join_lottery_{lottery_id}"))
                _lottery_players[lottery_id] = []
                
                try:
                    msg = _bot.send_message(group,
                        f"🎉 <b>قرعه‌کشی ویژه (مالک)!</b>\n\n"
                        f"💎 مبلغ ورودی: <b>{prize} الماس</b>\n"
                        f"💰 مجموع جایزه: <b>{prize * 2} الماس</b>\n\n"
                        f"با ورود نفر دوم، قرعه‌کشی انجام می‌شود!",
                        reply_markup=markup)
                    db.update_lottery_message(lottery_id, msg.message_id)
                    _bot.reply_to(message, 
                        f"✅ قرعه‌کشی در گروه {group} ایجاد شد!\n\n"
                        f"💎 جایزه: {prize} الماس\n"
                        f"📢 ID: <code>{lottery_id}</code>",
                        reply_markup=_owner_keyboard())
                    
                    threading.Timer(120, _auto_finish_lottery, args=[lottery_id, group]).start()
                except Exception as e:
                    _bot.reply_to(message, f"❌ خطا: {e}\nمطمئن شوید ربات در {group} ادمین است.", reply_markup=_owner_keyboard())
                
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
        
        except Exception as e:
            print(f"❌ خطا در handle_owner_state: {e}")
            _bot.reply_to(message, f"❌ خطا: {e}", reply_markup=_owner_keyboard())
            _owner_states.pop(message.from_user.id, None)

    # ══════════════════════════════════════════════════════════════════════════
    # دستورات متنی قدیمی
    # ══════════════════════════════════════════════════════════════════════════
    @_bot.message_handler(commands=["addchannel", "removechannel", "give", "users", "wc_create", "wc_winner", "lottery", "transfer"])
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
            account = _get_account_cached(message.from_user.id)
            if not account:
                return _bot.reply_to(message, "⚠️ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_user_keyboard())
            
            kb = _owner_keyboard() if message.from_user.id == OWNER_TG_ID else _user_keyboard()
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
