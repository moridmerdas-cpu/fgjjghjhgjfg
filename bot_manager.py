# bot_manager.py
# مدیریت پیشرفته بات‌ها با سیستم Heartbeat و Auto Reconnect

import asyncio
import threading
import time
from typing import Dict, Optional, Set, List
import database as db
import config
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError,
    RPCError,
    UnauthorizedError,
)
import redis_cache as rc


class AdvancedBotManager:
    """
    مدیریت پیشرفته بات‌ها با:
    - Heartbeat برای بررسی زنده بودن
    - Auto Reconnect با Exponential Backoff
    - Duplicate Protection
    - Queue برای تسک‌ها
    - مدیریت خطاهای کامل
    """
    
    def __init__(self):
        self._bots: Dict[int, dict] = {}  # owner_id -> {client, task, stop, ...}
        self._timers: Dict[int, threading.Timer] = {}
        self._lock = threading.Lock()
        self._hb_manager = None  # در ابتدا None، بعداً مقداردهی می‌شود
        self._task_queue = None
        self._started = False
        self._heartbeat_interval = 30  # هر ۳۰ ثانیه
        self._max_retries = 10
        self._base_retry_delay = 3
        
    def _get_hb_manager(self):
        """دریافت یا ساخت Heartbeat Manager"""
        if self._hb_manager is None:
            from heartbeat import get_heartbeat_manager
            self._hb_manager = get_heartbeat_manager()
        return self._hb_manager
    
    def _get_redis(self):
        """دریافت اتصال Redis"""
        if self._task_queue is None:
            self._task_queue = rc.get_redis()
        return self._task_queue
    
    def is_running(self, owner_id: int) -> bool:
        """بررسی آیا یک اکانت در حال اجراست"""
        with self._lock:
            entry = self._bots.get(owner_id)
            if not entry:
                return False
            
            # بررسی stop flag
            if entry.get("stop", False):
                return False
            
            # بررسی heartbeat
            hb = self._get_hb_manager()
            if not hb.is_alive(owner_id):
                # اگر heartbeat مرده است، اکانت را پاک کن
                self._cleanup_bot(owner_id)
                return False
            
            return True
    
    def get_client(self, owner_id: int):
        """دریافت کلاینت یک اکانت"""
        with self._lock:
            entry = self._bots.get(owner_id)
            return entry.get("client") if entry else None
    
    def get_all_running(self) -> List[int]:
        """دریافت لیست همه اکانت‌های در حال اجرا"""
        hb = self._get_hb_manager()
        return hb.get_all_alive()
    
    def start(self, owner_id: int, loop: asyncio.AbstractEventLoop, check_tokens: bool = True, is_restart: bool = False) -> bool:
        """شروع یک اکانت با بررسی‌های کامل"""
        
        print(f"🚀 [{owner_id}] شروع فرآیند استارت{'(ریستارت)' if is_restart else ''}...")
        
        # ─── ۱. Duplicate Protection ──────────────────────────────────────────
        # اگر اکانت در حال اجراست، آن را متوقف کن
        if self.is_running(owner_id):
            print(f"⚠️ [{owner_id}] اکانت در حال اجراست، متوقف می‌شود...")
            self.stop(owner_id)
            # صبر کوتاه برای پاک شدن کامل
            time.sleep(0.5)
        
        # ─── ۲. بررسی اشتراک ──────────────────────────────────────────────────
        tg_id = db.get_telegram_id_by_owner(owner_id)
        is_owner = (tg_id is not None and tg_id == config.OWNER_TG_ID)
        
        if not is_owner and not db.is_subscribed(owner_id):
            print(f"⛔ [{owner_id}] اشتراک منقضی شده")
            return False
        
        # ─── ۳. بررسی توکن ────────────────────────────────────────────────────
        tokens_deducted = 0
        if config.BOT_TOKEN and check_tokens and not is_owner:
            balance = db.get_token_balance(owner_id)
            if balance < config.TOKENS_PER_SESSION:
                print(f"❌ [{owner_id}] توکن کافی نیست: {balance} < {config.TOKENS_PER_SESSION}")
                return False
            db.deduct_tokens(owner_id, config.TOKENS_PER_SESSION)
            tokens_deducted = config.TOKENS_PER_SESSION
            print(f"💰 [{owner_id}] {tokens_deducted} توکن کسر شد")
        
        # ─── ۴. ساخت entry جدید ──────────────────────────────────────────────
        entry = {
            "client": None,
            "task": None,
            "stop": False,
            "is_owner": is_owner,
            "tokens_deducted": tokens_deducted,
            "owner_refunded": False,
            "paused": False,
            "retry_count": 0,
            "start_time": time.time(),
            "last_heartbeat": time.time(),
        }
        
        with self._lock:
            self._bots[owner_id] = entry
        
        # ─── ۵. استارت بات در event loop ─────────────────────────────────────
        try:
            task = asyncio.run_coroutine_threadsafe(
                self._run_bot_advanced(owner_id, loop),
                loop
            )
            entry["task"] = task
        except Exception as e:
            print(f"❌ [{owner_id}] خطا در استارت تسک: {e}")
            with self._lock:
                self._bots.pop(owner_id, None)
            return False
        
        # ─── ۶. ثبت در Heartbeat ─────────────────────────────────────────────
        hb = self._get_hb_manager()
        hb.register(owner_id)
        
        # ─── ۷. تایمر انقضا (برای کاربران غیرمالک) ──────────────────────────
        if config.BOT_TOKEN and not is_owner:
            self._cancel_timer(owner_id)
            timer = threading.Timer(
                config.SESSION_HOURS * 3600,
                self.stop,
                args=[owner_id]
            )
            timer.daemon = True
            timer._timer_start = time.time()  # ✅ برای محاسبه دقیق زمان باقی‌مانده
            timer.start()
            self._timers[owner_id] = timer
            print(f"⏱️ [{owner_id}] تایمر {config.SESSION_HOURS} ساعته تنظیم شد")
        
        # ─── ۸. تایمر چک اشتراک (برای کاربران غیرمالک) ──────────────────────
        if not is_owner:
            self._start_subscription_watcher(owner_id)
        
        print(f"✅ [{owner_id}] بات با موفقیت استارت شد")
        return True
    
    def _cancel_timer(self, owner_id: int):
        """لغو تایمر انقضا"""
        timer = self._timers.pop(owner_id, None)
        if timer:
            timer.cancel()
            print(f"⏹️ [{owner_id}] تایمر لغو شد")
    
    def stop(self, owner_id: int):
        """متوقف کردن یک اکانت"""
        print(f"⏹ [{owner_id}] در حال توقف...")
        
        # ─── ۱. لغو تایمرها ──────────────────────────────────────────────────
        self._cancel_timer(owner_id)
        
        # ─── ۲. لغو watcher اشتراک ──────────────────────────────────────────
        if hasattr(self, '_sub_watchers'):
            w = self._sub_watchers.pop(owner_id, None)
            if w:
                w.cancel()
        
        # ─── ۳. حذف از Heartbeat ────────────────────────────────────────────
        hb = self._get_hb_manager()
        hb.unregister(owner_id)
        
        # ─── ۴. متوقف کردن تسک ──────────────────────────────────────────────
        with self._lock:
            entry = self._bots.get(owner_id)
            if entry:
                entry["stop"] = True
                client = entry.get("client")
                if client and client.is_connected():
                    try:
                        # ایجاد یک event loop جدید برای disconnect
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        loop.run_until_complete(client.disconnect())
                        loop.close()
                    except Exception as e:
                        print(f"⚠️ [{owner_id}] خطا در disconnect: {e}")
        
        # ─── ۵. حذف از لیست ──────────────────────────────────────────────────
        with self._lock:
            self._bots.pop(owner_id, None)
        
        print(f"✅ [{owner_id}] بات متوقف شد")
    
    def stop_all(self):
        """متوقف کردن همه اکانت‌ها"""
        print("🛑 توقف همه اکانت‌ها...")
        with self._lock:
            owners = list(self._bots.keys())
        
        for oid in owners:
            self.stop(oid)
        
        hb = self._get_hb_manager()
        hb.stop()
        print("✅ همه اکانت‌ها متوقف شدند")
    
    def pause(self, owner_id: int):
        """متوقف کردن عملیات سلف (اتصال تلگرام نگه داشته می‌شود)"""
        with self._lock:
            entry = self._bots.get(owner_id)
            if entry and not entry.get("is_owner"):
                entry["paused"] = True
                print(f"⏸️ [{owner_id}] سلف موقتاً متوقف شد")
    
    def resume(self, owner_id: int):
        """از سرگیری عملیات سلف"""
        with self._lock:
            entry = self._bots.get(owner_id)
            if entry:
                entry["paused"] = False
                print(f"▶️ [{owner_id}] سلف دوباره فعال شد")
    
    def is_paused(self, owner_id: int) -> bool:
        """بررسی آیا سلف متوقف شده"""
        with self._lock:
            entry = self._bots.get(owner_id)
            return bool(entry and entry.get("paused"))
    
    def _cleanup_bot(self, owner_id: int):
        """پاک کردن یک اکانت از حافظه"""
        with self._lock:
            entry = self._bots.pop(owner_id, None)
            if entry:
                print(f"🧹 [{owner_id}] پاک شد")
    
    # ─── Subscription Watcher ──────────────────────────────────────────────────
    def _start_subscription_watcher(self, owner_id: int):
        """تایمر ۵ دقیقه‌ای برای چک اشتراک"""
        if not hasattr(self, '_sub_watchers'):
            self._sub_watchers = {}
        
        timer = threading.Timer(300, self._check_subscription, args=[owner_id])
        timer.daemon = True
        timer.start()
        self._sub_watchers[owner_id] = timer
    
    def _check_subscription(self, owner_id: int):
        """بررسی اشتراک و pause/resume"""
        if not self.is_running(owner_id):
            return
        
        entry = self._bots.get(owner_id)
        if entry and entry.get("is_owner"):
            return
        
        if not db.is_subscribed(owner_id):
            self.pause(owner_id)
        else:
            self.resume(owner_id)
        
        # چک بعدی
        self._start_subscription_watcher(owner_id)
    
    # ─── Core Bot Runner ──────────────────────────────────────────────────────
    async def _run_bot_advanced(self, owner_id: int, loop: asyncio.AbstractEventLoop):
        """اجرای بات با سیستم Auto Reconnect"""
        entry = self._bots.get(owner_id)
        if not entry:
            return
        
        retry_delay = self._base_retry_delay
        retry_count = 0
        
        while not entry["stop"]:
            try:
                # ─── ۱. دریافت Session ──────────────────────────────────────
                session_data = db.get_setting(owner_id, "session_data", "")
                if not session_data:
                    print(f"⚠️ [{owner_id}] Session یافت نشد")
                    await asyncio.sleep(10)
                    continue
                
                # ─── ۲. ساخت کلاینت ──────────────────────────────────────────
                client = TelegramClient(
                    StringSession(session_data),
                    config.API_ID,
                    config.API_HASH,
                    connection_retries=5,
                    retry_delay=2,
                    auto_reconnect=True,
                )
                entry["client"] = client
                entry["retry_count"] = 0
                
                # ─── ۳. ثبت هندلرها ──────────────────────────────────────────
                try:
                    from bot import _register_handlers
                    _register_handlers(client, owner_id, entry)
                except ImportError as e:
                    print(f"⚠️ [{owner_id}] خطا در ثبت هندلرها: {e}")
                    await asyncio.sleep(5)
                    continue
                
                # ─── ۴. اتصال ────────────────────────────────────────────────
                try:
                    await client.start()
                    me = await client.get_me()
                    print(f"✅ [{owner_id}] بات متصل شد — @{me.username or me.first_name}")
                except UnauthorizedError:
                    print(f"❌ [{owner_id}] Session نامعتبر — نیاز به لاگین مجدد")
                    db.set_setting(owner_id, "logged_in", "0")
                    db.set_setting(owner_id, "session_data", "")
                    break
                except Exception as e:
                    err_str = str(e)
                    # ✅ session باطل‌شده توسط تلگرام — دیگه retry نکن
                    if any(k in err_str for k in ("AUTH_KEY_UNREGISTERED", "SESSION_REVOKED",
                                                   "USER_DEACTIVATED", "AUTH_KEY_DUPLICATED")):
                        print(f"❌ [{owner_id}] Session باطل شده ({e}) — توقف کامل")
                        db.set_setting(owner_id, "logged_in", "0")
                        db.set_setting(owner_id, "session_data", "")
                        break
                    print(f"❌ [{owner_id}] خطا در اتصال: {e}")
                    retry_count += 1
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 120)
                    continue
                
                # ─── ۵. ذخیره Telegram ID ──────────────────────────────────
                db.save_telegram_user_id(owner_id, me.id)
                
                # ─── ۶. تشخیص مالک و برگشت توکن ──────────────────────────────
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
                        print(f"👑 [{owner_id}] مالک — {entry['tokens_deducted']} توکن برگشت")
                    print(f"👑 [{owner_id}] مالک: @{me.username} (ID: {me.id})")
                
                # ─── ۷. استارت تسک‌های پس‌زمینه ──────────────────────────────
                try:
                    from bot import _clock_loop, _scheduler_loop
                    clock_task = asyncio.ensure_future(_clock_loop(client, owner_id))
                    sched_task = asyncio.ensure_future(_scheduler_loop(client, owner_id))
                except ImportError as e:
                    print(f"⚠️ [{owner_id}] خطا در استارت تسک‌ها: {e}")
                    clock_task = None
                    sched_task = None
                
                # ─── ۸. Reset retry ──────────────────────────────────────────
                retry_delay = self._base_retry_delay
                retry_count = 0
                
                # ─── ۹. منتظر قطع شدن ──────────────────────────────────────────
                try:
                    await client.run_until_disconnected()
                except asyncio.CancelledError:
                    print(f"⚠️ [{owner_id}] تسک لغو شد")
                    break
                except Exception as e:
                    print(f"❌ [{owner_id}] خطا در run_until_disconnected: {e}")
                
                # ─── ۱۰. لغو تسک‌ها ───────────────────────────────────────────
                if clock_task:
                    clock_task.cancel()
                if sched_task:
                    sched_task.cancel()
                
                if entry["stop"]:
                    break

                # ✅ چک کن session هنوز در دیتابیس وجود داره
                try:
                    session_data = db.get_setting(owner_id, "session_data", "")
                    if not session_data:
                        print(f"⚠️ [{owner_id}] session حذف شده — توقف کامل")
                        break
                except Exception:
                    break
                
                print(f"⚠️ [{owner_id}] اتصال قطع شد، تلاش مجدد...")
                
            except asyncio.CancelledError:
                print(f"⚠️ [{owner_id}] تسک لغو شد")
                break
            except Exception as e:
                print(f"❌ [{owner_id}] خطای ناشناخته: {e}")
                retry_count += 1
                
                if retry_count > self._max_retries:
                    print(f"❌ [{owner_id}] بیش از حد مجاز تلاش ({self._max_retries}) — توقف")
                    break
            
            # ─── ۱۱. Auto Reconnect ────────────────────────────────────────────
            if not entry["stop"]:
                wait = min(retry_delay * (2 ** min(retry_count, 3)), 120)
                print(f"🔄 [{owner_id}] تلاش مجدد در {wait:.1f} ثانیه...")
                await asyncio.sleep(wait)
                retry_delay = min(retry_delay * 2, 120)
        
        print(f"🛑 [{owner_id}] بات متوقف شد")
        
        # ─── ۱۲. Cleanup ──────────────────────────────────────────────────────
        self._cleanup_bot(owner_id)
        hb = self._get_hb_manager()
        hb.unregister(owner_id)
    
    # ─── Task Queue ────────────────────────────────────────────────────────────
    def enqueue_task(self, owner_id: int, task_type: str, data: dict) -> bool:
        """افزودن تسک به Redis Queue"""
        r = self._get_redis()
        if not r:
            print(f"⚠️ [{owner_id}] Redis در دسترس نیست")
            return False
        
        try:
            import json
            task = {
                "owner_id": owner_id,
                "type": task_type,
                "data": data,
                "timestamp": time.time()
            }
            r.rpush(f"queue:{owner_id}", json.dumps(task))
            print(f"📋 [{owner_id}] تسک {task_type} به صف اضافه شد")
            return True
        except Exception as e:
            print(f"❌ [{owner_id}] خطا در enqueue: {e}")
            return False
    
    def dequeue_task(self, owner_id: int) -> Optional[dict]:
        """دریافت تسک از Redis Queue"""
        r = self._get_redis()
        if not r:
            return None
        
        try:
            import json
            raw = r.lpop(f"queue:{owner_id}")
            if raw:
                task = json.loads(raw)
                print(f"📤 [{owner_id}] تسک {task.get('type')} از صف خارج شد")
                return task
        except Exception as e:
            print(f"❌ [{owner_id}] خطا در dequeue: {e}")
        return None
    
    def get_queue_length(self, owner_id: int) -> int:
        """دریافت تعداد تسک‌های در صف"""
        r = self._get_redis()
        if not r:
            return 0
        
        try:
            return r.llen(f"queue:{owner_id}")
        except Exception as e:
            print(f"❌ [{owner_id}] خطا در get_queue_length: {e}")
            return 0
    
    def clear_queue(self, owner_id: int) -> bool:
        """پاک کردن تمام تسک‌های یک اکانت از صف"""
        r = self._get_redis()
        if not r:
            return False
        
        try:
            r.delete(f"queue:{owner_id}")
            print(f"🧹 [{owner_id}] صف تسک‌ها پاک شد")
            return True
        except Exception as e:
            print(f"❌ [{owner_id}] خطا در clear_queue: {e}")
            return False


# ─── Singleton ──────────────────────────────────────────────────────────────────
_bot_manager: Optional[AdvancedBotManager] = None

def get_bot_manager() -> AdvancedBotManager:
    """دریافت instance مدیریت بات‌ها (Singleton)"""
    global _bot_manager
    if _bot_manager is None:
        _bot_manager = AdvancedBotManager()
        print("✅ AdvancedBotManager ایجاد شد")
    return _bot_manager


# ─── برای سازگاری با کد قدیمی ─────────────────────────────────────────────────
# این متغیر جایگزین `bot_manager` در `bot.py` و `app.py` می‌شود
bot_manager = get_bot_manager()
