"""An in-memory stand-in for redis.asyncio, shared by the x402 settlement tests.

Covers the surface `swarm_core.x402.settle` / `.burn` touch: hash, set, zset,
list, and a transactional pipeline that applies all-or-nothing (modelling
MULTI/EXEC — a failure part-way discards the whole transaction). Values come
back as `str`, like a real client with `decode_responses=True`.

Not named `test_*`, so pytest does not try to collect it.
"""
from __future__ import annotations

import copy


class FakePipeline:
    def __init__(self, parent: "FakeRedis"):
        self.parent = parent
        self.ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self.ops.append((name, args, kwargs))
            return self
        return queue

    async def execute(self):
        snap = (copy.deepcopy(self.parent.h), copy.deepcopy(self.parent.s),
                copy.deepcopy(self.parent.z), copy.deepcopy(self.parent.l))
        try:
            out = []
            for name, args, kwargs in self.ops:
                out.append(await getattr(self.parent, name)(*args, **kwargs))
            self.ops.clear()
            return out
        except Exception:
            (self.parent.h, self.parent.s,
             self.parent.z, self.parent.l) = snap
            self.ops.clear()
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRedis:
    def __init__(self):
        self.h: dict[str, dict[str, str]] = {}
        self.s: dict[str, set] = {}
        self.z: dict[str, dict[str, float]] = {}
        self.l: dict[str, list] = {}
        self.kv: dict[str, str] = {}

    # string
    async def get(self, key):
        return self.kv.get(key)

    async def set(self, key, value, **kw):
        self.kv[key] = str(value)
        return True

    async def incrbyfloat(self, key, amount):
        cur = float(self.kv.get(key, 0) or 0) + float(amount)
        self.kv[key] = repr(cur)
        return cur

    async def delete(self, *keys):
        n = 0
        for k in keys:
            for store in (self.kv, self.h, self.s, self.z, self.l):
                if k in store:
                    del store[k]
                    n += 1
        return n

    async def expire(self, key, ttl):
        return 1  # TTLs are a no-op in the fake

    async def scan_iter(self, match=None):
        import fnmatch
        keys = set(self.kv) | set(self.h) | set(self.s) | set(self.z) | set(self.l)
        for k in list(keys):
            if match is None or fnmatch.fnmatchcase(k, match):
                yield k

    # hash
    async def hincrby(self, key, field, amount):
        d = self.h.setdefault(key, {})
        d[field] = str(int(d.get(field, 0)) + int(amount))
        return int(d[field])

    async def hincrbyfloat(self, key, field, amount):
        d = self.h.setdefault(key, {})
        d[field] = repr(float(d.get(field, 0) or 0) + float(amount))
        return float(d[field])

    async def hget(self, key, field):
        return self.h.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.h.get(key, {}))

    async def hset(self, key, field=None, value=None, *, mapping=None):
        d = self.h.setdefault(key, {})
        if mapping:
            for k, v in mapping.items():
                d[str(k)] = str(v)
        if field is not None:
            d[str(field)] = str(value)
        return 1

    async def hdel(self, key, *fields):
        d = self.h.get(key, {})
        return sum(1 for f in fields if d.pop(f, None) is not None)

    # set
    async def sadd(self, key, *members):
        s = self.s.setdefault(key, set())
        added = 0
        for m in members:
            if m not in s:
                s.add(m)
                added += 1
        return added

    async def sismember(self, key, member):
        return member in self.s.get(key, set())

    # zset
    async def zadd(self, key, mapping):
        z = self.z.setdefault(key, {})
        for m, score in mapping.items():
            z[m] = float(score)
        return len(mapping)

    async def zcard(self, key):
        return len(self.z.get(key, {}))

    async def zremrangebyscore(self, key, lo, hi):
        z = self.z.get(key, {})

        def parse(v):
            s = str(v).lstrip("(")
            if s == "-inf":
                return float("-inf")
            if s == "+inf":
                return float("inf")
            return float(s)

        lo_v, hi_v = parse(lo), parse(hi)
        hi_excl = str(hi).startswith("(")
        drop = [m for m, sc in z.items()
                if sc >= lo_v and (sc < hi_v if hi_excl else sc <= hi_v)]
        for m in drop:
            del z[m]
        return len(drop)

    # list
    async def lpush(self, key, *vals):
        lst = self.l.setdefault(key, [])
        for v in vals:
            lst.insert(0, v)
        return len(lst)

    async def rpop(self, key):
        lst = self.l.get(key, [])
        return lst.pop() if lst else None

    async def ltrim(self, key, start, end):
        lst = self.l.get(key, [])
        self.l[key] = lst[start:] if end == -1 else lst[start:end + 1]
        return True

    async def lrange(self, key, start, end):
        lst = self.l.get(key, [])
        return lst[start:] if end == -1 else lst[start:end + 1]

    async def llen(self, key):
        return len(self.l.get(key, []))

    def pipeline(self, transaction=True):
        return FakePipeline(self)
