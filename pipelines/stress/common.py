"""
Shared pieces of the Etendo GO stress suites: configuration, login and result files.

Every suite reads its target and credentials from the environment:

    STRESS_BASE      Etendo context URL (default http://localhost:8080/etendo)
    STRESS_EMAIL     Etendo GO account used to log in
    STRESS_PASSWORD  its password
    STRESS_OUT       directory for the result CSVs (default: the current directory)

and writes one CSV per suite, which report_datadog.py turns into metrics, plus <suite>_errors.csv
with the most frequent error messages of each level, which it sends to Datadog Logs.
"""
import csv
import datetime
import json
import os
import time
from collections import Counter

import aiohttp

BASE = os.environ.get("STRESS_BASE", "http://localhost:8080/etendo").rstrip("/")
EMAIL = os.environ.get("STRESS_EMAIL", "goadmin@etendo.software")
PASSWORD = os.environ.get("STRESS_PASSWORD", "12345")
OUT = os.environ.get("STRESS_OUT", ".")

TIMEOUT = aiohttp.ClientTimeout(total=20)


def levels(var, default):
    """Concurrency levels from a comma-separated environment variable."""
    return [int(x) for x in (os.environ.get(var) or default).split(",") if x.strip()]


def pct(values, p):
    """Nearest-rank percentile; 0 for an empty sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


async def get_jwt(session, email=None, password=None):
    """Two-step login, as the SPA does it.

    POST /sws/go/login returns a platform token; /sws/go/environments gives the account's
    adminUserId; /sws/go/login?userId=<id> exchanges both for the session token the NEO API takes.
    Returns (session token, adminUserId).
    """
    body = {"email": email or EMAIL, "password": password or PASSWORD}
    async with session.post(f"{BASE}/sws/go/login", json=body, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise SystemExit(f"login failed ({r.status}) at {BASE}/sws/go/login")
        platform = (await r.json()).get("token")

    auth = {"Authorization": f"Bearer {platform}"}
    async with session.get(f"{BASE}/sws/go/environments", headers=auth, timeout=TIMEOUT) as r:
        envs = await r.json(content_type=None) if r.status == 200 else {}
    env_list = envs.get("environments", []) if isinstance(envs, dict) else (envs if isinstance(envs, list) else [])
    admin_user_id = env_list[0].get("adminUserId") if env_list else None
    if not admin_user_id:
        raise SystemExit("could not read adminUserId from /sws/go/environments")

    async with session.get(f"{BASE}/sws/go/login?userId={admin_user_id}", headers=auth, timeout=TIMEOUT) as r:
        if r.status != 200:
            raise SystemExit(f"environment login failed ({r.status})")
        return (await r.json()).get("token"), admin_user_id


# Records of the GOClient sample data the write suites reference.
ORDERS = {
    "sales": {
        "entity": "sales-order",
        "header": {"businessPartner": "203884E383AB4B5AAF3FA05EF8E9BE46",
                   "partnerAddress": "7C6F01662067414EAEFD134D90A393F1",
                   "warehouse": "1FF18B068AA94146A2A49C51E13C739C"},
        "warehouse": "1FF18B068AA94146A2A49C51E13C739C",
    },
    "purchases": {
        "entity": "purchase-order",
        "header": {"businessPartner": "8EB9853B2C144E9BBF4F7AC1679AFEDD",
                   "partnerAddress": "E6674773E6C94DFEAD4BF586E8BFB0D6",
                   "warehouse": "081A28467A2948529BB65C902289AFDF"},
        "warehouse": "081A28467A2948529BB65C902289AFDF",
    },
}
PRODUCT, UOM = "88AD998AD10841F99D4F605014113EE3", "100"
TODAY = datetime.date.today().isoformat()
PAYMENTS = {
    "receipts": {
        "base": "payment-in/finPayment",
        "payload": {"businessPartner": "203884E383AB4B5AAF3FA05EF8E9BE46",
                    "account": "06DB0ED44F25406C9214064C1399E446", "paymentMethod": "EA00223235264DB78D44D9A47B87E808",
                    "amount": "100", "documentType": "D132517AE775435B8EB2832CC61FCAB1"},
    },
    "payments": {
        "base": "payment-out/header",
        "payload": {"businessPartner": "8EB9853B2C144E9BBF4F7AC1679AFEDD",
                    "account": "06DB0ED44F25406C9214064C1399E446", "paymentMethod": "EA00223235264DB78D44D9A47B87E808",
                    "amount": "100", "documentType": "ED1E059C9CF54062BA43B79F3EB89C77"},
    },
}

# Fields /defaults proposes that the POST rejects (REFERENCE_NOT_ALLOWED): the purchase order's
# salesRepresentative and the payment out's currency. Dropped so the backend derives them.
DROP_DEFAULTS = ("salesRepresentative", "currency")


def drop_rejected(defaults):
    return {k: v for k, v in defaults.items() if k.split("$")[0] not in DROP_DEFAULTS}


def error_message(body):
    error = body.get("error")
    message = error.get("message") if isinstance(error, dict) else error
    return (message or str(body)[:120])[:160]


def caller(jwt, timeout=40):
    headers = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}

    async def call(session, method, path, body=None):
        t0 = time.monotonic()
        try:
            async with session.request(method, f"{BASE}{path}", headers=headers,
                                       data=json.dumps(body).encode() if body is not None else None,
                                       timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                payload = await r.json(content_type=None) if method != "DELETE" else {}
                return r.status, payload or {}, (time.monotonic() - t0) * 1000
        except Exception as e:
            # Status 0: no HTTP answer (a timeout or a dropped connection).
            return 0, {"error": {"message": f"{type(e).__name__} {e}".strip()}}, (time.monotonic() - t0) * 1000
    return call


def new_id(body):
    return (body.get("response", {}).get("data") or [{}])[0].get("id")


def order_line(flow, order_id):
    """One line of the sample product on an order of the given flow."""
    return {"salesOrder": order_id, "product": PRODUCT, "uOM": UOM, "orderedQuantity": "1",
            "orderDate": TODAY, "scheduledDeliveryDate": TODAY, "warehouse": ORDERS[flow]["warehouse"],
            "listPrice": "23", "unitPrice": "23", "standardPrice": "23"}


def write_csv(name, header, rows):
    """Write a suite's results to <STRESS_OUT>/<name>.csv and return the path."""
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.csv")
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"\n  -> {path} ({len(rows)} rows)")
    return path


ERRORS = []


def note_errors(flow, level, messages):
    """Keep the three most frequent error messages of a level for write_errors()."""
    for message, count in Counter(messages).most_common(3):
        ERRORS.append([flow, level, count, message])


def write_errors(name):
    """Write the noted error messages to <STRESS_OUT>/<name>_errors.csv."""
    return write_csv(f"{name}_errors", ["flow", "level", "count", "message"], ERRORS)
