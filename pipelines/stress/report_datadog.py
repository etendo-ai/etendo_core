#!/usr/bin/env python3
"""
Send the stress results in STRESS_OUT to Datadog.

Every numeric column of every suite CSV becomes a gauge named etendo.stress.<suite>.<column>,
tagged with the row's level and flow (or onboarding mode) and with the run's context:
stress_run (STRESS_RUN), git_sha (STRESS_SHA), git_ref (STRESS_REF) and DD_TAGS (comma-separated, optional).

Rows that cross a limit also become findings: a gauge etendo.stress.finding = 1 tagged with the
row's tags plus kind (latency, errors, incomplete, onboarding_failed) and column, so the findings
stay in Datadog and never in the repository or the run log:

    any *p95* column above STRESS_P95_LIMIT_MS (default 5000, the ALB critical threshold)
    err_pct above STRESS_ERROR_LIMIT_PCT (default 0.1)
    a journey level that did not complete every journey
    an onboarding that failed

Needs DD_API_KEY; DD_SITE defaults to datadoghq.eu. Without the key it only prints what it
would send.
"""
import csv
import glob
import json
import os
import statistics
import sys
import time
import urllib.request

OUT = os.environ.get("STRESS_OUT", ".")
SITE = os.environ.get("DD_SITE", "datadoghq.eu")
API_KEY = os.environ.get("DD_API_KEY", "")
P95_LIMIT = float(os.environ.get("STRESS_P95_LIMIT_MS", "5000"))
ERROR_LIMIT = float(os.environ.get("STRESS_ERROR_LIMIT_PCT", "0.1"))
RUN = os.environ.get("STRESS_RUN", "")
NOW = int(time.time())

BASE_TAGS = [t for t in [f"stress_run:{RUN}" if RUN else "",
                         f"git_sha:{os.environ.get('STRESS_SHA', '')[:12]}" if os.environ.get("STRESS_SHA") else "",
                         f"git_ref:{os.environ.get('STRESS_REF', '')}" if os.environ.get("STRESS_REF") else ""] if t]
BASE_TAGS += [t.strip() for t in os.environ.get("DD_TAGS", "").split(",") if t.strip()]
TAG_COLUMNS = ("flow", "level", "mode")


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def series(suite, row):
    tags = BASE_TAGS + [f"suite:{suite}"] + [f"{c}:{row[c]}" for c in TAG_COLUMNS if row.get(c) not in (None, "")]
    out = []
    for column, value in row.items():
        v = number(value)
        if column in TAG_COLUMNS or v is None:
            continue
        out.append({"metric": f"etendo.stress.{suite}.{column}", "type": 3,
                    "points": [{"timestamp": NOW, "value": v}], "tags": tags})
    return out


def findings(suite, row):
    """(kind, column) of every limit the row crosses."""
    found = []
    for column, value in row.items():
        v = number(value)
        if v is not None and "p95" in column and v > P95_LIMIT:
            found.append(("latency", column))
    err = number(row.get("err_pct"))
    if err is not None and err > ERROR_LIMIT:
        found.append(("errors", "err_pct"))
    done = number(row.get("completed_pct"))
    if done is not None and done < 100:
        found.append(("incomplete", "completed_pct"))
    return found


def finding_series(suite, row, kind, column):
    tags = BASE_TAGS + [f"suite:{suite}", f"kind:{kind}", f"column:{column}"]
    tags += [f"{c}:{row[c]}" for c in TAG_COLUMNS if row.get(c) not in (None, "")]
    return {"metric": "etendo.stress.finding", "type": 3, "points": [{"timestamp": NOW, "value": 1}], "tags": tags}


def onboarding(suite, rows):
    """One summary row per mode: accounts, ok_pct and register/onboarding median and max."""
    ok = [r for r in rows if r.get("ok") == "True"]
    times = [number(r["onboarding_ms"]) for r in ok]
    registers = [number(r["register_ms"]) for r in rows]
    summary = {"mode": rows[0].get("mode", ""), "accounts": len(rows),
               "ok_pct": round(100 * len(ok) / len(rows), 1) if rows else 0,
               "onboarding_median_ms": statistics.median(times) if times else 0,
               "onboarding_max_ms": max(times, default=0),
               "register_median_ms": statistics.median(registers) if registers else 0}
    failed = sum(1 for r in rows if r.get("ok") != "True")
    return summary, failed


def post(path, body):
    request = urllib.request.Request(f"https://api.{SITE}{path}", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "DD-API-KEY": API_KEY})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status


def main():
    all_series, all_findings = [], []
    for path in sorted(glob.glob(os.path.join(OUT, "*.csv"))):
        suite = os.path.splitext(os.path.basename(path))[0]
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            continue
        if suite.startswith("onboarding_"):
            summary, failed = onboarding(suite, rows)
            all_series += series("onboarding", summary)
            all_findings += [finding_series("onboarding", summary, "onboarding_failed", "ok")] * bool(failed)
            continue
        for row in rows:
            all_series += series(suite, row)
            all_findings += [finding_series(suite, row, kind, column) for kind, column in findings(suite, row)]

    print(f"{len(all_series)} series, {len(all_findings)} findings")
    if not API_KEY:
        print("DD_API_KEY is not set: nothing sent")
        for s in all_series[:5]:
            print("  ", s["metric"], s["points"][0]["value"], s["tags"])
        return
    everything = all_series + all_findings
    for i in range(0, len(everything), 500):
        post("/api/v2/series", {"series": everything[i:i + 500]})
    # Only counts go to the log: the findings themselves stay in Datadog.
    print(f"sent to Datadog ({SITE})")


if __name__ == "__main__":
    sys.exit(main())
