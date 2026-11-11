"""Acceptance checks for editable flows, menus, locale CRUD and safe simulation."""

import json
import unittest
import test_system as fixtures
from system.store import db, one, rows
from system.telegram import action, handle_input, getstate


class StudioTest(unittest.TestCase):
    setUp = fixtures.SystemTest.setUp
    tearDown = fixtures.SystemTest.tearDown
    post = fixtures.SystemTest.post

    def workflow(self, steps):
        r = self.post("workflows", {"name": "اختبار", "steps": steps, "enabled": True})
        self.assertEqual(r.status_code, 200, r.json)
        return r.json["id"]

    def test_flow_input_and_completion(self):
        fid = self.workflow(
            [
                {"type": "input", "variable": "name", "text": "الاسم؟"},
                {"type": "message", "text": "أهلًا {name}"},
                {"type": "end"},
            ]
        )
        with db() as c:
            action(c, 123, "workflow:" + str(fid))
            self.assertEqual(getstate(c, 123)[0], "workflow")
            handle_input(c, 123, "أكرم", {})
            run = c.execute("SELECT * FROM flow_runs WHERE user_id=123").fetchone()
            self.assertEqual(run["status"], "completed")
            self.assertTrue(
                any(
                    "أهلًا أكرم" in r["payload"]
                    for r in rows(c, "SELECT payload FROM notifications")
                )
            )

    def test_flow_revision_invalidates_open_run(self):
        fid = self.workflow([{"type": "input", "variable": "name", "text": "الاسم؟"}])
        with db() as c:
            action(c, 123, "workflow:" + str(fid))
        self.post(
            "workflows",
            {
                "id": fid,
                "name": "جديد",
                "steps": [{"type": "input", "variable": "name", "text": "اسم جديد؟"}],
            },
        )
        with db() as c:
            with self.assertRaises(ValueError):
                handle_input(c, 123, "أكرم", {})

    def test_flow_numeric_validation(self):
        fid = self.workflow(
            [
                {
                    "type": "input",
                    "variable": "qty",
                    "text": "كم؟",
                    "validator": "integer",
                    "min": 1,
                    "max": 3,
                },
                {"type": "end"},
            ]
        )
        with db() as c:
            action(c, 123, "workflow:" + str(fid))
            for value in ["nan", "0", "4", "1.5"]:
                with self.assertRaises(ValueError):
                    handle_input(c, 123, value, {})
            handle_input(c, 123, "2", {})
            self.assertEqual(
                c.execute("SELECT status FROM flow_runs").fetchone()[0], "completed"
            )

    def test_flow_choice_button_styles_reach_telegram_markup(self):
        fid = self.workflow(
            [
                {
                    "type": "input",
                    "variable": "answer",
                    "text": "اختر",
                    "validator": "choice",
                    "choices": "نعم|لا",
                    "choice_styles": ["primary", "danger"],
                },
                {"type": "end"},
            ]
        )
        with db() as c:
            action(c, 123, "workflow:" + str(fid))
            message = json.loads(
                c.execute(
                    "SELECT payload FROM notifications ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]
            )
        buttons = message["data"]["reply_markup"]["inline_keyboard"]
        self.assertEqual(buttons[0][0]["style"], "primary")
        self.assertEqual(buttons[1][0]["style"], "danger")
        self.assertNotIn("style", buttons[-1][0])

    def test_flow_rejects_unknown_button_styles(self):
        response = self.post(
            "workflows",
            {
                "name": "تدفق غير صالح",
                "steps": [
                    {
                        "type": "input",
                        "variable": "answer",
                        "validator": "choice",
                        "choices": "نعم|لا",
                        "choice_styles": ["#ff00ff"],
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_changing_flow_button_color_does_not_reset_active_flow(self):
        steps = [
            {
                "type": "input",
                "variable": "answer",
                "text": "اختر",
                "validator": "choice",
                "choices": "نعم|لا",
                "choice_styles": ["default", "default"],
            },
            {"type": "end"},
        ]
        fid = self.workflow(steps)
        with db() as c:
            action(c, 123, "workflow:" + str(fid))
            revision = one(c, "workflows", fid)["revision"]
        steps[0]["choice_styles"] = ["success", "danger"]
        saved = self.post(
            "workflows", {"id": fid, "name": "اختبار", "steps": steps, "enabled": True}
        )
        self.assertEqual(saved.status_code, 200, saved.json)
        with db() as c:
            self.assertEqual(one(c, "workflows", fid)["revision"], revision)
            handle_input(c, 123, "نعم", {})
            self.assertEqual(one(c, "flow_runs", 1)["status"], "completed")

    def test_simulation_rolls_back_everything(self):
        fid = self.workflow(
            [
                {"type": "input", "variable": "name", "text": "الاسم؟"},
                {"type": "message", "text": "أهلًا {name}"},
                {"type": "end"},
            ]
        )
        with db() as c:
            before = {
                t: c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
                for t in ["users", "notifications", "sessions", "flow_runs", "audit"]
            }
        response = self.post(
            "simulate", {"route": "workflow:" + str(fid), "inputs": ["أكرم"]}
        )
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(
            any(
                "أهلًا أكرم" in p["data"].get("text", "")
                for p in response.json["messages"]
            )
        )
        with db() as c:
            for t, n in before.items():
                self.assertEqual(
                    c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0], n, t
                )

    def test_clone_menu_and_move_button(self):
        with db() as c:
            m = c.execute("SELECT id FROM menus WHERE key='home'").fetchone()[0]
            first = c.execute(
                "SELECT id FROM buttons WHERE menu_id=? ORDER BY id LIMIT 1", (m,)
            ).fetchone()[0]
            c.execute("UPDATE buttons SET style='success' WHERE id=?", (first,))
        r = self.post("studio/clone-menu", {"id": m, "key": "home_copy"})
        self.assertEqual(r.status_code, 200, r.json)
        with db() as c:
            bs = rows(c, "SELECT * FROM buttons WHERE menu_id=?", (r.json["id"],))
            self.assertTrue(bs)
            self.assertEqual(bs[0]["style"], "success")
        self.assertEqual(
            self.post(
                "studio/move-button", {"id": bs[0]["id"], "direction": "down"}
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/data/menus").status_code, 200)

    def test_locales_and_translations_crud(self):
        self.assertEqual(
            self.post(
                "data/locales", {"code": "en", "name": "English", "enabled": True}
            ).status_code,
            200,
        )
        r = self.post(
            "data/translations", {"locale": "en", "token": "menu:home", "text": "Hello"}
        )
        self.assertEqual(r.status_code, 200, r.json)
        for t in ["locales", "translations", "workflows"]:
            self.assertEqual(self.client.get("/api/data/" + t).status_code, 200)
        self.assertEqual(
            self.post("data/locales", {"code": "BAD", "name": "bad"}).status_code, 400
        )
        self.assertEqual(
            self.post(
                "data/translations",
                {"locale": "xx", "token": "menu:home", "text": "no"},
            ).status_code,
            400,
        )

    def test_bad_condition_is_rejected(self):
        r = self.post(
            "workflows",
            {"name": "bad", "steps": [{"type": "condition", "yes": 20, "no": 0}]},
        )
        self.assertEqual(r.status_code, 400)
