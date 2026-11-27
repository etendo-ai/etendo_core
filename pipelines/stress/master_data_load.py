#!/usr/bin/env python3
"""
Master data under load: create and delete contacts and products at growing concurrency.

Each simulated user creates one record and deletes it (STRESS_FLOWS: contacts, products).
Contacts need the identifier sequence that onboarding creates, so log in with an account of an
onboarded client (STRESS_EMAIL / STRESS_PASSWORD, as onboarding_load.py leaves in OB_EMAIL_FILE).

Writes master_data.csv: flow, level, ops, err_pct, throughput_ops_s, p50_ms, p95_ms, p99_ms
(the percentiles are of the create request).
"""
import asyncio
import os
import time
from collections import Counter

import aiohttp

from common import BASE, EMAIL, caller, drop_rejected, error_message, get_jwt, levels, new_id, pct, write_csv

LEVELS = levels("STRESS_LEVELS", "50,100,150,200")
FLOWS = os.environ.get("STRESS_FLOWS", "contacts,products").split(",")

ENTITIES = {
    "contacts": {"entity": "contacts/businessPartner", "prefix": "SBP"},
    "products": {"entity": "product/product", "prefix": "SPR"},
}


def unquote(defaults):
    """Some defaults come wrapped in literal quotes ('1'), which the POST rejects."""
    return {k: v[1:-1] if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] == "'" else v
            for k, v in defaults.items()}


async def one_user(jwt, flow, defaults, tag, records, errors):
    entity, prefix = ENTITIES[flow]["entity"], ENTITIES[flow]["prefix"]
    call = caller(jwt)
    async with aiohttp.ClientSession() as s:
        body = {**defaults, "name": f"{prefix} {tag}", "searchKey": f"{prefix}{tag}"}
        status, payload, ms = await call(s, "POST", f"/sws/neo/{entity}", body)
        records.append(("create", status, ms))
        record_id = new_id(payload)
        if not (200 <= status < 300) or not record_id:
            errors.append((status, error_message(payload)))
            return
        status, _, ms = await call(s, "DELETE", f"/sws/neo/{entity}/{record_id}")
        records.append(("delete", status, ms))


async def main():
    print(f"Backend {BASE}, account {EMAIL}, flows {FLOWS}, levels {LEVELS}")
    async with aiohttp.ClientSession() as s:
        jwt, _ = await get_jwt(s)
        defaults = {}
        for flow in FLOWS:
            async with s.get(f"{BASE}/sws/neo/{ENTITIES[flow]['entity']}/defaults",
                             headers={"Authorization": f"Bearer {jwt}"}) as r:
                defaults[flow] = drop_rejected(unquote((await r.json()).get("defaults", {})))

    rows, counter = [], 0
    for flow in FLOWS:
        for n in LEVELS:
            tags = [f"{int(time.time())}-{counter + i}" for i in range(n)]
            counter += n
            records, errors = [], []
            t0 = time.monotonic()
            await asyncio.gather(*[one_user(jwt, flow, defaults[flow], tag, records, errors) for tag in tags])
            wall = time.monotonic() - t0
            creates = [d for op, _, d in records if op == "create"]
            ok = sum(1 for _, status, _ in records if 200 <= status < 300)
            total = len(records)
            throughput = total / wall if wall else 0
            err = 100 * (total - ok) / total if total else 0
            rows.append([flow, n, total, round(err, 1), round(throughput, 1),
                         round(pct(creates, 0.5)), round(pct(creates, 0.95)), round(pct(creates, 0.99))])
            print(f"{flow:<9} {n:>3} users: {throughput:6.1f} ops/s, err {err:4.1f}%, "
                  f"create p50 {pct(creates, 0.5):5.0f}ms, p95 {pct(creates, 0.95):6.0f}ms")
            for message, count in Counter(f"[{st}] {m}" for st, m in errors).most_common(1):
                print(f"          {count}x {message}")

    write_csv("master_data", ["flow", "level", "ops", "err_pct", "throughput_ops_s", "p50_ms", "p95_ms", "p99_ms"],
              rows)


if __name__ == "__main__":
    asyncio.run(main())
