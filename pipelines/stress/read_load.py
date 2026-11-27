#!/usr/bin/env python3
"""
Read path under load: list and open-document requests at growing concurrency.

Logs in once and shares the session token (the account allows one session at a time), measures
the login latency on its own, warms the backend up and then runs each level in STRESS_LEVELS.

Writes login.csv (samples, p50_ms, p95_ms, max_ms) and
read.csv (level, reqs, err_pct, throughput_rps, p50_ms, p95_ms, p99_ms, max_ms).
"""
import asyncio
import time
from collections import defaultdict

import aiohttp

from common import BASE, EMAIL, get_jwt, levels, note_errors, pct, write_csv, write_errors

LEVELS = levels("STRESS_LEVELS", "1,5,10,20")

READ_OPS = [
    ("sales order list", f"{BASE}/sws/neo/sales-order/header?limit=20"),
    ("product list", f"{BASE}/sws/neo/product/product?limit=20"),
    ("contact list", f"{BASE}/sws/neo/contacts/businessPartner?limit=20"),
    ("new sales order (defaults)", f"{BASE}/sws/neo/sales-order/header/defaults"),
    ("new sales invoice (defaults)", f"{BASE}/sws/neo/sales-invoice/header/defaults"),
]


async def measure_login(samples=8):
    """Login latency, sequential: one session at a time."""
    durations = []
    async with aiohttp.ClientSession() as s:
        for _ in range(samples):
            t0 = time.monotonic()
            await get_jwt(s)
            durations.append((time.monotonic() - t0) * 1000)
            await asyncio.sleep(0.3)
    print(f"login x{len(durations)}: p50 {pct(durations, 0.5):.0f}ms  p95 {pct(durations, 0.95):.0f}ms")
    write_csv("login", ["samples", "p50_ms", "p95_ms", "max_ms"],
              [[len(durations), round(pct(durations, 0.5)), round(pct(durations, 0.95)), round(max(durations))]])


async def one_user(jwt, records):
    async with aiohttp.ClientSession() as s:
        for name, url in READ_OPS:
            t0 = time.monotonic()
            try:
                async with s.get(url, headers={"Authorization": f"Bearer {jwt}"},
                                 timeout=aiohttp.ClientTimeout(total=25)) as r:
                    await r.read()
                    records.append((name, r.status, (time.monotonic() - t0) * 1000))
            except Exception:
                records.append((name, 0, (time.monotonic() - t0) * 1000))
            await asyncio.sleep(0.2)


async def load_reads(jwt):
    # Two discarded passes fill the Hibernate cache before measuring.
    warm = []
    await one_user(jwt, warm)
    await one_user(jwt, warm)

    rows = []
    for n in LEVELS:
        records = []
        t0 = time.monotonic()
        await asyncio.gather(*[one_user(jwt, records) for _ in range(n)])
        wall = time.monotonic() - t0

        durations = [d for _, _, d in records]
        ok = sum(1 for _, status, _ in records if 200 <= status < 300)
        total = len(records)
        throughput = total / wall if wall else 0
        err = 100 * (total - ok) / total if total else 0
        rows.append([n, total, round(err, 1), round(throughput, 1), round(pct(durations, 0.5)),
                     round(pct(durations, 0.95)), round(pct(durations, 0.99)), round(max(durations, default=0))])

        print(f"{n:>3} users: {total} reqs, err {err:.1f}%, {throughput:.1f} req/s, "
              f"p50 {pct(durations, 0.5):.0f}ms, p95 {pct(durations, 0.95):.0f}ms")
        note_errors("", n, [f"{name} [{status}]" for name, status, _ in records if not 200 <= status < 300])
        by_op = defaultdict(list)
        for name, _, d in records:
            by_op[name].append(d)
        for name, ds in by_op.items():
            print(f"      {name:<30} p50 {pct(ds, 0.5):.0f}ms  p95 {pct(ds, 0.95):.0f}ms")

    write_csv("read", ["level", "reqs", "err_pct", "throughput_rps", "p50_ms", "p95_ms", "p99_ms", "max_ms"], rows)
    write_errors("read")


async def main():
    print(f"Backend {BASE}, account {EMAIL}, levels {LEVELS}")
    async with aiohttp.ClientSession() as s:
        jwt, _ = await get_jwt(s)
    await measure_login()
    await load_reads(jwt)


if __name__ == "__main__":
    asyncio.run(main())
