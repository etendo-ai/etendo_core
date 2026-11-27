#!/usr/bin/env python3
"""
End-to-end business journey, run by N concurrent users at each level in STRESS_LEVELS.

Each user creates its own master data and trades with it:

    1 product  ->  2 contact (customer and vendor)  ->  2b its address  ->  3 sales order + line
    ->  4 sales invoice + line  ->  5 receipt from the contact  ->  6 payment to the contact

and then deletes everything it created, documents first. The documents are created, not
confirmed (confirm_load.py measures confirming).

Writes journey.csv: level, completed, completed_pct, journeys_s and the p95 of each step
(product_p95, contact_p95, address_p95, order_p95, invoice_p95, receipt_p95, payment_p95).
"""
import asyncio
import time
import uuid
from collections import Counter, defaultdict

import aiohttp

from common import BASE, TODAY, caller, drop_rejected, error_message, get_jwt, levels, pct, write_csv

LEVELS = levels("STRESS_LEVELS", "5,10,20,40")

# GOClient sample data.
WAREHOUSE, UOM = "1FF18B068AA94146A2A49C51E13C739C", "100"
ACCOUNT, PAYMENT_METHOD = "06DB0ED44F25406C9214064C1399E446", "EA00223235264DB78D44D9A47B87E808"
RECEIPT_DOCTYPE, PAYMENT_DOCTYPE = "D132517AE775435B8EB2832CC61FCAB1", "ED1E059C9CF54062BA43B79F3EB89C77"
SPAIN = "110"

DEFAULTS = {"product": "product/product", "order": "sales-order/header", "invoice": "sales-invoice/header",
            "receipt": "payment-in/finPayment", "payment": "payment-out/header",
            "contact": "contacts/businessPartner"}
STEPS = ["product", "contact", "address", "order", "invoice", "receipt", "payment"]


def unquote(defaults):
    """Some defaults come wrapped in literal quotes ('1'), which the POST rejects."""
    return {k: v[1:-1] if isinstance(v, str) and len(v) >= 2 and v[0] == v[-1] == "'" else v
            for k, v in defaults.items()}


def first(body):
    return (body.get("response", {}).get("data") or [{}])[0]


async def journey(jwt, defaults, steps, completed, errors):
    call = caller(jwt, timeout=60)
    tag = uuid.uuid4().hex[:12]
    ids = {}
    async with aiohttp.ClientSession() as s:
        async def step(name, path, body):
            status, payload, ms = await call(s, "POST", path, body)
            steps[name].append(ms)
            if 200 <= status < 300:
                return first(payload).get("id")
            errors.append((name, status, error_message(payload)[:120]))
            return None

        ids["product"] = await step("product", "/sws/neo/product/product",
                                    {**defaults["product"], "name": f"J{tag}", "searchKey": f"J{tag}", "uOM": UOM})
        if not ids["product"]:
            return
        # The contact gets an explicit identifier: GOClient has no sequence for it.
        ids["contact"] = await step("contact", "/sws/neo/contacts/businessPartner",
                                    {**defaults["contact"], "name": f"J{tag}", "searchKey": f"C{tag}",
                                     "etgoIdentifier": f"C{tag}", "vendor": True})
        if ids["contact"]:
            contact = ids["contact"]
            address = await step("address", f"/sws/neo/contacts/locationAddress?parentId={contact}",
                                 {"name": "Madrid, Calle Test 1", "addressLine1": "Calle Test 1", "cityName": "Madrid",
                                  "postalCode": "28001", "country": SPAIN, "shipToAddress": "Y",
                                  "invoiceToAddress": "Y", "businessPartner": contact})
            ids["address"] = address
            if address:
                ids["order"] = await step("order", "/sws/neo/sales-order/header",
                                          {**defaults["order"], "businessPartner": contact,
                                           "partnerAddress": address, "warehouse": WAREHOUSE})
                if ids["order"]:
                    await call(s, "POST", "/sws/neo/sales-order/lines",
                               {"salesOrder": ids["order"], "product": ids["product"], "uOM": UOM,
                                "orderedQuantity": "1", "orderDate": TODAY, "scheduledDeliveryDate": TODAY,
                                "warehouse": WAREHOUSE, "listPrice": "20", "unitPrice": "20", "standardPrice": "20"})

                invoice = {**defaults["invoice"], "businessPartner": contact, "partnerAddress": address}
                invoice.update({k: TODAY for k in invoice if "date" in k.lower() and not k.endswith("_identifier")})
                ids["invoice"] = await step("invoice", "/sws/neo/sales-invoice/header", invoice)
                if ids["invoice"]:
                    await call(s, "POST", "/sws/neo/sales-invoice/lines",
                               {"invoice": ids["invoice"], "product": ids["product"], "uOM": UOM,
                                "invoicedQuantity": "1", "invoiceDate": TODAY,
                                "listPrice": "20", "unitPrice": "20", "standardPrice": "20"})

                ids["receipt"] = await step("receipt", "/sws/neo/payment-in/finPayment",
                                            {**defaults["receipt"], "businessPartner": contact, "account": ACCOUNT,
                                             "paymentMethod": PAYMENT_METHOD, "amount": "50",
                                             "documentType": RECEIPT_DOCTYPE})
                ids["payment"] = await step("payment", "/sws/neo/payment-out/header",
                                            {**defaults["payment"], "businessPartner": contact, "account": ACCOUNT,
                                             "paymentMethod": PAYMENT_METHOD, "amount": "50",
                                             "documentType": PAYMENT_DOCTYPE})

        if all(ids.get(k) for k in ("product", "contact", "order", "invoice", "receipt", "payment")):
            completed.append(1)

        for entity, key in [("sales-order/header", "order"), ("sales-invoice/header", "invoice"),
                            ("payment-in/finPayment", "receipt"), ("payment-out/header", "payment"),
                            ("contacts/locationAddress", "address"), ("contacts/businessPartner", "contact"),
                            ("product/product", "product")]:
            if ids.get(key):
                await call(s, "DELETE", f"/sws/neo/{entity}/{ids[key]}")


async def main():
    print(f"Backend {BASE}, levels {LEVELS}")
    async with aiohttp.ClientSession() as s:
        jwt, _ = await get_jwt(s)
        defaults = {}
        for key, path in DEFAULTS.items():
            async with s.get(f"{BASE}/sws/neo/{path}/defaults", headers={"Authorization": f"Bearer {jwt}"}) as r:
                defaults[key] = drop_rejected(unquote((await r.json()).get("defaults", {})))

    rows = []
    for n in LEVELS:
        steps, completed, errors = defaultdict(list), [], []
        t0 = time.monotonic()
        await asyncio.gather(*[journey(jwt, defaults, steps, completed, errors) for _ in range(n)])
        wall = time.monotonic() - t0
        done_pct = 100 * len(completed) / n if n else 0
        per_second = n / wall if wall else 0
        print(f"{n:>3} journeys: {len(completed)} completed ({done_pct:.0f}%), {per_second:.1f} journeys/s, "
              f"wall {wall:.1f}s")
        for name in STEPS:
            if steps[name]:
                print(f"      {name:<8} p95 {pct(steps[name], 0.95):6.0f}ms  (n={len(steps[name])})")
        for message, count in Counter(f"{nm} [{st}] {m}" for nm, st, m in errors).most_common(3):
            print(f"      {count}x {message}")
        rows.append([n, len(completed), round(done_pct), round(per_second, 1)]
                    + [round(pct(steps[name], 0.95)) for name in STEPS])

    write_csv("journey", ["level", "completed", "completed_pct", "journeys_s"] + [f"{name}_p95" for name in STEPS],
              rows)


if __name__ == "__main__":
    asyncio.run(main())
