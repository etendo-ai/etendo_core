#!/usr/bin/env python3
"""
Write path under load: create and delete documents at growing concurrency, per flow.

Flows (STRESS_FLOWS): sales (sales order + line), purchases (purchase order + line),
receipts (payment in from a customer) and payments (payment out to a vendor).
Each simulated user creates one document and deletes it. The references are records of the
GOClient sample data.

Writes write.csv: flow, level, ops, err_pct, throughput_ops_s, p95_ms, create_p95_ms.
"""
import asyncio
import os
import time
from collections import Counter

import aiohttp

from common import (BASE, ORDERS, PAYMENTS, caller, drop_rejected, error_message, get_jwt, levels, new_id,
                    note_errors, order_line, pct, write_csv, write_errors)

LEVELS = levels("STRESS_LEVELS", "50,100,150,200")
FLOWS = os.environ.get("STRESS_FLOWS", "sales,purchases,receipts,payments").split(",")

async def order_user(jwt, flow, defaults, records, errors):
    cfg = ORDERS[flow]
    entity = cfg["entity"]
    call = caller(jwt)
    async with aiohttp.ClientSession() as s:
        status, body, ms = await call(s, "POST", f"/sws/neo/{entity}/header", {**defaults, **cfg["header"]})
        records.append(("create", status, ms))
        order_id = new_id(body)
        if not (200 <= status < 300) or not order_id:
            errors.append((status, error_message(body)))
            return
        status, _, ms = await call(s, "POST", f"/sws/neo/{entity}/lines", order_line(flow, order_id))
        records.append(("create line", status, ms))
        status, _, ms = await call(s, "DELETE", f"/sws/neo/{entity}/header/{order_id}")
        records.append(("delete", status, ms))


async def payment_user(jwt, flow, defaults, records, errors):
    base = PAYMENTS[flow]["base"]
    call = caller(jwt)
    async with aiohttp.ClientSession() as s:
        status, body, ms = await call(s, "POST", f"/sws/neo/{base}", {**defaults, **PAYMENTS[flow]["payload"]})
        records.append(("create", status, ms))
        payment_id = new_id(body)
        if not (200 <= status < 300) or not payment_id:
            errors.append((status, error_message(body)))
            return
        status, _, ms = await call(s, "DELETE", f"/sws/neo/{base}/{payment_id}")
        records.append(("delete", status, ms))


async def main():
    print(f"Backend {BASE}, levels {LEVELS}, flows {FLOWS}")
    async with aiohttp.ClientSession() as s:
        jwt, _ = await get_jwt(s)
        defaults = {}
        for flow in FLOWS:
            path = (f"/sws/neo/{ORDERS[flow]['entity']}/header/defaults" if flow in ORDERS
                    else f"/sws/neo/{PAYMENTS[flow]['base']}/defaults")
            async with s.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {jwt}"}) as r:
                defaults[flow] = drop_rejected((await r.json()).get("defaults", {}))

    rows = []
    for flow in FLOWS:
        user = order_user if flow in ORDERS else payment_user
        for n in LEVELS:
            records, errors = [], []
            t0 = time.monotonic()
            await asyncio.gather(*[user(jwt, flow, defaults[flow], records, errors) for _ in range(n)])
            wall = time.monotonic() - t0
            durations = [d for _, _, d in records]
            creates = [d for op, _, d in records if op == "create"]
            ok = sum(1 for _, status, _ in records if 200 <= status < 300)
            total = len(records)
            throughput = total / wall if wall else 0
            err = 100 * (total - ok) / total if total else 0
            rows.append([flow, n, total, round(err, 1), round(throughput, 1),
                         round(pct(durations, 0.95)), round(pct(creates, 0.95))])
            print(f"{flow:<10} {n:>3} users: {throughput:5.1f} ops/s, err {err:4.1f}%, "
                  f"p95 {pct(durations, 0.95):6.0f}ms, create p95 {pct(creates, 0.95):6.0f}ms")
            note_errors(flow, n, [f"[{st}] {m}" for st, m in errors])
            for message, count in Counter(f"[{st}] {m}" for st, m in errors).most_common(1):
                print(f"           {count}x {message}")

    write_csv("write", ["flow", "level", "ops", "err_pct", "throughput_ops_s", "p95_ms", "create_p95_ms"], rows)
    write_errors("write")


if __name__ == "__main__":
    asyncio.run(main())
