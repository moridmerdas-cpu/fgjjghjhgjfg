import asyncio
import threading
import time

import database_supabase as db
import config
from bot import bot_manager

# ─── event loop جداگانه برای Telethon ────────────────────────────────────────
# این event loop توسط telegram_bot.py هم استفاده می‌شود (from app import get_loop)
_loop = None


def get_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        t = threading.Thread(target=_loop.run_forever, daemon=True)
        t.start()
    return _loop


def run_async(coro):
    return asyncio.run_coroutine_threadsafe(coro, get_loop()).result(timeout=30)


# ─── اجرا ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # ۱. ایجاد جداول (اگر موجود نیستند)
    db.init_tables()
    print("✅ جداول Supabase بررسی/ایجاد شدند")

    # ۲. استارت Heartbeat Manager
    from heartbeat import get_heartbeat_manager
    hb = get_heartbeat_manager()
    hb.start()
    print("✅ Heartbeat Manager استارت شد")

    # ۳. استارت ربات توکن (ربات اصلی تلگرام)
    from telegram_bot import start_token_bot
    start_token_bot()

    # ۴. استارت بات برای همه کاربران لاگین‌شده
    loop = get_loop()
    for oid in db.get_all_logged_in_users():
        # ✅ هر کاربر جدا try/except دارد — اگر استارت یک کاربر با خطا مواجه شود
        # (مثلاً یک هیکاپ لحظه‌ای دیتابیس/تلگرام)، دیگر کاربرهای بعدی در این
        # لیست بی‌خبر نمی‌مانند و استارت‌شان متوقف نمی‌شود
        try:
            bot_manager.start(oid, loop, check_tokens=False, is_restart=True)
            print(f"🚀 بات کاربر {oid} استارت شد.")
        except Exception as e:
            print(f"❌ خطا در استارت خودکار کاربر {oid}: {e} — کاربر بعدی ادامه می‌یابد")
        # ✅ فاصله‌ی کوچک بین استارت‌ها تا تلگرام همه‌ی این اتصال‌های هم‌زمان
        # را به‌عنوان رفتار مشکوک/فلود نبیند
        time.sleep(0.3)

    # ۵. واچ‌داگ سلامت سلف‌ها — هر چند دقیقه چک می‌کند که آیا سلف هر کاربر
    #    لاگین‌شده واقعاً در حال اجراست؛ اگر نبود خودش دوباره استارتش می‌زند
    def _self_heal_watchdog():
        WATCHDOG_INTERVAL = 180  # هر ۳ دقیقه
        while True:
            time.sleep(WATCHDOG_INTERVAL)
            try:
                for oid in db.get_all_logged_in_users():
                    try:
                        if not bot_manager.is_running(oid):
                            print(f"🩺 واچ‌داگ: سلف کاربر {oid} روشن نبود — تلاش برای ری‌استارت خودکار")
                            bot_manager.start(oid, get_loop(), check_tokens=False, is_restart=True)
                    except Exception as e:
                        print(f"⚠️ واچ‌داگ: خطا در بررسی/ری‌استارت کاربر {oid}: {e}")
            except Exception as e:
                print(f"⚠️ واچ‌داگ: خطای کلی: {e}")

    threading.Thread(target=_self_heal_watchdog, daemon=True).start()
    print("✅ واچ‌داگ سلامت سلف‌ها استارت شد")

    # برنامه هیچ وب‌سروری اجرا نمی‌کند — فقط زنده نگه‌داشتن پردازش اصلی
    # (ربات تلگرام و سلف‌بات‌ها همه در threadهای پس‌زمینه در حال اجرا هستند)
    print("🤖 ربات آماده است — در حال اجرا...")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("⏹ خروج...")
