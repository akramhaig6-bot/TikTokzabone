#!/usr/bin/env python3
"""Explicit, all-or-nothing import of a stopped starter bot.sqlite3 (never modifies source)."""

import argparse, json, secrets, sqlite3
from pathlib import Path
from werkzeug.security import generate_password_hash
from system.store import *


def migrate(source, owner=0):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError("ملف قاعدة البيانات القديمة غير موجود")
    init()
    old = sqlite3.connect("file:" + str(source) + "?mode=ro", uri=True)
    old.row_factory = sqlite3.Row
    try:
        with db() as c:
            if c.execute("SELECT 1 FROM users").fetchone() or setting(
                c, "legacy_imported"
            ):
                raise ValueError(
                    "الاستيراد يتطلب قاعدة جديدة خالية من مستخدمي البوت؛ العملية لا تتكرر"
                )
            users = rows(old, "SELECT * FROM users")
            old_ledger = rows(old, "SELECT * FROM ledger ORDER BY id")
            balances = {u["id"]: cents(u["balance"]) for u in users}
            for u in users:
                if balances[u["id"]] < 0:
                    raise ValueError("يوجد رصيد سلبي قديم؛ يلزم تدقيقه قبل الاستيراد")
                c.execute(
                    "INSERT INTO users(id,username,first_name,balance,created) VALUES(?,?,?,?,?)",
                    (
                        u["id"],
                        u["username"],
                        u["first_name"],
                        balances[u["id"]],
                        u["joined"] or now(),
                    ),
                )
            c.execute("DELETE FROM services")
            for s in rows(old, "SELECT * FROM services"):
                c.execute(
                    "INSERT INTO services(id,name,price,enabled,min_qty) VALUES(?,?,?,?,1)",
                    (s["id"], s["name"], cents(s["price_per_1000"]), s["enabled"]),
                )
            for o in rows(old, "SELECT * FROM orders"):
                service = c.execute(
                    "SELECT name FROM services WHERE id=?", (o["service_id"],)
                ).fetchone()
                if not service:
                    raise ValueError("طلب قديم مرتبط بخدمة مفقودة؛ يلزم إصلاح المصدر")
                c.execute(
                    "INSERT INTO orders(id,user_id,service_id,service_name,target,quantity,price,status,request_key,refunded,created,updated,completed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        o["id"],
                        o["user_id"],
                        o["service_id"],
                        service[0],
                        o["target"],
                        o["quantity"],
                        cents(o["price"]),
                        o["status"],
                        "legacy:" + str(o["id"]),
                        int(o["status"] in ("cancelled", "refunded")),
                        o["created"],
                        o["created"],
                        o["created"] if o["status"] == "completed" else None,
                    ),
                )
            for t in rows(old, "SELECT * FROM topups"):
                status = (
                    t["status"]
                    if t["status"] in ("approved", "rejected")
                    else "awaiting_proof"
                )
                c.execute(
                    "INSERT INTO topups(id,user_id,amount,method,status,proof,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        t["id"],
                        t["user_id"],
                        cents(t["amount"]),
                        t["method"],
                        status,
                        t["proof"] or "",
                        t["created"],
                        t["created"],
                    ),
                )
            for a in rows(old, "SELECT * FROM inventory"):
                c.execute(
                    "INSERT INTO inventory(id,username,note,status,created,updated,added_by,updated_by) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        a["id"],
                        a["username"],
                        a["note"] or "",
                        a["status"],
                        a["created"],
                        a["created"],
                        "legacy",
                        "legacy",
                    ),
                )
            sums = {
                uid: sum(cents(l["delta"]) for l in old_ledger if l["user_id"] == uid)
                for uid in balances
            }
            running = {uid: balances[uid] - sums[uid] for uid in balances}
            for l in old_ledger:
                uid = l["user_id"]
                before = running[uid]
                delta = cents(l["delta"])
                running[uid] += delta
                c.execute(
                    "INSERT INTO ledger(user_id,delta,before_balance,after_balance,reason,actor,operation_key,created) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        uid,
                        delta,
                        before,
                        running[uid],
                        l["reason"],
                        str(l["actor"]),
                        "legacy-ledger:" + str(l["id"]),
                        l["created"],
                    ),
                )
            for p in rows(old, "SELECT * FROM payments"):
                # Preserve historic charge IDs to prevent duplicate processing. These are not new verified invoices.
                tid = c.execute(
                    "INSERT INTO topups(user_id,amount,method,status,created,updated) VALUES(?,?,'stars','approved',?,?)",
                    (p["user_id"], cents(p["amount"]), p["created"], p["created"]),
                ).lastrowid
                c.execute(
                    "INSERT INTO payments(charge_id,topup_id,user_id,amount,currency,created) VALUES(?,?,?,?,?,?)",
                    (
                        p["telegram_charge_id"],
                        tid,
                        p["user_id"],
                        cents(p["amount"]),
                        "LEGACY",
                        p["created"],
                    ),
                )
            for a in rows(old, "SELECT * FROM admins"):
                if a["user_id"] == owner:
                    continue
                c.execute(
                    "INSERT INTO staff(username,password,telegram_id,permissions,enabled,created) VALUES(?,?,?,?,0,?)",
                    (
                        "telegram_" + str(a["user_id"]),
                        generate_password_hash(secrets.token_urlsafe(48)),
                        a["user_id"],
                        json.dumps(
                            [
                                "orders",
                                "topups",
                                "topups_approve",
                                "users",
                                "balances",
                                "support",
                                "broadcasts",
                            ]
                        ),
                        a["added_at"],
                    ),
                )
            if owner:
                put(c, "owner_telegram_id", owner)
            put(
                c,
                "legacy_imported",
                {"source": source.name, "at": now(), "users": len(users)},
            )
            audit(
                c,
                "migration",
                "legacy.import",
                "system",
                {
                    "users": len(users),
                    "ledger": len(old_ledger),
                    "opening_balances": {
                        uid: balances[uid] - sums[uid] for uid in balances
                    },
                },
            )
    finally:
        old.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("--owner-telegram-id", type=int, default=0)
    a = p.parse_args()
    migrate(a.source, a.owner_telegram_id)
    print(
        "Import complete. Review disabled legacy staff accounts in the web panel and assign passwords before enabling them."
    )
