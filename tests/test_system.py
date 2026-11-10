import concurrent.futures, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash
from system import store
from system.store import *
from system.domain import *
from system.telegram import (
    process_update,
    action,
    handle_input,
    getstate,
    draft,
    review,
)
from system.web import create_app, LIMITS


class SystemTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = store.ROOT
        store.ROOT = Path(self.temp.name)
        LIMITS.clear()
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/session").json["csrf"]
        self.post(
            "auth/setup", {"username": "owner", "password": "secure-password-123"}
        )
        self.csrf = self.client.get("/api/session").json["csrf"]
        with db() as c:
            c.execute(
                "INSERT INTO users(id,username,first_name,balance,created) VALUES(?,?,?,?,?)",
                (123, "customer", "Customer", 10000, now()),
            )

    def tearDown(self):
        store.ROOT = self.old
        self.temp.cleanup()

    def post(self, path, data):
        return self.client.post(
            "/api/" + path, json=data, headers={"X-CSRF-Token": self.csrf}
        )

    def makeorder(self, key="unique"):
        with db() as c:
            return order_create(
                c,
                123,
                {
                    "key": key,
                    "service_id": 1,
                    "target": "https://www.tiktok.com/@customer",
                    "quantity": 1000,
                    "price": 100,
                },
            )

    def update(self, n, text=None, callback=None, **extra):
        u = {"id": 123, "username": "customer", "first_name": "Customer"}
        if callback:
            return {
                "update_id": n,
                "callback_query": {
                    "id": str(n),
                    "from": u,
                    "data": callback,
                    "message": {"chat": {"id": 123, "type": "private"}},
                },
            }
        return {
            "update_id": n,
            "message": {
                "from": u,
                "chat": {"id": 123, "type": "private"},
                "text": text or "",
                **extra,
            },
        }

    def test_money_and_link_validation(self):
        self.assertEqual(cents("1.005"), 101)
        for x in ["nan", "Infinity", "-Infinity"]:
            with self.assertRaises(ValueError):
                cents(x)
        for x in [
            "https://tiktok.com.evil.org/@x",
            "https://tiktok.com@evil.org/@x",
            "http://tiktok.com/@x",
            "https://tiktok.com:999/@x",
            "https://evil.org",
            "https://www.tiktok.com/",
        ]:
            self.assertFalse(target_valid(x), x)
        self.assertTrue(target_valid("https://www.tiktok.com/@x/video/123", "video"))
        self.assertFalse(target_valid("https://www.tiktok.com/@x", "video"))

    def test_order_atomic_and_idempotent(self):
        first = self.makeorder()
        self.assertEqual(self.makeorder(), first)
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 9900)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM ledger").fetchone()[0], 1)

    def test_insufficient_balance_rolls_back_order(self):
        with db() as c:
            c.execute("UPDATE users SET balance=0 WHERE id=123")
        with self.assertRaises(ValueError):
            self.makeorder()
        with db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)

    def test_refund_only_once(self):
        oid = self.makeorder()
        with db() as c:
            order_status(c, oid, "cancelled", 1)
        with db() as c:
            order_status(c, oid, "cancelled", 1)
        with self.assertRaises(ValueError):
            with db() as c:
                order_status(c, oid, "processing", 1)
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 10000)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM ledger WHERE delta>0").fetchone()[0], 1
            )

    def test_concurrent_confirm(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
            ids = list(ex.map(lambda _: self.makeorder(), range(6)))
        self.assertEqual(len(set(ids)), 1)

    def test_concurrent_refund(self):
        oid = self.makeorder()

        def refund(_):
            with db() as c:
                order_status(c, oid, "refunded", 1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            list(ex.map(refund, range(5)))
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 10000)

    def test_current_service_and_price_checked(self):
        with db() as c:
            c.execute("UPDATE services SET price=200 WHERE id=1")
        with self.assertRaises(ValueError):
            self.makeorder()
        with db() as c:
            c.execute("UPDATE services SET price=100,enabled=0 WHERE id=1")
        with self.assertRaises(ValueError):
            self.makeorder()

    def test_topup_proof_required_and_once(self):
        with db() as c:
            t = topup_create(c, 123, 500, "manual")
        with self.assertRaises(ValueError):
            with db() as c:
                topup_review(c, t["id"], True, "", 1)
        with db() as c:
            c.execute(
                "UPDATE topups SET proof='proof',status='review' WHERE id=?", (t["id"],)
            )
        with db() as c:
            topup_review(c, t["id"], True, "", 1)
        with self.assertRaises(ValueError):
            with db() as c:
                topup_review(c, t["id"], True, "", 1)
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 10500)

    def test_stars_all_fields_validated_and_deduplicated(self):
        with db() as c:
            t = topup_create(c, 123, 500, "stars")
        p = {
            "invoice_payload": t["payload"],
            "currency": "XTR",
            "total_amount": t["stars"],
            "telegram_payment_charge_id": "charge1",
        }
        for change in [
            {"currency": "USD"},
            {"total_amount": 1},
            {"invoice_payload": "stars:999"},
        ]:
            with self.assertRaises(ValueError):
                with db() as c:
                    payment(c, 123, {**p, **change})
        with self.assertRaises(ValueError):
            with db() as c:
                payment(c, 999, p)
        with db() as c:
            payment(c, 123, p)
        with db() as c:
            payment(c, 123, p)
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 10500)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1
            )

    def test_customer_order_journey_and_update_replay(self):
        for n, cb in [(1, "home"), (2, "service:1")]:
            process_update(self.update(n, callback=cb))
        process_update(self.update(3, "https://www.tiktok.com/@customer"))
        process_update(self.update(4, "1000"))
        process_update(self.update(5, callback="order_confirm"))
        process_update(self.update(5, callback="order_confirm"))
        with db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)
            self.assertEqual(one(c, "users", 123)["balance"], 9900)
            self.assertEqual(draft(c, 123), {})

    def test_resume_order_after_topup_navigation(self):
        process_update(self.update(1, callback="service:1"))
        process_update(self.update(2, "https://www.tiktok.com/@customer"))
        process_update(self.update(3, "1000"))
        process_update(self.update(4, callback="topup"))
        process_update(self.update(5, callback="home"))
        process_update(self.update(6, callback="resume"))
        with db() as c:
            self.assertEqual(getstate(c, 123)[0], "order_confirm")
            self.assertEqual(draft(c, 123)["quantity"], 1000)

    def test_manual_proof_photo(self):
        process_update(self.update(1, callback="newtopup:manual"))
        process_update(self.update(2, "5"))
        process_update(self.update(3, callback="topup_go"))
        process_update(
            self.update(4, photo=[{"file_id": "photo_id"}], caption="reference 42")
        )
        with db() as c:
            t = one(c, "topups", 1)
            self.assertEqual(t["status"], "review")
            self.assertEqual(json.loads(t["proof"])["value"], "photo_id")
            self.assertEqual(t["note"], "reference 42")

    def test_ticket_conversation(self):
        process_update(self.update(1, callback="newticket:طلب"))
        process_update(self.update(2, "مشكلة في الطلب"))
        self.assertEqual(
            self.post("action/reply", {"id": 1, "body": "مرحبًا بك"}).status_code, 200
        )
        process_update(self.update(3, callback="ticket_status:1:closed"))
        process_update(self.update(4, callback="ticket_status:1:open"))
        with db() as c:
            self.assertEqual(one(c, "tickets", 1)["status"], "open")
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 2
            )

    def test_ledger_immutable(self):
        self.makeorder()
        with self.assertRaises(sqlite3.IntegrityError):
            with db() as c:
                c.execute("DELETE FROM ledger")

    def test_csrf_and_auth(self):
        self.assertEqual(
            self.client.post("/api/settings", json={"brand": "X"}).status_code, 403
        )
        other = self.app.test_client()
        self.assertEqual(other.get("/api/data/users").status_code, 401)

    def test_admin_permissions_and_self_escalation(self):
        self.assertEqual(
            self.post(
                "data/staff",
                {
                    "username": "admin",
                    "password": "admin-password-123",
                    "permissions": ["orders", "staff"],
                    "enabled": True,
                },
            ).status_code,
            200,
        )
        other = self.app.test_client()
        csrf = other.get("/api/session").json["csrf"]
        r = other.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin-password-123"},
            headers={"X-CSRF-Token": csrf},
        )
        csrf = r.json["csrf"]
        self.assertEqual(other.get("/api/data/users").status_code, 403)
        self.assertEqual(
            other.post(
                "/api/data/staff",
                json={"id": 2, "username": "admin", "permissions": ["settings"]},
                headers={"X-CSRF-Token": csrf},
            ).status_code,
            400,
        )
        self.assertEqual(
            other.post(
                "/api/data/staff",
                json={
                    "username": "other",
                    "password": "password-long-123",
                    "permissions": ["settings"],
                },
                headers={"X-CSRF-Token": csrf},
            ).status_code,
            400,
        )
        self.assertEqual(
            other.post(
                "/api/delete/staff/1", json={}, headers={"X-CSRF-Token": csrf}
            ).status_code,
            400,
        )

    def test_dynamic_menu_edit_immediate(self):
        with db() as c:
            mid = c.execute("SELECT id FROM menus WHERE key='home'").fetchone()[0]
        self.post("data/menus", {"id": mid, "text": "رسالة مخصصة جديدة"})
        process_update(self.update(1, "/start"))
        with db() as c:
            p = json.loads(
                c.execute(
                    "SELECT payload FROM notifications ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]
            )
            self.assertEqual(p["data"]["text"], "رسالة مخصصة جديدة")

    def test_dynamic_nested_menu(self):
        r = self.post(
            "data/menus",
            {"key": "faq", "name": "الأسئلة", "text": "نص الأسئلة", "kind": "inline"},
        )
        self.assertEqual(r.status_code, 200)
        with db() as c:
            home = c.execute("SELECT id FROM menus WHERE key='home'").fetchone()[0]
        r = self.post(
            "data/buttons",
            {
                "menu_id": home,
                "label": "الأسئلة",
                "action": "menu",
                "target": "faq",
                "kind": "callback",
                "enabled": True,
            },
        )
        self.assertEqual(r.status_code, 200)
        process_update(self.update(1, callback="button:" + str(r.json["id"])))
        with db() as c:
            p = json.loads(
                c.execute(
                    "SELECT payload FROM notifications ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]
            )
            self.assertEqual(p["data"]["text"], "نص الأسئلة")

    def test_soft_delete_preserves_orders(self):
        oid = self.makeorder()
        self.assertEqual(self.post("delete/services/1", {}).status_code, 200)
        with db() as c:
            self.assertEqual(one(c, "orders", oid)["service_id"], 1)
            self.assertEqual(one(c, "services", 1)["deleted"], 1)

    def test_connection_encrypts_token_and_does_not_return(self):
        with patch(
            "system.telegram.call", return_value={"id": 77, "username": "testbot"}
        ):
            r = self.post("connect", {"token": "123:secret"})
        self.assertEqual(r.status_code, 200)
        with db() as c:
            self.assertNotIn("secret", setting(c, "telegram_token"))
        self.assertNotIn(
            "telegram_token", self.client.get("/api/bootstrap").json["settings"]
        )

    def test_broadcast_real_queue_and_lifecycle(self):
        r = self.post(
            "data/broadcasts", {"body": "Hello", "kind": "text", "audience": "active"}
        )
        bid = r.json["id"]
        self.assertEqual(
            self.post("action/broadcast", {"id": bid, "status": "running"}).status_code,
            200,
        )
        with db() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0], 1
            )
        self.assertEqual(
            self.post("action/broadcast", {"id": bid, "status": "paused"}).status_code,
            200,
        )

    def test_stats_actual_cost_not_sales_as_profit(self):
        oid = self.makeorder()
        with db() as c:
            order_status(c, oid, "processing", 1)
            order_status(c, oid, "completed", 1)
            c.execute("UPDATE orders SET cost=40 WHERE id=?", (oid,))
            from system.accounting import expense_add

            expense_add(c, "expense", 10, "تشغيل", now()[:10], 1, "test-cost")
        s = self.client.get("/api/stats").json
        self.assertEqual(s["sales"], 100)
        self.assertEqual(s["profit"], 50)

    def test_financial_action_idempotent(self):
        d = {"user_id": 123, "amount": "5", "reason": "تعويض", "key": "stable"}
        self.assertEqual(self.post("action/balance", d).status_code, 200)
        self.assertEqual(self.post("action/balance", d).status_code, 200)
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 10500)

    def test_owner_cannot_be_removed(self):
        self.assertEqual(self.post("delete/staff/1", {}).status_code, 400)

    def test_maintenance_prevents_orders(self):
        with db() as c:
            put(c, "maintenance", "orders")
        with self.assertRaises(ValueError):
            self.makeorder()

    def test_foreign_customer_access_denied(self):
        oid = self.makeorder()
        with db() as c:
            c.execute("INSERT INTO users(id,created) VALUES(456,?)", (now(),))
        with self.assertRaises(ValueError):
            with db() as c:
                action(c, 456, "order:" + str(oid))

    def test_session_timeout_keeps_draft(self):
        process_update(self.update(1, callback="service:1"))
        with db() as c:
            c.execute("UPDATE sessions SET updated=0")
            self.assertEqual(getstate(c, 123)[0], "expired")
            self.assertTrue(draft(c, 123))

    def test_expired_confirmation_does_not_debit(self):
        process_update(self.update(1, callback="service:1"))
        process_update(self.update(2, "https://www.tiktok.com/@customer"))
        process_update(self.update(3, "1000"))
        with db() as c:
            c.execute("UPDATE sessions SET updated=0")
        process_update(self.update(4, callback="order_confirm"))
        with db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)
            self.assertEqual(one(c, "users", 123)["balance"], 10000)
            self.assertTrue(draft(c, 123))

    def test_cancelled_invoice_rejects_new_payment(self):
        with db() as c:
            t = topup_create(c, 123, 500, "stars")
        process_update(self.update(1, callback="topup_cancel:" + str(t["id"])))
        with self.assertRaises(ValueError):
            with db() as c:
                payment(
                    c,
                    123,
                    {
                        "invoice_payload": t["payload"],
                        "currency": "XTR",
                        "total_amount": t["stars"],
                        "telegram_payment_charge_id": "late",
                    },
                )

    def test_catalog_ready_before_first_bot_user(self):
        with db() as c:
            self.assertTrue(
                c.execute("SELECT 1 FROM menus WHERE key='order_review'").fetchone()
            )
            self.assertTrue(
                c.execute(
                    "SELECT 1 FROM menus WHERE key='layout_topup_review'"
                ).fetchone()
            )

    def test_manual_edit_keeps_manual_method(self):
        process_update(self.update(1, callback="newtopup:stars"))
        process_update(self.update(2, "5"))
        process_update(self.update(3, callback="newtopup:manual"))
        process_update(self.update(4, "10"))
        process_update(self.update(5, callback="edit_topup_amount"))
        with db() as c:
            self.assertEqual(getstate(c, 123), ("topup_amount", {"method": "manual"}))

    def test_outbox_sends_and_records_status(self):
        from system.telegram import dispatch

        with db() as c:
            notify(c, 123, "Hello")
        with patch("system.telegram.call", return_value={"message_id": 1}) as mocked:
            dispatch("test-token")
        self.assertEqual(mocked.call_count, 1)
        with db() as c:
            self.assertEqual(one(c, "notifications", 1)["status"], "sent")

    def test_broadcast_delivery_and_pause(self):
        from system.telegram import broadcast_step

        bid = self.post(
            "data/broadcasts", {"body": "Hello", "kind": "text", "audience": "all"}
        ).json["id"]
        self.post("action/broadcast", {"id": bid, "status": "running"})
        self.post("action/broadcast", {"id": bid, "status": "paused"})
        with patch("system.telegram.call") as mocked:
            broadcast_step("test-token")
            self.assertFalse(mocked.called)
        self.post("action/broadcast", {"id": bid, "status": "running"})
        with patch("system.telegram.call", return_value={}):
            broadcast_step("test-token")
            broadcast_step("test-token")
        with db() as c:
            self.assertEqual(one(c, "broadcasts", bid)["status"], "completed")
            self.assertEqual(one(c, "deliveries", 1)["status"], "sent")

    def test_missing_csrf_session_cannot_be_forged(self):
        fresh = self.app.test_client()
        self.assertEqual(
            fresh.post(
                "/api/auth/setup",
                json={"username": "x", "password": "long-password-123"},
                headers={"X-CSRF-Token": "MISSING"},
            ).status_code,
            403,
        )

    def test_inventory_history_preserved(self):
        i = self.post(
            "data/inventory",
            {"username": "sample", "note": "record only", "status": "available"},
        ).json["id"]
        self.post("data/inventory", {"id": i, "status": "reserved"})
        self.post("delete/inventory/" + str(i), {})
        with db() as c:
            self.assertEqual(one(c, "inventory", i)["deleted"], 1)
            self.assertGreaterEqual(
                c.execute(
                    "SELECT COUNT(*) FROM audit WHERE action LIKE 'inventory.%' AND entity=?",
                    (str(i),),
                ).fetchone()[0],
                3,
            )

    def test_safe_old_database_migration(self):
        from migrate_legacy import migrate

        with db() as c:
            c.execute("DELETE FROM users")
        old_path = Path(self.temp.name) / "old.sqlite3"
        old = sqlite3.connect(old_path)
        # Build the original schema without importing or executing the historical network client.
        source = (Path(__file__).parent.parent / "legacy/bot.py.txt").read_text()
        import re

        schema = re.search(r'c.executescript\("""(.*?)"""\)', source, re.S).group(1)
        old.executescript(schema)
        old.execute(
            "INSERT INTO users VALUES(123,'customer','Customer',5.5,'2026-11-09')"
        )
        old.execute("INSERT INTO services VALUES(1,'Legacy service',1,1)")
        old.execute(
            "INSERT INTO ledger(user_id,delta,reason,actor,created) VALUES(123,5.5,'manual',1,'2026-11-09')"
        )
        old.commit()
        old.close()
        migrate(old_path)
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 550)
            self.assertEqual(one(c, "ledger", 1)["after_balance"], 550)
            self.assertEqual(one(c, "services", 1)["price"], 100)
        with self.assertRaises(ValueError):
            migrate(old_path)

    def test_precheckout_blocks_cancel_but_allows_paid_credit(self):
        from system.telegram import precheckout

        with db() as c:
            t = topup_create(c, 123, 500, "stars")
        p = {
            "invoice_payload": t["payload"],
            "currency": "XTR",
            "total_amount": t["stars"],
        }
        with patch("system.telegram.call", return_value={}):
            precheckout("test-token", {"id": "query", "from": {"id": 123}, **p})
        process_update(self.update(1, callback="topup_cancel:" + str(t["id"])))
        with db() as c:
            self.assertEqual(one(c, "topups", t["id"])["status"], "awaiting_payment")
            payment(c, 123, {**p, "telegram_payment_charge_id": "paid-after-checkout"})
            self.assertEqual(one(c, "users", 123)["balance"], 10500)

    def test_password_change_requires_current_password(self):
        self.assertEqual(
            self.post(
                "password", {"current": "wrong", "new": "new-secure-password"}
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "password",
                {"current": "secure-password-123", "new": "new-secure-password"},
            ).status_code,
            200,
        )

    def upload(
        self, data, filename="picture.png", purpose="services", client=None, csrf=None
    ):
        import io

        return (client or self.client).post(
            "/api/media",
            data={"purpose": purpose, "file": (io.BytesIO(data), filename)},
            headers={"X-CSRF-Token": csrf or self.csrf},
            content_type="multipart/form-data",
        )

    def image_bytes(self):
        import io
        from PIL import Image

        data = io.BytesIO()
        Image.new("RGB", (12, 12), "red").save(data, format="PNG")
        return data.getvalue()

    def test_image_upload_is_private_and_reencoded(self):
        response = self.upload(
            self.image_bytes() + b"<script>bad</script>", filename="../../example.png"
        )
        self.assertEqual(response.status_code, 200, response.json)
        asset_id = response.json["id"]
        ref = response.json["ref"]
        from system.media import asset

        with db() as c:
            row, path = asset(c, ref, kind="photo", purpose="services")
            self.assertEqual(path.parent, store.ROOT / "uploads")
            self.assertTrue(path.read_bytes().startswith(b"\xff\xd8"))
            self.assertNotIn(b"<script>", path.read_bytes())
        result = self.client.get("/api/media/" + str(asset_id))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.mimetype, "image/jpeg")
        result.close()
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/api/media/" + str(asset_id)).status_code, 401)

    def test_upload_rejects_executable_html_svg_and_fake_image(self):
        for name, raw in [
            ("x.html", b"<html>hello"),
            ("x.svg", b"<svg/>"),
            ("x.png", b"not an image"),
            ("x.mp4", b"not video"),
            ("x.txt", b"\x00binary"),
        ]:
            self.assertEqual(
                self.upload(raw, name, "broadcasts").status_code, 400, name
            )

    def test_upload_caps_enforced(self):
        with patch("system.media.MAX_BYTES", 10):
            self.assertEqual(
                self.upload(b"a" * 11, "a.txt", "broadcasts").status_code, 400
            )
        with patch("system.media.MAX_IMAGE_BYTES", 10):
            self.assertEqual(self.upload(self.image_bytes()).status_code, 400)

    def test_broadcast_upload_kind_and_section_checked(self):
        ref = self.upload(self.image_bytes()).json["ref"]
        # Service images cannot be reused to evade the broadcast upload section boundary.
        self.assertEqual(
            self.post(
                "data/broadcasts",
                {"body": "hello", "kind": "photo", "audience": "all", "media": ref},
            ).status_code,
            400,
        )
        ref = self.upload(
            b"%PDF-1.7\nexample", filename="proof.pdf", purpose="broadcasts"
        ).json["ref"]
        self.assertEqual(
            self.post(
                "data/broadcasts",
                {"body": "hello", "kind": "photo", "audience": "all", "media": ref},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "data/broadcasts",
                {"body": "hello", "kind": "document", "audience": "all", "media": ref},
            ).status_code,
            200,
        )
        aid = ref.split(":")[1]
        response = self.client.get("/api/media/" + aid)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        response.close()

    def test_upload_permissions_are_checked_on_read_and_write(self):
        ref = self.upload(self.image_bytes(), purpose="broadcasts").json["ref"]
        self.post(
            "data/staff",
            {
                "username": "serviceadmin",
                "password": "admin-password-123",
                "permissions": ["services"],
                "enabled": True,
            },
        )
        client = self.app.test_client()
        csrf = client.get("/api/session").json["csrf"]
        result = client.post(
            "/api/auth/login",
            json={"username": "serviceadmin", "password": "admin-password-123"},
            headers={"X-CSRF-Token": csrf},
        )
        csrf = result.json["csrf"]
        self.assertEqual(client.get("/api/media/" + ref.split(":")[1]).status_code, 403)
        self.assertEqual(
            self.upload(
                self.image_bytes(), purpose="broadcasts", client=client, csrf=csrf
            ).status_code,
            403,
        )
        self.assertEqual(
            self.upload(self.image_bytes(), client=client, csrf=csrf).status_code, 200
        )

    def test_telegram_upload_uses_real_multipart(self):
        ref = self.upload(self.image_bytes()).json["ref"]
        from system.telegram import call
        import io

        with patch(
            "system.telegram.urllib.request.urlopen",
            return_value=io.BytesIO(b'{"ok":true,"result":{"message_id":1}}'),
        ) as mock:
            result = call(
                "not-a-real-token",
                "sendPhoto",
                {
                    "chat_id": 123,
                    "photo": ref,
                    "caption": "hello",
                    "reply_markup": {"inline_keyboard": []},
                },
            )
        req = mock.call_args.args[0]
        self.assertIn("multipart/form-data", req.headers["Content-type"])
        self.assertIn(b"\xff\xd8", req.data)
        self.assertNotIn(ref.encode(), req.data)
        self.assertIn(b"inline_keyboard", req.data)
        self.assertEqual(result["message_id"], 1)

    def test_uploaded_service_image_is_queued_for_customer(self):
        ref = self.upload(self.image_bytes()).json["ref"]
        self.post("data/services", {"id": 1, "image": ref})
        process_update(self.update(1, callback="service:1"))
        with db() as c:
            payloads = [
                json.loads(r["payload"]) for r in rows(c, "SELECT * FROM notifications")
            ]
            self.assertTrue(
                any(
                    p["method"] == "sendPhoto" and p["data"]["photo"] == ref
                    for p in payloads
                )
            )

    def test_media_backup_includes_referenced_uploads(self):
        import backup

        ref = self.upload(self.image_bytes()).json["ref"]
        destination = Path(self.temp.name) / "snapshot"
        with patch.object(backup, "ROOT", store.ROOT):
            backup.backup(destination)
        with db() as c:
            stored = c.execute(
                "SELECT stored_name FROM assets WHERE id=?", (int(ref.split(":")[1]),)
            ).fetchone()[0]
        self.assertEqual(
            (destination / "uploads" / stored).read_bytes(),
            (store.ROOT / "uploads" / stored).read_bytes(),
        )

    def expense(self, amount="10.00", day="2026-01-10", kind="expense", key="expense1"):
        return self.post(
            "expenses",
            {
                "amount": amount,
                "kind": kind,
                "occurred_on": day,
                "reason": "تشغيل",
                "key": key,
            },
        )

    def test_expense_is_dated_and_does_not_touch_wallet(self):
        self.assertEqual(self.expense().status_code, 200)
        self.assertEqual(
            self.expense("2", "2026-02-10", "fee", "fee1").status_code, 200
        )
        jan = self.client.get("/api/stats?start=2026-01-01&end=2026-01-31").json
        feb = self.client.get("/api/stats?start=2026-02-01&end=2026-02-28").json
        self.assertEqual(
            (jan["expenses"], jan["fees"], jan["profit"]), (1000, 0, -1000)
        )
        self.assertEqual((feb["expenses"], feb["fees"], feb["profit"]), (0, 200, -200))
        with db() as c:
            self.assertEqual(one(c, "users", 123)["balance"], 10000)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM ledger").fetchone()[0], 0)

    def test_expense_retry_is_idempotent(self):
        first = self.expense()
        second = self.expense()
        self.assertEqual(first.json["id"], second.json["id"])
        self.assertEqual(self.expense("11").status_code, 400)
        with db() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 1
            )

    def test_expense_reversal_once_and_in_its_period(self):
        eid = self.expense().json["id"]
        data = {"reason": "تصحيح", "occurred_on": "2026-02-10", "key": "reverse1"}
        self.assertEqual(self.post(f"expenses/{eid}/reverse", data).status_code, 200)
        self.assertEqual(self.post(f"expenses/{eid}/reverse", data).status_code, 200)
        self.assertEqual(
            self.post(
                f"expenses/{eid}/reverse", {**data, "key": "different"}
            ).status_code,
            400,
        )
        jan = self.client.get("/api/stats?start=2026-01-01&end=2026-01-31").json
        feb = self.client.get("/api/stats?start=2026-02-01&end=2026-02-28").json
        self.assertEqual(jan["expenses"], 1000)
        self.assertEqual(feb["expenses"], -1000)
        with db() as c:
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 2
            )

    def test_expenses_cannot_be_modified_or_deleted(self):
        self.expense()
        for sql in ["DELETE FROM expenses", "UPDATE expenses SET amount=0"]:
            with self.assertRaises(sqlite3.IntegrityError):
                with db() as c:
                    c.execute(sql)
        self.assertEqual(
            self.post("data/expenses", {"id": 1, "amount": 2}).status_code, 400
        )

    def test_expense_validation_and_filters(self):
        for amount, day in [
            ("0", "2026-01-01"),
            ("-1", "2026-01-01"),
            ("NaN", "2026-01-01"),
            ("1", "2026-02-30"),
        ]:
            self.assertEqual(self.expense(amount, day).status_code, 400)
        self.expense()
        self.expense("2", "2026-02-10", key="exp2")
        result = self.client.get(
            "/api/data/expenses?start=2026-02-01&end=2026-02-28"
        ).json
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["amount"], 200)
        self.assertEqual(self.client.get("/api/stats?start=invalid").status_code, 400)
        self.assertEqual(
            self.client.get("/api/stats?start=2026-02-01&end=2026-01-01").status_code,
            400,
        )

    def test_expense_permission_independent_of_stats(self):
        self.post(
            "data/staff",
            {
                "username": "reporter",
                "password": "admin-password-123",
                "permissions": ["stats"],
                "enabled": True,
            },
        )
        client = self.app.test_client()
        csrf = client.get("/api/session").json["csrf"]
        result = client.post(
            "/api/auth/login",
            json={"username": "reporter", "password": "admin-password-123"},
            headers={"X-CSRF-Token": csrf},
        )
        csrf = result.json["csrf"]
        self.assertEqual(client.get("/api/stats").status_code, 200)
        self.assertEqual(client.get("/api/data/expenses").status_code, 403)
        self.assertEqual(
            client.post(
                "/api/expenses", json={}, headers={"X-CSRF-Token": csrf}
            ).status_code,
            403,
        )

    def test_later_refund_preserves_original_sales_period(self):
        oid = self.makeorder()
        with db() as c:
            order_status(c, oid, "processing", 1)
            order_status(c, oid, "completed", 1)
            c.execute(
                "UPDATE orders SET completed='2026-01-12T10:00:00+00:00',cost=40 WHERE id=?",
                (oid,),
            )
        with patch("system.store.now", return_value="2026-02-12T10:00:00+00:00"):
            with db() as c:
                order_status(c, oid, "refunded", 1)
        jan = self.client.get("/api/stats?start=2026-01-01&end=2026-01-31").json
        feb = self.client.get("/api/stats?start=2026-02-01&end=2026-02-28").json
        self.assertEqual(
            (jan["sales"], jan["recognized_refunds"], jan["profit"]), (100, 0, 60)
        )
        self.assertEqual(
            (feb["sales"], feb["recognized_refunds"], feb["profit"]), (0, 100, -100)
        )

    def test_pending_cancel_refund_not_counted_against_sales(self):
        oid = self.makeorder()
        with db() as c:
            order_status(c, oid, "cancelled", 1)
        s = self.client.get("/api/stats").json
        self.assertEqual(
            (s["sales"], s["refunds"], s["recognized_refunds"], s["profit"]),
            (0, 100, 0, 0),
        )

    def test_legacy_global_expense_migration_runs_once(self):
        with db() as c:
            put(c, "expenses", 150)
            put(c, "fees", 25)
            put(c, "dated_expenses_migrated", False)
        init()
        init()
        with db() as c:
            self.assertEqual(
                c.execute("SELECT SUM(amount) FROM expenses").fetchone()[0], 175
            )
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 2
            )
            self.assertEqual(setting(c, "expenses"), 0)

    def proof_topup(self, kind="photo", value="telegram-file"):
        with db() as c:
            t = topup_create(c, 123, 500, "manual")
            c.execute(
                "UPDATE topups SET status='review',proof=? WHERE id=?",
                (json.dumps({"type": kind, "value": value}), t["id"]),
            )
            return t["id"]

    def test_proof_photo_read_proxy_never_exposes_token(self):
        import io

        tid = self.proof_topup()
        with patch("system.web.token", return_value="123:secret"), patch(
            "system.telegram.call",
            return_value={"file_path": "photos/file.jpg", "file_size": 100},
        ), patch(
            "system.proofs.urllib.request.urlopen",
            return_value=io.BytesIO(self.image_bytes()),
        ):
            result = self.client.get(f"/api/topups/{tid}/proof")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.mimetype, "image/jpeg")
        self.assertTrue(result.data.startswith(b"\xff\xd8"))
        self.assertNotIn(b"secret", result.data)
        with db() as c:
            self.assertTrue(
                c.execute(
                    "SELECT 1 FROM audit WHERE action='topup.proof.viewed'"
                ).fetchone()
            )

    def test_proof_document_forces_attachment_and_keeps_private(self):
        import io

        tid = self.proof_topup("document")
        with patch("system.web.token", return_value="123:secret"), patch(
            "system.telegram.call", return_value={"file_path": "documents/file.pdf"}
        ), patch(
            "system.proofs.urllib.request.urlopen",
            return_value=io.BytesIO(b"%PDF-1.7\nproof"),
        ):
            result = self.client.get(f"/api/topups/{tid}/proof")
        self.assertEqual(result.status_code, 200)
        self.assertIn("attachment", result.headers["Content-Disposition"])
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get(f"/api/topups/{tid}/proof").status_code, 401)

    def test_proof_proxy_rejects_unsafe_path_and_oversize(self):
        from system.proofs import retrieve

        for path in (
            "https://evil.org/file",
            "../secret",
            "/etc/passwd",
            "photos/../../secrets",
        ):
            with patch("system.telegram.call", return_value={"file_path": path}):
                with self.assertRaises(ValueError):
                    retrieve("secret", "file", "photo")
        with patch(
            "system.telegram.call",
            return_value={
                "file_path": "photos/file.jpg",
                "file_size": 30 * 1024 * 1024,
            },
        ):
            with self.assertRaises(ValueError):
                retrieve("secret", "file", "photo")

    def test_proof_text_visible_in_web_without_telegram(self):
        tid = self.proof_topup("text", "reference 123")
        result = self.client.get(f"/api/topups/{tid}/proof")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["text"], "reference 123")

    def test_proof_proxy_requires_topup_permission(self):
        tid = self.proof_topup()
        self.post(
            "data/staff",
            {
                "username": "viewer",
                "password": "admin-password-123",
                "permissions": ["users"],
                "enabled": True,
            },
        )
        client = self.app.test_client()
        csrf = client.get("/api/session").json["csrf"]
        client.post(
            "/api/auth/login",
            json={"username": "viewer", "password": "admin-password-123"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(client.get(f"/api/topups/{tid}/proof").status_code, 403)

    def test_settings_still_save_without_deprecated_expense_totals(self):
        result = self.post(
            "settings", {"brand": "updated brand", "order_min": 1, "order_max": 10000}
        )
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.post("settings", {"expenses": 100}).status_code, 400)

    def test_private_upload_download_with_relative_data_dir(self):
        original = store.ROOT
        cache = Path(".cache")
        cache.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=cache) as directory:
                store.ROOT = Path(directory)
                app = create_app()
                app.testing = True
                client = app.test_client()
                csrf = client.get("/api/session").json["csrf"]
                response = client.post(
                    "/api/auth/setup",
                    json={
                        "username": "relativeowner",
                        "password": "long-safe-password",
                    },
                    headers={"X-CSRF-Token": csrf},
                )
                csrf = response.json["csrf"]
                result = self.upload(self.image_bytes(), client=client, csrf=csrf)
                self.assertEqual(result.status_code, 200, result.json)
                download = client.get(result.json["url"])
                self.assertEqual(download.status_code, 200)
                self.assertEqual(download.mimetype, "image/jpeg")
                download.close()
        finally:
            store.ROOT = original

    def test_arabic_upload_filename_is_supported(self):
        result = self.upload(self.image_bytes(), filename="صورة الخدمة.png")
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json["name"], "صورة الخدمة.jpg")
        response = self.client.get(result.json["url"])
        self.assertEqual(response.status_code, 200)
        self.assertIn("filename*=", response.headers["Content-Disposition"])
        response.close()


if __name__ == "__main__":
    unittest.main()
