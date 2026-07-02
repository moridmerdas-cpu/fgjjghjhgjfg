# redis_cache.py
# لایه کش Redis با Upstash — جایگزین کش RAM و SQLite موقت
import os
import json
import redis
from typing import Any, Optional

# ─── اتصال به Upstash Redis ────────────────────────────────────────────────────
_redis: Optional[redis.Redis] = None

def get_redis() -> Optional[redis.Redis]:
    """دریافت اتصال Redis — اگه UPSTASH_REDIS_URL نباشه None برمی‌گردونه"""
    global _redis
    if _redis is not None:
        return _redis
    url = os.environ.get("UPSTASH_REDIS_URL", "")
    if not url:
        return None
    try:
        _redis = redis.from_url(url, decode_responses=True, socket_timeout=2)
        _redis.ping()
        print("✅ Upstash Redis متصل شد!")
        return _redis
    except Exception as e:
        print(f"⚠️ Redis اتصال ناموفق: {e} — بدون کش ادامه می‌دهیم")
        _redis = None
        return None

# ─── توابع پایه ────────────────────────────────────────────────────────────────
def rget(key: str) -> Optional[str]:
    r = get_redis()
    if not r:
        return None
    try:
        return r.get(key)
    except Exception:
        return None

def rset(key: str, value: str, ttl: int = 300):
    """ذخیره در Redis با TTL ثانیه (پیش‌فرض ۵ دقیقه)"""
    r = get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, value)
    except Exception:
        pass

def rdel(key: str):
    r = get_redis()
    if not r:
        return
    try:
        r.delete(key)
    except Exception:
        pass

def rdel_pattern(pattern: str):
    """حذف همه کلیدهایی که با pattern مطابقت دارن"""
    r = get_redis()
    if not r:
        return
    try:
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        pass

def rget_json(key: str) -> Optional[Any]:
    raw = rget(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None

def rset_json(key: str, value: Any, ttl: int = 300):
    try:
        rset(key, json.dumps(value, ensure_ascii=False, default=str), ttl)
    except Exception:
        pass

# ─── TTL های استاندارد (ثانیه) ────────────────────────────────────────────────
TTL_SETTING   = 600    # تنظیمات کاربر — ۱۰ دقیقه
TTL_SUBSCRIBE = 120    # وضعیت اشتراک — ۲ دقیقه (چون حساسه)
TTL_TOKEN     = 60     # موجودی توکن — ۱ دقیقه
TTL_ENEMIES   = 300    # لیست دشمن — ۵ دقیقه
TTL_FRIENDS   = 300    # لیست دوست — ۵ دقیقه
TTL_SILENT    = 300    # سایلنت — ۵ دقیقه
TTL_CHANNELS  = 600    # چنل‌های اجباری — ۱۰ دقیقه
TTL_ACCOUNT   = 300    # اطلاعات اکانت — ۵ دقیقه

# ─── کلیدهای Redis ────────────────────────────────────────────────────────────
def k_setting(owner_id: int, key: str) -> str:
    return f"stg:{owner_id}:{key}"

def k_all_settings(owner_id: int) -> str:
    return f"stg:{owner_id}:*"

def k_subscribe(owner_id: int) -> str:
    return f"sub:{owner_id}"

def k_token(owner_id: int) -> str:
    return f"tok:{owner_id}"

def k_enemies(owner_id: int) -> str:
    return f"enm:{owner_id}"

def k_friends(owner_id: int) -> str:
    return f"frn:{owner_id}"

def k_silent_chats(owner_id: int) -> str:
    return f"sltc:{owner_id}"

def k_silent_users(owner_id: int) -> str:
    return f"sltu:{owner_id}"

def k_forced_channels() -> str:
    return "fc:list"

def k_account(owner_id: int) -> str:
    return f"acc:{owner_id}"

# ─── توابع invalidation ────────────────────────────────────────────────────────
def invalidate_setting(owner_id: int, key: str):
    rdel(k_setting(owner_id, key))

def invalidate_all_settings(owner_id: int):
    rdel_pattern(k_all_settings(owner_id))

def invalidate_subscribe(owner_id: int):
    rdel(k_subscribe(owner_id))

def invalidate_token(owner_id: int):
    rdel(k_token(owner_id))

def invalidate_enemies(owner_id: int):
    rdel(k_enemies(owner_id))

def invalidate_friends(owner_id: int):
    rdel(k_friends(owner_id))

def invalidate_silent(owner_id: int):
    rdel(k_silent_chats(owner_id))
    rdel(k_silent_users(owner_id))

def invalidate_forced_channels():
    rdel(k_forced_channels())
# ─── اضافات جدید برای سیستم Queue و Heartbeat ─────────────────────────────────

# TTL‌های جدید
TTL_HEARTBEAT = 60   # ۶۰ ثانیه برای Heartbeat
TTL_QUEUE = 3600     # ۱ ساعت برای تسک‌های Queue

def k_queue(owner_id: int) -> str:
    return f"queue:{owner_id}"

def k_heartbeat(owner_id: int) -> str:
    return f"hb:{owner_id}"

def k_active_bots() -> str:
    return "active_bots:set"

# توابع جدید برای مدیریت Queue
def push_task(owner_id: int, task_type: str, data: dict) -> bool:
    """افزودن تسک به Queue"""
    r = get_redis()
    if not r:
        return False
    try:
        import json
        task = {
            "type": task_type,
            "data": data,
            "timestamp": time.time()
        }
        r.rpush(k_queue(owner_id), json.dumps(task))
        return True
    except Exception:
        return False

def pop_task(owner_id: int) -> Optional[dict]:
    """دریافت تسک از Queue"""
    r = get_redis()
    if not r:
        return None
    try:
        import json
        raw = r.lpop(k_queue(owner_id))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None

def get_queue_length(owner_id: int) -> int:
    """تعداد تسک‌های در صف"""
    r = get_redis()
    if not r:
        return 0
    try:
        return r.llen(k_queue(owner_id))
    except Exception:
        return 0
