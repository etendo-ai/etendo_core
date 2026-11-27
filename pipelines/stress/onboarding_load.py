#!/usr/bin/env python3
"""
Onboarding: N new accounts, each registering and provisioning its own client.

OB_MODE=seq provisions them one after another, OB_MODE=conc all at once (OB_N of them).
Each one is POST /sws/go/register and then POST /sws/go/onboarding, whose NDJSON progress stream
gives the time of every step.

With OB_EMAIL_FILE set, writes there the email of the first account that finished, for
master_data_load.py. Provisioned clients cannot be deleted: run it on a throwaway environment.

Writes onboarding_<mode>.csv: mode, label, register_ms, onboarding_ms, ok, slowest_step, slowest_ms, error.
"""
import datetime
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from common import BASE, write_csv

PASSWORD = os.environ.get("OB_PASSWORD", "Onboard!Test2026")
MODE = os.environ.get("OB_MODE", "seq")
N = int(os.environ.get("OB_N", "3"))
TAG = os.environ.get("OB_TAG", "ci")
EMAIL_FILE = os.environ.get("OB_EMAIL_FILE")
# es_ES is what the SPA's onboarding page sends.
LANG = os.environ.get("OB_LANG", "es_ES")
# "StressOB-YYYYMMDD-HHMMSS-" takes 25 characters; client names are kept within 37.
MAX_CLIENT_NAME = 37
FIELDS = ["mode", "label", "register_ms", "onboarding_ms", "ok", "slowest_step", "slowest_ms", "error"]


def post(path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(f"{BASE}{path}", data=json.dumps(body).encode(), headers=headers, method="POST")


def provision(label):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    client, name = f"StressOB-{stamp}-{label}", f"Stress Onboard {stamp} {label}"
    email = f"stress-ob-{stamp}-{label}@test.local"
    row = {"mode": MODE, "label": label, "register_ms": 0, "onboarding_ms": 0, "ok": False,
           "slowest_step": "", "slowest_ms": 0, "error": "", "email": email}
    try:
        t0 = time.monotonic()
        with urllib.request.urlopen(post("/sws/go/register", {"email": email, "password": PASSWORD, "name": name}),
                                    timeout=60) as response:
            token = json.loads(response.read()).get("token")
        row["register_ms"] = round((time.monotonic() - t0) * 1000)
        if not token:
            raise RuntimeError("register returned no token")
        body = {"clientName": client, "currency": "EUR", "countryCode": "ES", "language": LANG,
                "fullName": name, "businessType": "Retail", "address": "Calle Test 1", "sector": "General"}
        t0 = last = time.monotonic()
        with urllib.request.urlopen(post("/sws/go/onboarding", body, token), timeout=600) as stream:
            for raw in stream:
                line = raw.decode(errors="replace").strip()
                try:
                    event = json.loads(line) if line else None
                except ValueError:
                    event = None
                if not event:
                    continue
                step = event.get("step") or event.get("stage") or event.get("phase") or "?"
                status = event.get("status", "")
                if "heartbeat" in (step, status):
                    continue
                now = time.monotonic()
                if (now - last) * 1000 > row["slowest_ms"]:
                    row["slowest_ms"], row["slowest_step"] = round((now - last) * 1000), step
                last = now
                if event.get("success") is True or status == "success":
                    row["ok"] = True
                if status == "error":
                    row["error"] = (event.get("message") or "")[:160]
        row["onboarding_ms"] = round((time.monotonic() - t0) * 1000)
    except urllib.error.HTTPError as e:
        row["error"] = f"HTTP {e.code}: {e.read().decode(errors='replace')}"[:160]
    except Exception as e:
        row["error"] = str(e)[:160]
    print(f"  {label:<10} {'OK ' if row['ok'] else 'ERR'}  register {row['register_ms']:>5}ms  "
          f"onboarding {row['onboarding_ms'] / 1000:6.1f}s  slowest step {row['slowest_step']} "
          f"({row['slowest_ms'] / 1000:.1f}s)  {row['error']}", flush=True)
    return row


def main():
    print(f"Backend {BASE}, mode {MODE}, language {LANG}, accounts {N}", flush=True)
    labels = [f"{MODE}-{TAG}{i + 1}" for i in range(N)]
    longest = 25 + max(len(label) for label in labels)
    if longest > MAX_CLIENT_NAME:
        raise SystemExit(f"OB_TAG is too long: the client name would take {longest} characters "
                         f"(at most {MAX_CLIENT_NAME})")
    t0 = time.monotonic()
    if MODE == "conc":
        with ThreadPoolExecutor(max_workers=N) as pool:
            rows = list(pool.map(provision, labels))
    else:
        rows = [provision(label) for label in labels]
    ok = [r for r in rows if r["ok"]]
    times = sorted(r["onboarding_ms"] for r in ok)
    median = times[len(times) // 2] / 1000 if times else 0
    print(f"\n  {len(ok)}/{N} OK, median {median:.1f}s, wall {time.monotonic() - t0:.1f}s", flush=True)

    write_csv(f"onboarding_{MODE}", FIELDS, [[r[f] for f in FIELDS] for r in rows])
    if EMAIL_FILE and ok:
        with open(EMAIL_FILE, "w") as f:
            f.write(ok[0]["email"])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
