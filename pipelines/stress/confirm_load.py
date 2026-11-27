#!/usr/bin/env python3
"""
Confirming (booking) orders under load.

For each flow (CONFIRM_FLOWS: sales, purchases) and level N in CONFIRM_LEVELS, creates N draft
orders with one line, which is not measured, and then confirms all N at once, which is:

    POST /sws/neo/{entity}/header/{id}/action/documentAction  {"fieldValues": {"documentAction": "CO"}}

Confirmed orders cannot be reopened through the API, so the suite leaves them in the database.
Run it on a throwaway environment.

Writes confirm.csv: flow, level, confirmed, err_pct, throughput_conf_s, p50_ms, p95_ms, p99_ms.
"""
import asyncio
import os
import time
from collections import Counter

import aiohttp

from common import (BASE, ORDERS, caller, drop_rejected, error_message, get_jwt, levels, new_id, order_line, pct,
                    write_csv)

LEVELS = levels("CONFIRM_LEVELS", "10,25,50,75")
FLOWS = os.environ.get("CONFIRM_FLOWS", "sales,purchases").split(",")


async def create_draft(jwt, flow, defaults, ids):
    entity = ORDERS[flow]["entity"]
    call = caller(jwt, timeout=60)
    async with aiohttp.ClientSession() as s:
        _, body, _ = await call(s, "POST", f"/sws/neo/{entity}/header", {**defaults, **ORDERS[flow]["header"]})
        order_id = new_id(body)
        if order_id:
            await call(s, "POST", f"/sws/neo/{entity}/lines", order_line(flow, order_id))
            ids.append(order_id)


async def confirm(jwt, flow, order_id, durations, errors):
    entity = ORDERS[flow]["entity"]
    call = caller(jwt, timeout=60)
    async with aiohttp.ClientSession() as s:
        status, body, ms = await call(s, "POST", f"/sws/neo/{entity}/header/{order_id}/action/documentAction",
                                      {"fieldValues": {"documentAction": "CO"}})
        durations.append(ms)
        if not (200 <= status < 300):
            errors.append((status, error_message(body)))


async def main():
    print(f"Backend {BASE}, flows {FLOWS}, levels {LEVELS}")
    async with aiohttp.ClientSession() as s:
        jwt, _ = await get_jwt(s)
        defaults = {}
        for flow in FLOWS:
            async with s.get(f"{BASE}/sws/neo/{ORDERS[flow]['entity']}/header/defaults",
                             headers={"Authorization": f"Bearer {jwt}"}) as r:
                defaults[flow] = drop_rejected((await r.json()).get("defaults", {}))

    rows = []
    for flow in FLOWS:
        for n in LEVELS:
            ids = []
            await asyncio.gather(*[create_draft(jwt, flow, defaults[flow], ids) for _ in range(n)])
            durations, errors = [], []
            t0 = time.monotonic()
            await asyncio.gather(*[confirm(jwt, flow, order_id, durations, errors) for order_id in ids])
            wall = time.monotonic() - t0
            throughput = len(ids) / wall if wall else 0
            err = 100 * len(errors) / len(ids) if ids else 100
            rows.append([flow, n, len(ids), round(err, 1), round(throughput, 1),
                         round(pct(durations, 0.5)), round(pct(durations, 0.95)), round(pct(durations, 0.99))])
            print(f"{flow:<10} {n:>3} orders: {len(ids) - len(errors)} confirmed, err {err:4.0f}%, "
                  f"{throughput:5.1f} conf/s, p50 {pct(durations, 0.5):5.0f}ms, p95 {pct(durations, 0.95):6.0f}ms")
            for message, count in Counter(f"[{st}] {m}" for st, m in errors).most_common(1):
                print(f"           {count}x {message}")

    write_csv("confirm", ["flow", "level", "confirmed", "err_pct", "throughput_conf_s", "p50_ms", "p95_ms", "p99_ms"],
              rows)


if __name__ == "__main__":
    asyncio.run(main())
