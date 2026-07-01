import threading
import time
import telebot
from telebot import types
import database as db
import config
import datetime
import random
import re

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

def _format_plan_remaining(owner_id: int) -> str:
    """متن باقی‌مانده‌ی پلن سلف یک کاربر (برای نمایش به مالک در لیست کاربران)."""
    try:
        sub = db.get_subscription(owner_id)
    except Exception:
        sub = None
    if not sub or not sub.get("expires_at"):
        return "بدون پلن"
    exp = sub["expires_at"]
    if isinstance(exp, str):
        try:
            exp = datetime.datetime.fromisoformat(exp)
        except Exception:
            return "نامشخص"
    if exp.tzinfo is not None:
        exp = exp.replace(tzinfo=None)
    now_teh = datetime.datetime.now(_TEHRAN_OFFSET).replace(tzinfo=None)
    secs = (exp - now_teh).total_seconds()
    if secs <= 0:
        return "❌ منقضی شده"
    days = int(secs // 86400)
    hours = int((secs % 86400) // 3600)
    minutes = int((secs % 3600) // 60)
    if days > 0:
        return f"{days} روز و {hours} ساعت"
    if hours > 0:
        return f"{hours} ساعت و {minutes} دقیقه"
    return f"{minutes} دقیقه"

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

# ─── شرط‌بندی‌های فعال ─────────────────────────────────────────────────────
_active_bets = {}

# ══════════════════════════════════════════════════════════════════════════════
# 🔐 سیستم ساخت اکانت و لاگین تلگرام از طریق ربات
# ══════════════════════════════════════════════════════════════════════════════
_reg_sessions: dict = {}
_REG_TIMEOUT = 300
_tg_loop = None

def _get_tg_loop():
    global _tg_loop
    import asyncio as _asyncio
    if _tg_loop is None or _tg_loop.is_closed():
        _tg_loop = _asyncio.new_event_loop()
        t = threading.Thread(target=_tg_loop.run_forever, daemon=True)
        t.start()
    return _tg_loop

def _run_tg(coro):
    import asyncio as _asyncio
    return _asyncio.run_coroutine_threadsafe(coro, _get_tg_loop()).result(timeout=30)

def _kp_markup(digits, mode="code"):
    prefix = f"reg_kp_{mode}_"
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("1", callback_data=f"{prefix}1", style="primary"),
        types.InlineKeyboardButton("2", callback_data=f"{prefix}2", style="primary"),
        types.InlineKeyboardButton("3", callback_data=f"{prefix}3", style="primary"),
    )
    markup.add(
        types.InlineKeyboardButton("4", callback_data=f"{prefix}4", style="primary"),
        types.InlineKeyboardButton("5", callback_data=f"{prefix}5", style="primary"),
        types.InlineKeyboardButton("6", callback_data=f"{prefix}6", style="primary"),
    )
    markup.add(
        types.InlineKeyboardButton("7", callback_data=f"{prefix}7", style="primary"),
        types.InlineKeyboardButton("8", callback_data=f"{prefix}8", style="primary"),
        types.InlineKeyboardButton("9", callback_data=f"{prefix}9", style="primary"),
    )
    markup.add(
        types.InlineKeyboardButton("⬅️", callback_data=f"{prefix}del", style="danger"),
        types.InlineKeyboardButton("0", callback_data=f"{prefix}0", style="primary"),
        types.InlineKeyboardButton("✔️", callback_data=f"{prefix}confirm", style="success"),
    )
    markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="reg_cancel", style="danger"))
    return markup

def _kp_display(digits, mode="code"):
    if mode in ("2fa", "pw"):
        return "●" * len(digits) if digits else "  _ _ _  "
    return digits if digits else "  _ _ _ _ "

def _reg_expired(tg_id):
    s = _reg_sessions.get(tg_id)
    return not s or time.time() > s.get("expires", 0)

def _reg_clear(tg_id):
    _reg_sessions.pop(tg_id, None)

def get_bot():
    return _bot

def check_membership_cached(user_id):
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

def _check_membership_cached(user_id):
    return check_membership_cached(user_id)

def get_account_cached(tg_id):
    cache_key = f"account_{tg_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    account = db.get_account_by_tg_id(tg_id)
    if account:
        cache.set(cache_key, account)
    return account

def _get_account_cached(tg_id):
    return get_account_cached(tg_id)

def start_token_bot():
    global _bot, BOT_USERNAME
    if not config.BOT_TOKEN:
        print("⚠️ BOT_TOKEN تنظیم نشده — ربات الماس غیرفعال است")
        return
    try:
        _bot = telebot.TeleBot(config.BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
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

# ─── توابع کمکی ───────────────────────────────────────────────────────────────
def send_forced_channels_menu(message, missing_channels):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch in missing_channels:
        ch_clean = ch.lstrip("@")
        markup.add(types.InlineKeyboardButton(f"📢 عضویت در {ch}", url=f"https://t.me/{ch_clean}", style="primary"))
    markup.add(types.InlineKeyboardButton("✅ بررسی عضویت من", callback_data="check_join", style="success"))
    channels_list = "\n".join([f"🔸 {ch}" for ch in missing_channels])
    _bot.reply_to(
        message,
        f"⛔️ <b>ورود به ربات منوط به عضویت در کانال‌های زیر است:</b>\n\n"
        f"{channels_list}\n\n"
        f"👇 روی هر کانال کلیک کنید و Join بزنید، سپس دکمه «بررسی عضویت من» را بزنید:",
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

def _user_keyboard(show_remove_self=True):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🤖 مدیریت سلف", style="primary"))
    return markup

def _owner_keyboard(show_remove_self=True):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("📢 مدیریت", style="danger"),
        types.KeyboardButton("🤖 مدیریت سلف", style="primary")
    )
    return markup

def _main_inline_keyboard(account=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💎 موجودی", callback_data="menu_balance", style="primary"),
        types.InlineKeyboardButton("🎁 هدیه روزانه", callback_data="menu_daily", style="success")
    )
    markup.add(
        types.InlineKeyboardButton("🔗 رفرال", callback_data="menu_referral", style="primary"),
        types.InlineKeyboardButton("🛒 خرید الماس", callback_data="menu_buy", style="success")
    )
    markup.add(
        types.InlineKeyboardButton("🎯 ماموریت‌ها", callback_data="menu_missions", style="primary")
    )
    markup.add(
        types.InlineKeyboardButton("📖 راهنما", callback_data="guide_menu", style="success")
    )
    if account is not None:
        try:
            is_logged_in = db.get_setting(account["id"], "logged_in", "0") == "1"
        except Exception:
            is_logged_in = True
        if not is_logged_in:
            markup.add(
                types.InlineKeyboardButton("🤖 ورود سلف با ربات", callback_data="reg_start", style="success")
            )
    return markup

# ══════════════════════════════════════════════════════════════════════════════
# 💎 خرید پلن برای کاربران جدید (قبل از ثبت‌نام)
# ══════════════════════════════════════════════════════════════════════════════
PLANS_NEW = {
    "weekly": {"fa": "هفتگی", "days": 7, "toman": 22500},
    "monthly": {"fa": "ماهانه", "days": 30, "toman": 90000},
    "bimonthly": {"fa": "دو ماهه", "days": 60, "toman": 180000},
}

@_bot.callback_query_handler(func=lambda call: call.data.startswith("new_plan_"))
def callback_new_plan(call):
    try:
        tg_id = call.from_user.id
        plan_key = call.data.replace("new_plan_", "")
        plan = PLANS_NEW.get(plan_key)
        if not plan:
            return _bot.answer_callback_query(call.id, "❌ پلن نامعتبر", show_alert=True)
        
        card = _get_card_number()
        payment_id = db.create_payment(
            0,  # owner_id = 0 یعنی کاربر هنوز ثبت‌نام نکرده
            tg_id,
            "new_registration",
            plan=plan_key,
            toman_amount=plan["toman"]
        )
        
        _purchase_states[tg_id] = {
            "step": "waiting_receipt_new",
            "payment_id": payment_id,
            "plan_key": plan_key,
            "plan_info": plan
        }
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="new_plan_cancel", style="danger"))
        
        _bot.edit_message_text(
            f"💳 <b>خرید پلن {plan['fa']}</b>\n\n"
            f"💰 مبلغ: <b>{plan['toman']:,} تومان</b>\n"
            f"💳 شماره کارت: <code>{card}</code>\n"
            f"👤 به نام: <b>غفاری</b>\n\n"
            f"📸 بعد از واریز، تصویر رسید را ارسال کنید 👇",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="HTML"
        )
        _bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"❌ خطا در callback_new_plan: {e}")
        _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:80]}", show_alert=True)

@_bot.callback_query_handler(func=lambda call: call.data == "new_plan_cancel")
def callback_new_plan_cancel(call):
    _purchase_states.pop(call.from_user.id, None)
    _bot.answer_callback_query(call.id, "❌ لغو شد")
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💎 خرید پلن هفتگی (7 روز) — 22,500 تومان", callback_data="new_plan_weekly", style="primary"),
        types.InlineKeyboardButton("💎 خرید پلن ماهانه (30 روز) — 90,000 تومان", callback_data="new_plan_monthly", style="primary"),
        types.InlineKeyboardButton("💎 خرید پلن دو ماهه (60 روز) — 180,000 تومان", callback_data="new_plan_bimonthly", style="primary"),
    )
    markup.add(
        types.InlineKeyboardButton("📞 پشتیبانی: @amele55", url="https://t.me/amele55", style="primary")
    )
    _bot.edit_message_text(
        "⚠️ <b>ابتدا پلن خود را خریداری کنید</b>، سپس می‌توانید ثبت‌نام کنید.\n\n"
        "💡 <b>دلیل:</b> به دلیل محدودیت منابع سرور، ابتدا باید پلن تهیه کنید.\n\n"
        "👇 یکی از پلن‌های زیر را انتخاب کنید:\n\n"
        "📞 برای نکات تکمیلی به آیدی <b>@amele55</b> پیام دهید.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode="HTML"
    )

# ══════════════════════════════════════════════════════════════════════════════
# ✅ تایید/رد پرداخت جدید (قبل از ثبت‌نام)
# ══════════════════════════════════════════════════════════════════════════════
@_bot.callback_query_handler(func=lambda call: call.data.startswith("new_approve_") or call.data.startswith("new_reject_"))
def callback_new_payment_approval(call):
    try:
        if call.from_user.id != OWNER_TG_ID:
            return _bot.answer_callback_query(call.id, "❌ فقط مالک دسترسی دارد", show_alert=True)
        
        action = "approve" if call.data.startswith("new_approve_") else "reject"
        payment_id = int(call.data.split("_")[2])
        payment = db.get_payment(payment_id)
        
        if not payment:
            return _bot.answer_callback_query(call.id, "❌ پرداخت یافت نشد", show_alert=True)
        if payment["status"] != "pending":
            return _bot.answer_callback_query(call.id, "⚠️ این پرداخت قبلاً پردازش شده", show_alert=True)
        
        tg_id = payment["tg_id"]
        
        if action == "approve":
            db.update_payment(payment_id, status="approved")
            
            # اطلاع به کاربر و شروع فرآیند ثبت‌نام
            try:
                _bot.send_message(
                    tg_id,
                    "✅ <b>پرداخت تأیید شد!</b>\n\n"
                    "🎉 حالا می‌توانید ثبت‌نام کنید.\n\n"
                    "👇 برای شروع ثبت‌نام روی دکمه زیر کلیک کنید:",
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("🤖 شروع ثبت‌نام", callback_data="reg_start", style="success")
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            
            # ذخیره payment_id در session برای استفاده در ثبت‌نام
            _reg_sessions[tg_id] = _reg_sessions.get(tg_id, {})
            _reg_sessions[tg_id]["payment_id"] = payment_id
            _reg_sessions[tg_id]["payment_approved"] = True
            
            _bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("✅ تأیید شد — کاربر ثبت‌نام می‌کند", callback_data="noop", style="success")
                )
            )
            _bot.answer_callback_query(call.id, "✅ پرداخت تأیید شد! کاربر وارد فرآیند ثبت‌نام می‌شود.", show_alert=True)
        
        else:  # reject
            db.update_payment(payment_id, status="rejected")
            try:
                _bot.send_message(
                    tg_id,
                    "❌ <b>پرداخت شما رد شد.</b>\n\n"
                    "لطفاً با پشتیبانی تماس بگیرید: @" + getattr(config, 'SUPPORT_USERNAME', 'll_x_yasi'),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            
            _bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton("❌ رد شد", callback_data="noop", style="danger")
                )
            )
            _bot.answer_callback_query(call.id, "❌ پرداخت رد شد", show_alert=True)
    
    except Exception as e:
        print(f"❌ خطا در callback_new_payment_approval: {e}")
        _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:80]}", show_alert=True)

# ─── مرحله ۱: کاربر «شروع ثبت‌نام» را می‌زند → شماره بخواه ─────────
@_bot.callback_query_handler(func=lambda call: call.data == "reg_start")
def callback_reg_start(call):
    tg_id = call.from_user.id
    _reg_sessions[tg_id] = {
        "step": "phone",
        "digits": "",
        "expires": time.time() + _REG_TIMEOUT,
    }
    _bot.answer_callback_query(call.id)
    try:
        _bot.edit_message_text(
            "📱 <b>مرحله ۱ از ۳ — شماره تلفن</b>\n\n"
            "شماره تلفن خود را با کد کشور وارد کنید:\n"
            "مثال: <code>+989123456789</code>\n\n"
            "⏱ این فرم ۵ دقیقه اعتبار دارد.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("❌ لغو", callback_data="reg_cancel", style="danger")
            ),
        )
    except Exception:
        pass

# ─── مرحله ۱b: دریافت شماره به صورت متن ──────────────────────────────
@_bot.message_handler(
    func=lambda m: m.chat.type == "private"
    and m.from_user.id in _reg_sessions
    and _reg_sessions[m.from_user.id].get("step") == "phone"
    and not _reg_expired(m.from_user.id)
)
def handle_reg_phone(message):
    tg_id = message.from_user.id
    phone = message.text.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    session = _reg_sessions[tg_id]
    session["phone"] = phone
    session["step"] = "sending_code"
    session["expires"] = time.time() + _REG_TIMEOUT
    wait_msg = _bot.reply_to(message, "⏳ در حال ارسال کد تأیید...")
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        async def _send_code():
            cl = TelegramClient(StringSession(), config.API_ID, config.API_HASH)
            await cl.connect()
            result = await cl.send_code_request(phone)
            partial = cl.session.save()
            await cl.disconnect()
            return result.phone_code_hash, partial
        phone_hash, partial_sess = _run_tg(_send_code())
        session["phone_hash"] = phone_hash
        session["partial_session"] = partial_sess
        session["step"] = "code"
        session["digits"] = ""
        session["expires"] = time.time() + _REG_TIMEOUT
        try:
            _bot.delete_message(message.chat.id, wait_msg.message_id)
        except Exception:
            pass
        sent = _bot.send_message(
            tg_id,
            f"📲 <b>مرحله ۲ از ۳ — کد تأیید</b>\n\n"
            f"کد ارسال‌شده به <b>{phone}</b> را با کیپد زیر وارد کنید:\n\n"
            f"<code>{_kp_display('', 'code')}</code>",
            reply_markup=_kp_markup("", "code"),
        )
        session["msg_id"] = sent.message_id
    except Exception as e:
        _reg_clear(tg_id)
        try:
            _bot.delete_message(message.chat.id, wait_msg.message_id)
        except Exception:
            pass
        _bot.reply_to(message, f"❌ خطا در ارسال کد: {str(e)}\n\nدوباره /start بزنید.")

# ─── مرحله ۲fa: دریافت رمز دومرحله‌ای به صورت متن ────────────────────
@_bot.message_handler(
    func=lambda m: m.chat.type == "private"
    and m.from_user.id in _reg_sessions
    and _reg_sessions[m.from_user.id].get("step") == "2fa"
    and not _reg_expired(m.from_user.id)
)
def handle_reg_2fa_text(message):
    tg_id = message.from_user.id
    session = _reg_sessions[tg_id]
    password = message.text.strip()
    if not password:
        _bot.reply_to(message, "❗ رمز نمی‌تواند خالی باشد. دوباره تایپ کنید:")
        return
    try:
        _bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    wait_msg = _bot.send_message(tg_id, "⏳ در حال تأیید رمز دو مرحله‌ای...")
    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        partial_sess = session["partial_session"]
        async def _verify_2fa():
            cl = TelegramClient(StringSession(partial_sess), config.API_ID, config.API_HASH)
            await cl.connect()
            await cl.sign_in(password=password)
            me = await cl.get_me()
            sess = cl.session.save()
            await cl.disconnect()
            return sess, me
        sess, me = _run_tg(_verify_2fa())
        session["saved_session"] = sess
        session["tg_user"] = {"id": me.id, "name": me.first_name, "username": getattr(me, "username", "")}
        session["step"] = "pw"
        session["digits"] = ""
        session["expires"] = time.time() + _REG_TIMEOUT
        try:
            _bot.delete_message(tg_id, wait_msg.message_id)
        except Exception:
            pass
        sent = _bot.send_message(
            tg_id,
            "✅ رمز دو مرحله‌ای تأیید شد!\n\n"
            "🔑 <b>مرحله ۳ — رمز عبور پنل</b>\n\n"
            "یک رمز عبور برای ورود به پنل وب انتخاب کنید:\n"
            f"(حداقل ۴ رقم)\n\n"
            f"<code>{_kp_display('', 'pw')}</code>",
            reply_markup=_kp_markup("", "pw"),
        )
        session["msg_id"] = sent.message_id
    except Exception as e:
        try:
            _bot.delete_message(tg_id, wait_msg.message_id)
        except Exception:
            pass
        session["digits"] = ""
        _bot.send_message(tg_id, "❌ رمز دو مرحله‌ای اشتباه است!\n\nدوباره رمز را تایپ کنید و بفرستید:")

# ─── مرحله ۲ & ۳: کیپد (code / pw) ──────────────────────────────────
@_bot.callback_query_handler(func=lambda call: call.data.startswith("reg_kp_"))
def callback_reg_kp(call):
    tg_id = call.from_user.id
    if _reg_expired(tg_id):
        _reg_clear(tg_id)
        _bot.answer_callback_query(call.id, "⏰ سشن منقضی شده! دوباره /start بزنید.", show_alert=True)
        try:
            _bot.edit_message_text("⏰ سشن منقضی شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        except Exception:
            pass
        return
    session = _reg_sessions[tg_id]
    parts = call.data.split("_", 3)
    mode = parts[2]
    action = parts[3]
    digits = session.get("digits", "")
    if action == "del":
        digits = digits[:-1]
    elif action == "confirm":
        _process_reg_confirm(call, tg_id, session, mode, digits)
        return
    elif action.isdigit():
        if len(digits) >= 10:
            _bot.answer_callback_query(call.id, "❗ حداکثر ۱۰ رقم", show_alert=True)
            return
        digits += action
    else:
        _bot.answer_callback_query(call.id)
        return
    session["digits"] = digits
    display = _kp_display(digits, mode)
    label_map = {
        "code": "📲 <b>مرحله ۲ از ۳ — کد تأیید</b>\n\nکد دریافتی را وارد کنید:",
        "2fa": "🔒 <b>رمز دو مرحله‌ای</b>\n\nرمز دو مرحله‌ای تلگرام را وارد کنید:",
        "pw": "🔑 <b>مرحله ۳ — رمز عبور پنل</b>\n\nرمز عبور برای ورود به پنل وب را وارد کنید:\n(حداقل ۴ رقم)",
    }
    text = f"{label_map.get(mode, '')}\n\n<code>{display}</code>"
    try:
        _bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=_kp_markup(digits, mode),
        )
    except Exception:
        pass
    _bot.answer_callback_query(call.id)

def _process_reg_confirm(call, tg_id, session, mode, digits):
    """پردازش تأیید در هر مرحله"""
    if not digits:
        _bot.answer_callback_query(call.id, "❗ چیزی وارد نکردید!", show_alert=True)
        return
    _bot.answer_callback_query(call.id, "⏳ در حال بررسی...")

    # ── تأیید کد تلگرام ──────────────────────────────────────────────
    if mode == "code":
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError
            phone = session["phone"]
            phone_hash = session["phone_hash"]
            partial_sess = session["partial_session"]
            async def _verify_code():
                cl = TelegramClient(StringSession(partial_sess), config.API_ID, config.API_HASH)
                await cl.connect()
                await cl.sign_in(phone=phone, code=digits, phone_code_hash=phone_hash)
                me = await cl.get_me()
                sess = cl.session.save()
                await cl.disconnect()
                return sess, me
            try:
                sess, me = _run_tg(_verify_code())
                session["saved_session"] = sess
                session["tg_user"] = {"id": me.id, "name": me.first_name, "username": getattr(me, "username", "")}
                session["step"] = "pw"
                session["digits"] = ""
                session["expires"] = time.time() + _REG_TIMEOUT
                try:
                    _bot.edit_message_text(
                        "🔑 <b>مرحله ۳ — رمز عبور پنل</b>\n\n"
                        "یک رمز عبور برای ورود به پنل وب انتخاب کنید:\n"
                        "(حداقل ۴ رقم)\n\n"
                        f"<code>{_kp_display('', 'pw')}</code>",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=_kp_markup("", "pw"),
                    )
                except Exception:
                    pass
            except Exception as e:
                err_str = str(e)
                if "SessionPasswordNeeded" in err_str or "password" in err_str.lower():
                    session["step"] = "2fa"
                    session["digits"] = ""
                    session["expires"] = time.time() + _REG_TIMEOUT
                    try:
                        _bot.edit_message_text(
                            "🔒 <b>رمز دو مرحله‌ای</b>\n\n"
                            "حساب شما رمز دو مرحله‌ای دارد.\n"
                            "رمز را تایپ کنید و بفرستید:",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                        )
                    except Exception:
                        pass
                elif "PhoneCodeInvalid" in err_str or "PHONE_CODE_INVALID" in err_str:
                    session["digits"] = ""
                    try:
                        _bot.edit_message_text(
                            "❌ کد اشتباه بود! دوباره وارد کنید:\n\n"
                            f"<code>{_kp_display('', 'code')}</code>",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                            reply_markup=_kp_markup("", "code"),
                        )
                    except Exception:
                        pass
                elif "PhoneCodeExpired" in err_str or "PHONE_CODE_EXPIRED" in err_str:
                    _reg_clear(tg_id)
                    try:
                        _bot.edit_message_text(
                            "⏰ کد منقضی شده! دوباره /start بزنید.",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                        )
                    except Exception:
                        pass
                else:
                    _reg_clear(tg_id)
                    try:
                        _bot.edit_message_text(
                            f"❌ خطا: {err_str[:200]}\n\nدوباره /start بزنید.",
                            chat_id=call.message.chat.id,
                            message_id=call.message.message_id,
                        )
                    except Exception:
                        pass
        except Exception as e:
            _reg_clear(tg_id)
            try:
                _bot.edit_message_text(f"❌ خطای داخلی: {str(e)[:200]}", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception:
                pass

    # ── تأیید ۲FA ────────────────────────────────────────────────────
    elif mode == "2fa":
        try:
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            partial_sess = session["partial_session"]
            async def _verify_2fa():
                cl = TelegramClient(StringSession(partial_sess), config.API_ID, config.API_HASH)
                await cl.connect()
                await cl.sign_in(password=digits)
                me = await cl.get_me()
                sess = cl.session.save()
                await cl.disconnect()
                return sess, me
            try:
                sess, me = _run_tg(_verify_2fa())
                session["saved_session"] = sess
                session["tg_user"] = {"id": me.id, "name": me.first_name, "username": getattr(me, "username", "")}
                session["step"] = "pw"
                session["digits"] = ""
                session["expires"] = time.time() + _REG_TIMEOUT
                try:
                    _bot.edit_message_text(
                        "✅ ورود موفق!\n\n"
                        "🔑 <b>مرحله ۳ — رمز عبور پنل</b>\n\n"
                        "یک رمز عبور برای ورود به پنل وب انتخاب کنید:\n"
                        "(حداقل ۴ رقم)\n\n"
                        f"<code>{_kp_display('', 'pw')}</code>",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        reply_markup=_kp_markup("", "pw"),
                    )
                except Exception:
                    pass
            except Exception as e:
                session["digits"] = ""
                try:
                    _bot.send_message(
                        call.message.chat.id,
                        "❌ رمز دو مرحله‌ای اشتباه است!\n\nدوباره رمز را تایپ کنید و بفرستید:",
                    )
                except Exception:
                    pass
        except Exception as e:
            _reg_clear(tg_id)
            try:
                _bot.edit_message_text(f"❌ خطا: {str(e)[:200]}", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception:
                pass

    # ── ثبت رمز عبور پنل و ساخت اکانت ────────────────────────────────
    elif mode == "pw":
        if len(digits) < 4:
            _bot.answer_callback_query(call.id, "❗ رمز باید حداقل ۴ رقم باشد!", show_alert=True)
            return
        try:
            tg_user = session["tg_user"]
            saved_session = session["saved_session"]
            tg_id_val = tg_user["id"]

            existing = db.get_account_by_tg_id(tg_id) or db.get_account_by_tg_id(tg_id_val)
            if existing:
                db.set_setting(existing["id"], "session_data", saved_session)
                db.set_setting(existing["id"], "logged_in", "1")
                db.save_telegram_user_id(existing["id"], tg_id)
                _reg_clear(tg_id)

                def _start_existing(_acc_id):
                    time.sleep(1.5)
                    try:
                        from bot import bot_manager
                        from app import get_loop
                        bot_manager.start(_acc_id, get_loop(), check_tokens=False)
                    except Exception as _e:
                        print(f"⚠️ bot_manager.start (existing): {_e}")
                threading.Thread(target=_start_existing, args=(existing["id"],), daemon=True).start()

                try:
                    _bot.edit_message_text(
                        f"✅ <b>خوش برگشتید!</b>\n\n"
                        f"👤 {tg_user['name']}\n"
                        f"🆔 اکانت موجود بود — سلف‌بات فعال شد!\n\n"
                        f"💎 موجودی: <b>{db.get_token_balance(existing['id'])}</b> الماس",
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                    )
                except Exception:
                    pass
                return

            base_username = (tg_user.get("username") or tg_user["name"] or f"user{tg_id_val}").lower()
            base_username = "".join(c for c in base_username if c.isalnum() or c == "_")[:20] or f"user{tg_id_val}"
            candidate = base_username
            suffix = 1
            while db.get_account_by_username(candidate):
                candidate = f"{base_username}{suffix}"
                suffix += 1

            new_id = db.create_account(candidate, digits)
            if not new_id:
                _reg_clear(tg_id)
                try:
                    _bot.edit_message_text("❌ خطا در ساخت اکانت. دوباره /start بزنید.", chat_id=call.message.chat.id, message_id=call.message.message_id)
                except Exception:
                    pass
                return

            db.init_user_settings(new_id)
            db.set_setting(new_id, "session_data", saved_session)
            db.set_setting(new_id, "logged_in", "1")
            db.save_telegram_user_id(new_id, tg_id)

            # هدیه خوش‌آمد
            db.add_tokens(new_id, config.WELCOME_TOKENS)

            # ─── اتصال پلن خریداری‌شده به اکانت ─────────────────────────
            payment_id = session.get("payment_id")
            if payment_id and session.get("payment_approved"):
                try:
                    payment = db.get_payment(payment_id)
                    plan_key = payment.get("plan", "weekly") if payment else "weekly"
                    days = PLANS_NEW.get(plan_key, {"days": 7})["days"]
                    db.set_subscription(new_id, plan_key, days)
                    db.update_payment(payment_id, owner_id=new_id)
                    print(f"✅ پلن {plan_key} به اکانت {new_id} متصل شد")
                except Exception as _e:
                    print(f"⚠️ خطا در اتصال پلن: {_e}")
            else:
                # اگر پلن خریداری نشده بود، اشتراک رایگان یک‌روزه
                try:
                    if not db.get_subscription(new_id):
                        db.set_subscription(new_id, "free_trial", 1)
                except Exception as _e:
                    print(f"⚠️ set free_trial on register: {_e}")

            _reg_clear(tg_id)

            def _start_new(_acc_id, _tg_id):
                time.sleep(1.5)
                try:
                    from bot import bot_manager
                    from app import get_loop
                    bot_manager.start(_acc_id, get_loop(), check_tokens=False)
                except Exception as _e:
                    print(f"⚠️ bot_manager.start (new): {_e}")
                threading.Timer(86400, _notify_subscription_expired, args=[_acc_id, _tg_id]).start()
            threading.Thread(target=_start_new, args=(new_id, tg_id), daemon=True).start()

            site_url = getattr(config, "SITE_URL", "")
            markup_done = types.InlineKeyboardMarkup()
            if site_url:
                markup_done.add(types.InlineKeyboardButton("🌐 ورود به پنل وب", url=site_url, style="primary"))

            try:
                _bot.edit_message_text(
                    f"🎉 <b>اکانت ساخته شد!</b>\n\n"
                    f"👤 نام: <b>{tg_user['name']}</b>\n"
                    f"🔑 یوزرنیم پنل: <code>{candidate}</code>\n"
                    f"🔒 رمز عبور: همان رمزی که وارد کردید\n\n"
                    f"🎁 <b>{config.WELCOME_TOKENS} الماس</b> هدیه خوش‌آمد دریافت کردید!\n"
                    f"✅ سلف‌بات در حال اتصال است — چند لحظه صبر کنید.",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup_done,
                )
            except Exception:
                pass

            ref_tg_id = session.get("referrer_tg_id")
            if ref_tg_id:
                threading.Thread(target=_process_referral_async, args=(ref_tg_id, tg_id_val), daemon=True).start()

        except Exception as e:
            _reg_clear(tg_id)
            try:
                _bot.edit_message_text(f"❌ خطا: {str(e)[:300]}\n\nدوباره /start بزنید.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            except Exception:
                pass

# ─── لغو فرایند ────────────────────────────────────────────────────────
@_bot.callback_query_handler(func=lambda call: call.data == "reg_cancel")
def callback_reg_cancel(call):
    tg_id = call.from_user.id
    _reg_clear(tg_id)
    _bot.answer_callback_query(call.id)
    try:
        _bot.edit_message_text("❌ فرایند ثبت‌نام لغو شد.\n\nبرای شروع مجدد /start بزنید.", chat_id=call.message.chat.id, message_id=call.message.message_id)
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════════════════
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

        # ─── کاربر ثبت‌نام نکرده → فقط منوی خرید پلن ─────────────────────
        if not account:
            # ذخیره کد رفرال در سشن در صورت وجود
            if ref_code and ref_code.startswith("ref_"):
                try:
                    referrer_tg = int(ref_code[4:])
                    _reg_sessions[tg_id] = _reg_sessions.get(tg_id, {})
                    _reg_sessions[tg_id]["referrer_tg_id"] = referrer_tg
                except Exception:
                    pass

            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("💎 خرید پلن هفتگی (7 روز) — 22,500 تومان", callback_data="new_plan_weekly", style="primary"),
                types.InlineKeyboardButton("💎 خرید پلن ماهانه (30 روز) — 90,000 تومان", callback_data="new_plan_monthly", style="primary"),
                types.InlineKeyboardButton("💎 خرید پلن دو ماهه (60 روز) — 180,000 تومان", callback_data="new_plan_bimonthly", style="primary"),
            )
            markup.add(
                types.InlineKeyboardButton("📞 پشتیبانی: @amele55", url="https://t.me/amele55", style="primary")
            )
            _bot.reply_to(
                message,
                "👋 <b>سلام!</b>\n\n"
                "⚠️ <b>ابتدا پلن خود را خریداری کنید</b>، سپس می‌توانید ثبت‌نام کنید.\n\n"
                "💡 <b>دلیل:</b> به دلیل محدودیت منابع سرور، ابتدا باید پلن تهیه کنید.\n\n"
                "👇 یکی از پلن‌های زیر را انتخاب کنید:\n\n"
                "📞 برای نکات تکمیلی به آیدی <b>@amele55</b> پیام دهید.",
                reply_markup=markup,
                parse_mode="HTML"
            )
            return

        # ─── کاربر ثبت‌نام کرده → فلوی قبلی ─────────────────────────────
        try:
            if not db.get_subscription(account["id"]):
                threading.Thread(target=_grant_free_trial, args=[account["id"], tg_id], daemon=True).start()
        except Exception:
            pass

        if message.chat.type == 'private':
            is_logged_in = db.get_setting(account["id"], "logged_in", "0") == "1"
            if not is_logged_in:
                kb_reconnect = types.InlineKeyboardMarkup(row_width=1)
                kb_reconnect.add(
                    types.InlineKeyboardButton("🤖 وصل کردن سلف", callback_data="reg_start", style="success")
                )
                _bot.reply_to(
                    message,
                    f"👋 سلام <b>{account['username']}</b>!\n\n"
                    "⚠️ <b>سلف شما به اکانت وصل نیست.</b>\n"
                    "برای وصل کردن دوباره دکمه زیر را بزنید:",
                    parse_mode="HTML",
                    reply_markup=kb_reconnect
                )
                return

        stats = db.get_token_stats(account["id"])
        sub = db.get_subscription(account["id"])
        now_tehran = _now_tehran().strftime("%Y/%m/%d — %H:%M")

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
            kb_markup = _owner_keyboard() if tg_id == OWNER_TG_ID else _user_keyboard()
        else:
            kb_markup = None

        default_welcome = (
            "👋 سلام {name}!\n\n"
            "🕐 وقت تهران: {time}\n\n"
            "💎 موجودی الماس: {balance}\n"
            "📊 کل دریافتی: {total_earned}\n\n"
            "📦 اشتراک سلف:\n{sub_status}"
        )
        welcome_template = db.get_global_setting("welcome_text", default_welcome)
        tg_user = message.from_user
        full_name = ((tg_user.first_name or "") + (" " + tg_user.last_name if tg_user.last_name else "")).strip()
        mention = f"<a href='tg://user?id={tg_id}'>{full_name or account['username']}</a>"
        welcome_text = welcome_template.format(
            name=account["username"],
            name_full=full_name or account["username"],
            mention=mention,
            tag=f"@{account['username']}",
            tg_id=tg_id,
            time=now_tehran,
            balance=stats["balance"],
            total_earned=stats["total_earned"],
            sub_status=sub_status,
        )

        welcome_photo = db.get_global_setting("welcome_photo_id", "")

        if welcome_photo and message.chat.type == 'private':
            _bot.send_photo(
                message.chat.id,
                welcome_photo,
                caption=welcome_text,
                reply_markup=kb_markup
            )
        else:
            _bot.reply_to(message, welcome_text, reply_markup=kb_markup)

        if message.chat.type == 'private':
            _bot.send_message(message.chat.id, "📋 منوی اصلی:", reply_markup=_main_inline_keyboard(account))

        if message.chat.type == 'private':
            sponsors = getattr(config, 'SPONSORS', [])
            if sponsors:
                sponsors_text = "🤝 <b>اسپانسرهای رسمی پروژه:</b>\n"
                for sp in sponsors:
                    sponsors_text += f"🔸 @{sp['username']}\n"
                sponsors_text += f"\n👑 <b>مالک:</b> @{config.OWNER_USERNAME}\n🛟 <b>پشتیبانی:</b> @{getattr(config, 'SUPPORT_USERNAME', 'll_x_yasi')}"
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

# ══════════════════════════════════════════════════════════════════════════════
# Callback: بررسی عضویت
# ══════════════════════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════════════════════
# 🛒 سیستم خرید و اشتراک (برای کاربران ثبت‌نام‌شده)
# ══════════════════════════════════════════════════════════════════════════════
MONTHLY_TOMAN = 90_000
PLANS = {
    "weekly": {"fa": "هفتگی", "days": 7, "toman": MONTHLY_TOMAN // 4, "diamonds": 100},
    "monthly": {"fa": "ماهانه", "days": 30, "toman": MONTHLY_TOMAN, "diamonds": 360},
    "bimonthly": {"fa": "دو ماهه", "days": 60, "toman": MONTHLY_TOMAN * 2, "diamonds": 700},
}
DIAMOND_RATE = 250
DIAMOND_MIN_BUY = 100

_purchase_states = {}

def _get_card_number():
    return db.get_global_setting("card_number", "----")

def _purchase_main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💎 خرید اشتراک با الماس", callback_data="pur_sub_diamond", style="success"),
    )
    markup.add(
        types.InlineKeyboardButton("💳 خرید اشتراک با کارت", callback_data="pur_sub_card", style="primary"),
    )
    markup.add(
        types.InlineKeyboardButton("🛍 خرید الماس", callback_data="pur_buy_diamond", style="success"),
    )
    return markup

def _plans_keyboard(prefix: str):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, p in PLANS.items():
        markup.add(types.InlineKeyboardButton(
            f"{p['fa']} — {p['toman']:,} تومان / {p['diamonds']} الماس",
            callback_data=f"{prefix}_{key}",
            style="primary"
        ))
    markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_back", style="danger"))
    return markup

@_bot.message_handler(func=lambda m: m.text and m.text.strip() in ("🛒 خرید الماس", "🛒 خرید"), chat_types=['private'])
def cmd_buy(message):
    _do_buy(message.from_user.id, message.chat.id, reply_to=message.message_id)

@_bot.callback_query_handler(func=lambda call: call.data == "menu_buy")
def callback_menu_buy(call):
    _bot.answer_callback_query(call.id)
    _do_buy(call.from_user.id, call.message.chat.id)

def _do_buy(tg_id, chat_id, reply_to=None):
    try:
        account = _get_account_cached(tg_id)
        if not account:
            return _bot.send_message(chat_id, "❌ ابتدا در پنل وب ثبت‌نام کنید.", reply_markup=_main_inline_keyboard())
        balance = db.get_token_balance(account["id"])
        kwargs = {"reply_markup": _purchase_main_keyboard()}
        if reply_to:
            kwargs["reply_to_message_id"] = reply_to
        _bot.send_message(chat_id,
            f"🛒 <b>منوی خرید</b>\n\n"
            f"💎 موجودی فعلی شما: <b>{balance} الماس</b>\n\n"
            f"یکی از گزینه‌های زیر را انتخاب کنید:",
            **kwargs)
    except Exception as e:
        print(f"❌ خطا در _do_buy: {e}")

@_bot.callback_query_handler(func=lambda call: call.data.startswith("pur_"))
def callback_purchase(call):
    try:
        data = call.data
        tg_id = call.from_user.id
        account = _get_account_cached(tg_id)
        if not account:
            return _bot.answer_callback_query(call.id, "❌ ابتدا در پنل وب ثبت‌نام کنید.", show_alert=True)

        if data == "pur_back":
            balance = db.get_token_balance(account["id"])
            _purchase_states.pop(tg_id, None)
            return _bot.edit_message_text(
                f"🛒 <b>منوی خرید</b>\n\n💎 موجودی: <b>{balance} الماس</b>\n\nیکی از گزینه‌های زیر را انتخاب کنید:",
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                reply_markup=_purchase_main_keyboard()
            )

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
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🛍 خرید الماس", callback_data="pur_buy_diamond", style="success"))
                markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_sub_diamond", style="danger"))
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
                    reply_markup=markup
                )
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
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_sub_card", style="danger"))
            _bot.edit_message_text(
                f"💳 <b>پرداخت اشتراک {plan['fa']}</b>\n\n"
                f"💰 مبلغ: <b>{plan['toman']:,} تومان</b>\n"
                f"💳 شماره کارت: <code>{card}</code>\n"
                f"👤 به نام: <b>غفاری</b>\n\n"
                f"بعد از واریز، تصویر رسید را ارسال کنید 👇",
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                reply_markup=markup
            )
            _bot.answer_callback_query(call.id)

        elif data == "pur_buy_diamond":
            card = _get_card_number()
            _purchase_states[tg_id] = {"step": "waiting_diamond_amount"}
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="pur_back", style="danger"))
            _bot.edit_message_text(
                f"🛍 <b>خرید الماس</b>\n\n"
                f"💎 نرخ: هر ۱۰۰ الماس = <b>{100 * DIAMOND_RATE:,} تومان</b>\n"
                f"📌 حداقل خرید: <b>{DIAMOND_MIN_BUY} الماس</b>\n\n"
                f"چه تعداد الماس می‌خوای؟ (عدد بنویس)\n"
                f"مثال: <code>200</code>",
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                reply_markup=markup
            )
            _bot.answer_callback_query(call.id)

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
                        types.InlineKeyboardButton("✅ تأیید شد", callback_data="noop", style="success")
                    )
                )
                _bot.answer_callback_query(call.id, "✅ پرداخت تأیید شد!", show_alert=True)

            else:
                db.update_payment(payment_id, status="rejected")
                try:
                    _bot.send_message(
                        payment["tg_id"],
                        "❌ <b>پرداخت شما رد شد.</b>\n\nلطفاً با پشتیبانی تماس بگیرید: @" + getattr(config, 'SUPPORT_USERNAME', 'll_x_yasi')
                    )
                except Exception: pass
                _bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("❌ رد شد", callback_data="noop", style="danger")
                    )
                )
                _bot.answer_callback_query(call.id, "❌ پرداخت رد شد", show_alert=True)

        elif data == "noop":
            _bot.answer_callback_query(call.id)

    except Exception as e:
        print(f"❌ خطا در callback_purchase: {e}")
        _bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:80]}", show_alert=True)

# ─── دریافت پیام‌های مرتبط با خرید ─────────────────────────────────────
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

        # ── کاربر تعداد الماس رو نوشت ───────────────────────────────
        if step == "waiting_diamond_amount":
            if not account:
                return
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
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("❌ لغو", callback_data="pur_back", style="danger"))
            _bot.reply_to(message,
                f"🛍 <b>خرید {amount} الماس</b>\n\n"
                f"💰 مبلغ: <b>{toman:,} تومان</b>\n"
                f"💳 شماره کارت: <code>{card}</code>\n"
                f"👤 به نام: <b>غفاری</b>\n\n"
                f"بعد از واریز، تصویر رسید را ارسال کنید 👇",
                reply_markup=markup
            )

        # ── کاربر رسید پلن جدید فرستاد (قبل از ثبت‌نام) ────────────
        elif step == "waiting_receipt_new":
            payment_id = state.get("payment_id")
            if not payment_id:
                return

            file_id = None
            if message.photo:
                file_id = message.photo[-1].file_id
            elif message.document:
                file_id = message.document.file_id
            else:
                return _bot.reply_to(message, "❌ لطفاً تصویر رسید را ارسال کنید.")

            db.update_payment(payment_id, receipt_file_id=file_id)
            payment = db.get_payment(payment_id)

            username = message.from_user.username
            user_display = f"@{username}" if username else str(tg_id)
            
            plan_info = state.get("plan_info", {})
            desc = f"پلن {plan_info.get('fa', '')} — {plan_info.get('toman', 0):,} تومان"

            admin_text = (
                f"🧾 <b>رسید جدید — ثبت‌نام</b>\n\n"
                f"👤 کاربر: {user_display}\n"
                f"🆔 تلگرام: <code>{tg_id}</code>\n"
                f"📦 نوع: {desc}\n"
                f"🔢 شناسه پرداخت: <code>{payment_id}</code>\n\n"
                f"⚠️ <b>تایید = ثبت‌نام کاربر در سیستم</b>"
            )
            admin_markup = types.InlineKeyboardMarkup(row_width=2)
            admin_markup.add(
                types.InlineKeyboardButton("✅ تأیید و ثبت‌نام", callback_data=f"new_approve_{payment_id}", style="success"),
            )
            admin_markup.add(
                types.InlineKeyboardButton("❌ رد", callback_data=f"new_reject_{payment_id}", style="danger")
            )
            try:
                admin_msg = _bot.send_photo(
                    OWNER_TG_ID, file_id,
                    caption=admin_text,
                    reply_markup=admin_markup,
                    parse_mode="HTML"
                )
                db.update_payment(payment_id, admin_msg_id=admin_msg.message_id)
            except Exception as e:
                print(f"❌ ارسال رسید به ادمین: {e}")

            _purchase_states.pop(tg_id, None)
            _bot.reply_to(
                message,
                "✅ <b>رسید دریافت شد!</b>\n\n"
                "⏳ پس از تأیید توسط ادمین، وارد فرآیند ثبت‌نام می‌شوید.\n"
                "معمولاً کمتر از ۳۰ دقیقه طول می‌کشد.",
                parse_mode="HTML"
            )

        # ── کاربر رسید فرستاد (برای کاربران ثبت‌نام‌شده) ───────────
        elif step in ("waiting_receipt_sub", "waiting_receipt_diamond"):
            if not account:
                return
            payment_id = state.get("payment_id")
            if not payment_id:
                return

            file_id = None
            if message.photo:
                file_id = message.photo[-1].file_id
            elif message.document:
                file_id = message.document.file_id
            else:
                return _bot.reply_to(message, "❌ لطفاً تصویر رسید را ارسال کنید.")

            db.update_payment(payment_id, receipt_file_id=file_id)
            payment = db.get_payment(payment_id)

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
                types.InlineKeyboardButton("✅ تأیید", callback_data=f"pur_approve_{payment_id}", style="success"),
            )
            admin_markup.add(
                types.InlineKeyboardButton("❌ رد", callback_data=f"pur_reject_{payment_id}", style="danger")
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

# ─── توابع کمکی ───────────────────────────────────────────────────────────────
def _grant_free_trial(account_id: int, tg_id: int):
    """یک روز سلف رایگان برای کاربران جدید"""
    try:
        existing = db.get_subscription(account_id)
        if existing:
            return
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
            return
        site_url = getattr(config, "SITE_URL", "")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🛒 تمدید اشتراک", callback_data="pur_sub_diamond", style="success"))
        if site_url:
            markup.add(types.InlineKeyboardButton("🌐 پنل وب", url=site_url, style="primary"))
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
                time.sleep(1800)
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
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🛒 تمدید اشتراک", callback_data="pur_sub_diamond", style="success"))
                _bot.send_message(
                    tg_id,
                    f"⚠️ <b>اشتراک شما در حال انقضاست!</b>\n\n"
                    f"⏰ باقی‌مانده: <b>{remaining}</b>\n\n"
                    f"برای تمدید همین الان اقدام کنید 👇",
                    reply_markup=markup
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

# ══════════════════════════════════════════════════════════════════════════════
# ✅ پیام‌های ناشناخته
# ══════════════════════════════════════════════════════════════════════════════
@_bot.message_handler(func=lambda m: True, chat_types=['private'])
def cmd_unknown(message):
    try:
        account = _get_account_cached(message.from_user.id)
        if not account:
            # کاربر ثبت‌نام نکرده → منوی خرید پلن
            markup = types.InlineKeyboardMarkup(row_width=1)
            markup.add(
                types.InlineKeyboardButton("💎 خرید پلن هفتگی (7 روز) — 22,500 تومان", callback_data="new_plan_weekly", style="primary"),
                types.InlineKeyboardButton("💎 خرید پلن ماهانه (30 روز) — 90,000 تومان", callback_data="new_plan_monthly", style="primary"),
                types.InlineKeyboardButton("💎 خرید پلن دو ماهه (60 روز) — 180,000 تومان", callback_data="new_plan_bimonthly", style="primary"),
            )
            markup.add(
                types.InlineKeyboardButton("📞 پشتیبانی: @amele55", url="https://t.me/amele55", style="primary")
            )
            return _bot.reply_to(
                message,
                "⚠️ <b>ابتدا پلن خود را خریداری کنید</b>، سپس می‌توانید ثبت‌نام کنید.\n\n"
                "💡 <b>دلیل:</b> به دلیل محدودیت منابع سرور، ابتدا باید پلن تهیه کنید.\n\n"
                "👇 یکی از پلن‌های زیر را انتخاب کنید:",
                reply_markup=markup,
                parse_mode="HTML"
            )
        
        kb = _owner_keyboard() if message.from_user.id == OWNER_TG_ID else _user_keyboard()
        _bot.reply_to(message, "⚠️ دستور نامعتبر. از دکمه‌های زیر استفاده کنید:", reply_markup=kb)
    except Exception as e:
        print(f"❌ خطا در cmd_unknown: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# Polling
# ══════════════════════════════════════════════════════════════════════════════
def _polling_loop():
    while True:
        try:
            _bot.infinity_polling(
                timeout=10,
                long_polling_timeout=5,
                restart_on_change=False,
                skip_pending=True,
                interval=0
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
