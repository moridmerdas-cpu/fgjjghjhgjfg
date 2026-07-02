# redis_cache.py
# لایه کش Redis — پشتیبانی از چند سرور/اکانت Redis به‌صورت هم‌زمان
# (مثلاً چند اکانت رایگان Upstash / Redis Cloud و ...) برای جمع‌کردن سقف
# درخواست رایگان همه‌شون با هم و هم برای redundancy (اگه یکی خواب بود، بقیه کار کنن)
import os
import json
import time
import hashlib
import redis
from typing import Any, Optional, List

# ══════════════════════════════════════════════════════════════════════════════
# 🔀 پروکسی چند-Redis: هر کلید بر اساس هش‌اش به یکی از سرورها sharding می‌شه
#    (consistent hashing) تا همیشه یک کلید مشخص به همون سرور برسه — و اگه اون
#    سرور در دسترس نبود، خودکار سراغ سرور بعدی می‌ره (failover)
# ══════════════════════════════════════════════════════════════════════════════
class MultiRedisClient:
    """رابطی شبیه redis.Redis که پشت صحنه بین چند اتصال Redis پخش می‌کند."""

    def __init__(self, clients: List["redis.Redis"]):
        self._clients = clients

    def __len__(self):
        return len(self._clients)

    def _shard_index(self, key: str) -> int:
        h = int(hashlib.md5(str(key).encode()).hexdigest(), 16)
        return h % len(self._clients)

    def _ordered_clients(self, key: str) -> List["redis.Redis"]:
        """اول سروری که این کلید بهش تعلق داره، بعد بقیه به‌عنوان fallback"""
        idx = self._shard_index(key)
        return [self._clients[idx]] + [c for i, c in enumerate(self._clients) if i != idx]

    def _call(self, key: str, method: str, *args, **kwargs):
        last_err = None
        for client in self._ordered_clients(key):
            try:
                return getattr(client, method)(key, *args, **kwargs)
            except Exception as e:
                last_err = e
                continue
        if last_err:
            raise last_err
        return None

    # ── متدهای تک‌کلیدی (بر اساس کلید shard می‌شن) ─────────────────────────
    def get(self, key):
        return self._call(key, "get")

    def set(self, key, value, *a, **kw):
        return self._call(key, "set", value, *a, **kw)

    def setex(self, key, ttl, value):
        return self._call(key, "setex", ttl, value)

    def delete(self, *keys):
        ok = True
        for k in keys:
            try:
                self._call(k, "delete")
            except Exception:
                ok = False
        return ok

    def exists(self, key):
        return self._call(key, "exists")

    def expire(self, key, ttl):
        return self._call(key, "expire", ttl)

    def rpush(self, key, *values):
        return self._call(key, "rpush", *values)

    def lpush(self, key, *values):
        return self._call(key, "lpush", *values)

    def lpop(self, key):
        return self._call(key, "lpop")

    def llen(self, key):
        return self._call(key, "llen")

    def sadd(self, key, *values):
        return self._call(key, "sadd", *values)

    def srem(self, key, *values):
        return self._call(key, "srem", *values)

    def smembers(self, key):
        return self._call(key, "smembers")

    # ── متدهایی که کلید مشخصی ندارن (باید روی همه سرورها پخش بشن) ──────────
    def keys(self, pattern="*"):
        result = []
        for client in self._clients:
            try:
                result.extend(client.keys(pattern))
            except Exception:
                continue
        return result

    def ping(self):
        ok = False
        for client in self._clients:
            try:
                if client.ping():
                    ok = True
            except Exception:
                continue
        return ok


# ─── اتصال به چند سرور Redis ────────────────────────────────────────────────
_redis_pool: List["redis.Redis"] = []
_multi_client: Optional[MultiRedisClient] = None
_pool_initialized = False


def _collect_redis_urls() -> List[str]:
    """جمع‌آوری آدرس‌های Redis از env vars — دو فرمت پشتیبانی می‌شه:
    ۱) چند متغیر جدا: UPSTASH_REDIS_URL, UPSTASH_REDIS_URL_2, UPSTASH_REDIS_URL_3, ...
    ۲) یک متغیر با چند آدرس جدا شده با کاما: UPSTASH_REDIS_URLS=url1,url2,url3
    """
    urls: List[str] = []

    primary = os.environ.get("UPSTASH_REDIS_URL", "").strip()
    if primary:
        urls.append(primary)

    i = 2
    while True:
        u = os.environ.get(f"UPSTASH_REDIS_URL_{i}", "").strip()
        if not u:
            break
        urls.append(u)
        i += 1

    combined = os.environ.get("UPSTASH_REDIS_URLS", "").strip()
    if combined:
        for u in combined.split(","):
            u = u.strip()
            if u and u not in urls:
                urls.append(u)

    return urls


def _init_pool():
    global _redis_pool, _pool_initialized
    if _pool_initialized:
        return
    _pool_initialized = True

    urls = _collect_redis_urls()
    if not urls:
        print("⚠️ هیچ UPSTASH_REDIS_URL ای تنظیم نشده — بدون کش ادامه می‌دهیم")
        return

    for idx, url in enumerate(urls, start=1):
        try:
            client = redis.from_url(url, decode_responses=True, socket_timeout=2)
            client.ping()
            _redis_pool.append(client)
            print(f"✅ Redis شماره {idx} از {len(urls)} متصل شد!")
        except Exception as e:
            print(f"⚠️ Redis شماره {idx} اتصال ناموفق: {e}")

    if not _redis_pool:
        print("⚠️ هیچ‌کدام از سرورهای Redis وصل نشدند — بدون کش ادامه می‌دهیم")
    else:
        print(f"🔗 مجموعاً {len(_redis_pool)} سرور Redis فعال است (sharding + failover)")


def get_redis():
    """دریافت اتصال Redis — اگه چند سرور تنظیم شده باشه یک پروکسی چند-سرور
    برمی‌گردونه که خودکار بین‌شون sharding/failover می‌کنه. اگه هیچ‌کدوم در
    دسترس نباشن None برمی‌گردونه."""
    global _multi_client
    _init_pool()
    if not _redis_pool:
        return None
    if len(_redis_pool) == 1:
        return _redis_pool[0]
    if _multi_client is None:
        _multi_client = MultiRedisClient(_redis_pool)
    return _multi_client


def get_pool_status() -> dict:
    """وضعیت فعلی pool — چند سرور تنظیم شده و کدوم‌ها وصل‌ان (برای دیباگ/ادمین)"""
    _init_pool()
    total_configured = len(_collect_redis_urls())
    connected = len(_redis_pool)
    pings = []
    for i, c in enumerate(_redis_pool, start=1):
        try:
            c.ping()
            pings.append({"index": i, "ok": True})
        except Exception as e:
            pings.append({"index": i, "ok": False, "error": str(e)})
    return {"configured": total_configured, "connected": connected, "servers": pings}


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
    """حذف همه کلیدهایی که با pattern مطابقت دارن (روی همه‌ی سرورهای Redis)"""
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
