#!/usr/bin/env python3
"""
Send the stress results in STRESS_OUT to Datadog.

Every numeric column of every suite CSV becomes a gauge named etendo.stress.<suite>.<column>,
tagged with the row's level and flow (or onboarding mode) and with the run's context:
stress_run (STRESS_RUN), git_sha (STRESS_SHA), git_ref (STRESS_REF) and DD_TAGS (comma-separated, optional).

Rows that cross a limit also become Datadog events, tagged etendo_stress_finding, so the
findings stay in Datadog and never in the repository or the run log:

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
    where = " ".join(f"{c}={row[c]}" for c in TAG_COLUMNS if row.get(c))
    found = []
    for column, value in row.items():
        v = number(value)
        if v is not None and "p95" in column and v > P95_LIMIT:
            found.append(f"{suite} {where}: {column} {v:.0f} ms is above {P95_LIMIT:.0f} ms")
    err = number(row.get("err_pct"))
    if err is not None and err > ERROR_LIMIT:
        found.append(f"{suite} {where}: error rate {err:.1f}% is above {ERROR_LIMIT}%")
    done = number(row.get("completed_pct"))
    if done is not None and done < 100:
        found.append(f"{suite} {where}: only {done:.0f}% of the journeys completed")
    return found


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
    failed = [f"{suite} mode={summary['mode']}: onboarding {r.get('label')} failed: {r.get('error', '')[:120]}"
              for r in rows if r.get("ok") != "True"]
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
            all_findings += failed
            continue
        for row in rows:
            all_series += series(suite, row)
            all_findings += findings(suite, row)

    print(f"{len(all_series)} series, {len(all_findings)} findings")
    if not API_KEY:
        print("DD_API_KEY is not set: nothing sent")
        for s in all_series[:5]:
            print("  ", s["metric"], s["points"][0]["value"], s["tags"])
        return
    for i in range(0, len(all_series), 500):
        post("/api/v2/series", {"series": all_series[i:i + 500]})
    for text in all_findings:
        post("/api/v1/events", {"title": "Etendo GO stress finding", "text": text, "alert_type": "warning",
                                "tags": BASE_TAGS + ["etendo_stress_finding"]})
    # Only counts go to the log: the findings themselves stay in Datadog.
    print(f"sent to Datadog ({SITE})")


if __name__ == "__main__":
    sys.exit(main())
