"""
پاک‌سازیِ خودکارِ اکانت‌های بی‌فعالیت.

قانون: اگه یه اکانت هم «۳ روز با سلف کار نکرده باشه» (نه پیامی فرستاده نه
دستوری داده، نه توی گروه/پیویی که سلفش عضوشه پیامی رد و بدل شده) و هم
«۳ روز گردشِ مالیِ الماس نداشته باشه» (نه الماسی گرفته نه خرج کرده)، کاملاً
از سیستم پاک می‌شه:
  - سلفش (اگه در حال اجراست) متوقف می‌شه
  - سشنش پاک می‌شه
  - دارایی‌هاش صفر/حذف می‌شه
  - کلاً از دیتابیس حذف می‌شه (تنظیمات، توکن، پیام‌های ذخیره‌شده و ...)
  - آیدیِ عددیش تو جدولِ amel_deleted_accounts ثبت می‌شه تا سیستم یادش
    بمونه این کاربر قبلاً حذف شده (بدون فعالیت/اشتراک)

این پاک‌سازی باید بعد از هر بار بالا اومدنِ پروژه یک‌بار اجرا بشه (نه
مداوم/زمان‌بندی‌شده) — طبق درخواستِ صریحِ کاربر.
"""

import time

import database as db

INACTIVITY_SECONDS = 3 * 24 * 60 * 60  # ۳ روز


def purge_inactive_accounts(bot_manager=None):
    """
    روی همه‌ی اکانت‌ها می‌چرخه و هرکدوم که هم ۳ روزه با سلف کار نکرده و هم
    ۳ روزه گردشِ مالیِ الماس نداشته رو کاملاً حذف می‌کنه.

    bot_manager: اگه داده بشه، قبل از حذف سعی می‌کنه سلفِ در حالِ اجرا رو
    هم متوقف کنه (نه فقط از دیتابیس پاک کنه).

    خروجی: (تعداد بررسی‌شده، لیستِ آیدیِ عددیِ حذف‌شده‌ها)
    """
    now = time.time()
    deleted_tg_ids = []
    checked = 0

    try:
        accounts = db.get_all_accounts()
    except Exception as e:
        print(f"❌ purge_inactive_accounts: خطا در خوندنِ اکانت‌ها: {e}")
        return 0, []

    for acc in accounts:
        checked += 1
        owner_id = acc.get("id")
        tg_id = acc.get("telegram_user_id")
        created_at = acc.get("created_at")

        # اکانت‌های خیلی تازه (کمتر از ۳ روز از ثبت‌نامشون گذشته) رو دست
        # نمی‌زنیم، حتی اگه هنوز هیچ فعالیتی نداشتن — باید حداقل ۳ روز
        # فرصت داشته باشن.
        created_ts = None
        try:
            if created_at is not None:
                if hasattr(created_at, "timestamp"):
                    created_ts = created_at.timestamp()
                else:
                    # اگه رشته باشه (بعضی درایورها رشته برمی‌گردونن)
                    import datetime
                    created_ts = datetime.datetime.fromisoformat(str(created_at)).timestamp()
        except Exception:
            created_ts = None

        baseline = created_ts if created_ts else now  # اگه نامعلوم بود، محافظه‌کارانه: الان

        try:
            last_activity = db.get_last_activity_ts(owner_id)
        except Exception:
            last_activity = 0
        try:
            last_token_tx = db.get_last_token_tx_ts(owner_id)
        except Exception:
            last_token_tx = 0

        last_activity_effective = max(last_activity, baseline)
        last_token_tx_effective = max(last_token_tx, baseline)

        inactive_long_enough = (now - last_activity_effective) >= INACTIVITY_SECONDS
        no_token_flow_long_enough = (now - last_token_tx_effective) >= INACTIVITY_SECONDS

        if not (inactive_long_enough and no_token_flow_long_enough):
            continue

        # ── این اکانت واجدِ شرایطِ حذفه ──────────────────────────────────────
        print(f"🧹 پاک‌سازی: اکانت {owner_id} (tg_id={tg_id}) — {int((now - last_activity_effective) / 3600)} ساعت بی‌فعالیت و {int((now - last_token_tx_effective) / 3600)} ساعت بدون گردشِ الماس.")

        # ۱. سلف در حالِ اجرا رو متوقف کن (اگه هست)
        if bot_manager is not None:
            try:
                bot_manager.stop(owner_id)
            except Exception as e:
                print(f"⚠️ purge_inactive_accounts: خطا در متوقف کردنِ سلفِ {owner_id}: {e}")

        # ۲. دارایی رو صفر کن (قبل از حذفِ کاملِ ردیف‌ها، برای اطمینان)
        try:
            bal = db.get_token_balance(owner_id)
            if bal:
                db.deduct_tokens(owner_id, bal)
        except Exception:
            pass

        # ۳. حذفِ کاملِ اکانت از دیتابیس (شاملِ سشن که خودش یه کلید توی
        # amel_settings هست) + ثبتِ آیدیِ عددیش
        try:
            ok = db.delete_account_completely(owner_id, tg_id=tg_id, reason="inactive_3d_no_tokens")
            if ok:
                deleted_tg_ids.append(tg_id)
                print(f"✅ اکانت {owner_id} (tg_id={tg_id}) کاملاً پاک شد.")
        except Exception as e:
            print(f"❌ purge_inactive_accounts: خطا در حذفِ اکانت {owner_id}: {e}")

    if deleted_tg_ids:
        print(f"🧹 پاک‌سازیِ استارت‌آپ: {len(deleted_tg_ids)} اکانتِ بی‌فعالیت از {checked} اکانتِ بررسی‌شده حذف شد.")
    else:
        print(f"🧹 پاک‌سازیِ استارت‌آپ: هیچ اکانتِ واجدِ شرایطی پیدا نشد ({checked} اکانت بررسی شد).")

    return checked, deleted_tg_ids
