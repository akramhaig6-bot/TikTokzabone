import csv, io, json, os, secrets, time
from collections import defaultdict, deque
from functools import wraps
from pathlib import Path
from datetime import date, datetime
from flask import Flask, request, session, jsonify, send_from_directory, Response
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from . import store
from .store import *
from .domain import *
from .accounting import expense_add
from . import media
from .flows import validate_steps
from .studio import check_key, menu_clone, button_move

BASE = Path(__file__).resolve().parent.parent
LIMITS = defaultdict(deque)
SCHEMAS = {
    "services": {
        "name": "text",
        "price": "money",
        "cost": "money",
        "min_qty": "int",
        "max_qty": "int",
        "description": "text",
        "image": "text",
        "target_type": "any|profile|video",
        "enabled": "bool",
        "position": "int",
    },
    "inventory": {
        "username": "text",
        "note": "text",
        "status": "available|reserved|used|unavailable",
    },
    "menus": {
        "name": "text",
        "key": "text",
        "text": "text",
        "kind": "inline|reply|text|multilevel",
        "layout_key": "text",
    },
    "buttons": {
        "menu_id": "int",
        "label": "text",
        "kind": "callback|reply|url|webapp",
        "action": "callback|services|topup|myorders|account|support|menu|message|order|ledger|tickets|topups|admin|workflow|language|none",
        "target": "text",
        "row_num": "int",
        "col_num": "int",
        "enabled": "bool",
        "permission": "text",
        "child_menu": "text",
    },
    "locales": {"code": "text", "name": "text", "enabled": "bool"},
    "translations": {"locale": "text", "token": "text", "text": "text"},
    "broadcasts": {
        "body": "text",
        "kind": "text|photo|video|document",
        "media": "text",
        "audience": "all|active|balance|orders",
    },
}
TABLE_PERM = {
    "workflows": "menus",
    "flow_runs": "menus",
    "translations": "menus",
    "locales": "settings",
    "expenses": "expenses",
    "assets": "audit",
    "deliveries": "broadcasts",
    "tickets": "support",
    "messages": "support",
    "payments": "ledger",
    "notifications": "audit",
    "buttons": "menus",
    **{
        k: k
        for k in [
            "orders",
            "topups",
            "users",
            "services",
            "inventory",
            "menus",
            "staff",
            "ledger",
            "audit",
            "broadcasts",
        ]
    },
}


def keyfile(name, generate):
    p = store.ROOT / name
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(generate())
    return p.read_bytes()


def cipher():
    return Fernet(keyfile("encryption.key", Fernet.generate_key))


def token(c):
    encrypted = setting(c, "telegram_token", "")
    return cipher().decrypt(encrypted.encode()).decode() if encrypted else ""


def clean_staff(r):
    return {k: v for k, v in r.items() if k != "password"}


def allowed(actor, perm):
    return actor["role"] == "owner" or perm in json.loads(actor["permissions"])


def require(perm=None):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            with db() as c:
                a = c.execute(
                    "SELECT * FROM staff WHERE id=? AND enabled=1",
                    (session.get("uid", -1),),
                ).fetchone()
                if not a or a["auth_version"] != session.get("auth_version", 0):
                    session.clear()
                    return jsonify(error="سجل الدخول أولًا"), 401
                actor = dict(a)
            if perm and not allowed(actor, perm):
                return jsonify(error="⛔ لا تمتلك صلاحية تنفيذ هذا الإجراء"), 403
            request.actor = actor
            return fn(*args, **kwargs)

        return wrapped

    return deco


def create_app():
    init()
    app = Flask(__name__, static_folder=None)
    app.secret_key = keyfile("session.key", lambda: secrets.token_bytes(48))
    app.config.update(
        MAX_CONTENT_LENGTH=media.MAX_BYTES + 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=(
            "None" if os.getenv("COOKIE_PARTITIONED") == "1" else "Strict"
        ),
        SESSION_COOKIE_PARTITIONED=os.getenv("COOKIE_PARTITIONED") == "1",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
        PERMANENT_SESSION_LIFETIME=28800,
    )

    @app.before_request
    def csrf():
        if request.path.startswith("/api/") and request.method not in (
            "GET",
            "HEAD",
            "OPTIONS",
        ):
            if not session.get("csrf") or not secrets.compare_digest(
                request.headers.get("X-CSRF-Token", ""), session["csrf"]
            ):
                return jsonify(error="انتهت جلسة الأمان. حدّث الصفحة."), 403

    @app.after_request
    def headers(r):
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "same-origin"
        r.headers["Cache-Control"] = "no-store"
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'; frame-ancestors 'self' https://*.arena.ai https://arena.ai https://*.e2b.app"
        )
        return r

    @app.errorhandler(413)
    def too_large(e):
        return jsonify(error="حجم الرفع يتجاوز 20 ميجابايت"), 413

    @app.errorhandler(ValueError)
    def invalid(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(sqlite3.IntegrityError)
    def conflict(e):
        return (
            jsonify(
                error="تعارض بيانات: سجل مكرر أو ارتباط غير صالح أو قيمة خارج الحدود."
            ),
            409,
        )

    @app.errorhandler(404)
    def missing(e):
        return jsonify(error="المسار غير موجود"), 404

    @app.get("/")
    def index():
        return send_from_directory(BASE / "static", "index.html")

    @app.get("/static/<path:name>")
    def static(name):
        return send_from_directory(BASE / "static", name)

    @app.get("/api/session")
    def identity():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        with db() as c:
            count = c.execute("SELECT COUNT(*) FROM staff").fetchone()[0]
            a = c.execute(
                "SELECT * FROM staff WHERE id=? AND enabled=1",
                (session.get("uid", -1),),
            ).fetchone()
        return jsonify(
            csrf=session["csrf"],
            setup=count == 0,
            actor=(
                clean_staff(dict(a))
                if a and a["auth_version"] == session.get("auth_version", 0)
                else None
            ),
        )

    @app.post("/api/auth/<action>")
    def auth(action):
        key = request.remote_addr
        q = LIMITS[key]
        t = time.time()
        while q and q[0] < t - 300:
            q.popleft()
        if len(q) >= 10:
            return jsonify(error="محاولات كثيرة. انتظر خمس دقائق."), 429
        q.append(t)
        d = request.get_json()
        with db() as c:
            if action == "setup":
                if c.execute("SELECT 1 FROM staff").fetchone():
                    raise ValueError("تم إعداد المالك مسبقًا")
                # Optional deployment setup secret protects an unclaimed public installation.
                secret = os.getenv("SETUP_SECRET", "")
                if secret and not secrets.compare_digest(
                    secret, d.get("setup_secret", "")
                ):
                    return jsonify(error="رمز التهيئة غير صحيح"), 403
                if len(d.get("password", "")) < 12 or not d.get("username", "").strip():
                    raise ValueError("اختر اسم دخول وكلمة مرور لا تقل عن 12 حرفًا")
                uid = c.execute(
                    "INSERT INTO staff(username,password,role,created) VALUES(?,?,'owner',?)",
                    (
                        d["username"].strip(),
                        generate_password_hash(d["password"]),
                        now(),
                    ),
                ).lastrowid
                audit(c, uid, "owner.setup", uid, {})
            elif action == "login":
                a = c.execute(
                    "SELECT * FROM staff WHERE username=? AND enabled=1",
                    (d.get("username"),),
                ).fetchone()
                if not a or not check_password_hash(
                    a["password"], d.get("password", "")
                ):
                    return jsonify(error="بيانات الدخول غير صحيحة"), 401
                uid = a["id"]
                c.execute("UPDATE staff SET last_active=? WHERE id=?", (now(), uid))
            elif action == "logout":
                session.clear()
                return jsonify(ok=True)
            else:
                raise ValueError("عملية غير صالحة")
        session.clear()
        session["uid"] = uid
        with db() as c:
            session["auth_version"] = one(c, "staff", uid)["auth_version"]
        session["csrf"] = secrets.token_urlsafe(32)
        session.permanent = True
        return jsonify(ok=True, csrf=session["csrf"])

    @app.post("/api/password")
    @require()
    def password_change():
        d = request.get_json()
        if not check_password_hash(request.actor["password"], d.get("current", "")):
            raise ValueError("كلمة المرور الحالية غير صحيحة")
        if len(d.get("new", "")) < 12:
            raise ValueError("كلمة المرور الجديدة لا تقل عن 12 حرفًا")
        with db() as c:
            c.execute(
                "UPDATE staff SET password=?,auth_version=auth_version+1 WHERE id=?",
                (generate_password_hash(d["new"]), request.actor["id"]),
            )
            session["auth_version"] = one(c, "staff", request.actor["id"])[
                "auth_version"
            ]
            audit(
                c,
                request.actor["id"],
                "staff.password_changed",
                request.actor["id"],
                {},
            )
        return jsonify(ok=True)

    @app.post("/api/media")
    @require()
    def upload_media():
        purpose = request.form.get("purpose", "")
        if purpose not in media.PURPOSES or not allowed(request.actor, purpose):
            return jsonify(error="لا تملك صلاحية رفع ملفات لهذا القسم"), 403
        result = media.upload(request.files.get("file"), purpose, request.actor["id"])
        return jsonify(result)

    @app.get("/api/media/<int:aid>")
    @require()
    def download_media(aid):
        with db() as c:
            record, path = media.asset(c, "upload:" + str(aid))
        if not allowed(request.actor, record["purpose"]):
            return jsonify(error="غير مصرح بعرض هذا الملف"), 403
        # Only re-encoded images are shown inline. Documents/videos are attachments.
        return send_from_directory(
            path.parent.resolve(),
            path.name,
            mimetype=record["mime"],
            as_attachment=record["kind"] != "photo",
            download_name=record["name"],
        )

    @app.get("/api/topups/<int:tid>/proof")
    @require("topups")
    def proof_file(tid):
        with db() as c:
            topup = one(c, "topups", tid)
            if not topup["proof"]:
                raise ValueError("لم يُرفق إثبات لهذا الطلب")
            try:
                proof = json.loads(topup["proof"])
            except (ValueError, TypeError):
                proof = {"type": "text", "value": topup["proof"]}
            if not isinstance(proof, dict):
                proof = {"type": "text", "value": str(proof)}
            audit(
                c,
                request.actor["id"],
                "topup.proof.viewed",
                tid,
                {"type": proof.get("type", "text")},
            )
            if proof.get("type") not in ("photo", "document"):
                return jsonify(type="text", text=proof.get("value", ""))
            bot_token = token(c)
        if not bot_token:
            raise ValueError("اربط البوت أولًا لتحميل الإثبات من Telegram")
        from .proofs import retrieve

        try:
            content, mime, extension = retrieve(
                bot_token, proof["value"], proof["type"]
            )
        except RuntimeError as e:
            return jsonify(error=str(e)), 502
        disposition = "inline" if proof["type"] == "photo" else "attachment"
        return Response(
            content,
            mimetype=mime,
            headers={
                "Content-Disposition": f'{disposition}; filename="TOP-{tid:05d}{extension}"'
            },
        )

    @app.post("/api/expenses")
    @require("expenses")
    def save_expense():
        d = request.get_json()
        with db() as c:
            eid = expense_add(
                c,
                d.get("kind"),
                cents(d.get("amount")),
                d.get("reason", ""),
                d.get("occurred_on", ""),
                request.actor["id"],
                d.get("key"),
            )
        return jsonify(ok=True, id=eid)

    @app.post("/api/expenses/<int:eid>/reverse")
    @require("expenses")
    def reverse_expense(eid):
        d = request.get_json()
        with db() as c:
            original = one(c, "expenses", eid)
            result = expense_add(
                c,
                original["kind"],
                -original["amount"],
                d.get("reason", ""),
                d.get("occurred_on", ""),
                request.actor["id"],
                d.get("key"),
                eid,
            )
        return jsonify(ok=True, id=result)

    @app.get("/api/bootstrap")
    @require()
    def bootstrap():
        with db() as c:
            settings = {
                r["key"]: json.loads(r["value"])
                for r in c.execute(
                    "SELECT * FROM settings WHERE key NOT IN ('telegram_token','poll_offset')"
                )
            }
            connected = bool(setting(c, "telegram_token"))
            menu_options = (
                rows(c, "SELECT id,key,name,kind,layout_key FROM menus ORDER BY id")
                if allowed(request.actor, "menus")
                else []
            )
            locales = rows(c, "SELECT * FROM locales ORDER BY id")
            service_options = rows(
                c, "SELECT id,name FROM services WHERE enabled=1 AND deleted=0"
            )

        from .telegram import runtime

        return jsonify(
            actor=clean_staff(request.actor),
            permissions=PERMISSIONS,
            schemas=SCHEMAS,
            settings=(
                settings
                if allowed(request.actor, "settings")
                else {"brand": settings["brand"]}
            ),
            connected=connected,
            menus=menu_options,
            locales=locales,
            services=service_options,
            runtime=runtime,
        )

    @app.post("/api/simulate")
    @require("menus")
    def simulate():
        from .telegram import action, handle_input, upsert, getstate

        d = request.get_json()
        inputs = d.get("inputs", [])
        if (
            not isinstance(inputs, list)
            or len(inputs) > 100
            or any(not isinstance(x, str) for x in inputs)
        ):
            raise ValueError("مدخلات محاكاة غير صالحة")
        uid = -secrets.randbelow(2**40) - 1
        with db() as c:
            c.execute("SAVEPOINT simulation")
            try:
                upsert(c, {"id": uid, "username": "preview", "first_name": "معاينة"})
                c.execute("UPDATE users SET balance=10000 WHERE id=?", (uid,))
                action(c, uid, d.get("route", "home"))
                for value in inputs:
                    handle_input(c, uid, value, {})
                payloads = [
                    json.loads(r["payload"])
                    for r in rows(c, "SELECT payload FROM notifications ORDER BY id")
                ]
                result = [p for p in payloads if p["data"].get("chat_id") == uid]
                st, data = getstate(c, uid)
            finally:
                c.execute("ROLLBACK TO simulation")
                c.execute("RELEASE simulation")
        return jsonify(messages=result, state=st)

    @app.post("/api/workflows")
    @require("menus")
    def save_workflow():
        data = request.get_json()
        steps = validate_steps(data.get("steps"))
        if not isinstance(data.get("name"), str) or not data["name"].strip():
            raise ValueError("اسم التدفق مطلوب")
        with db() as c:
            for step in steps:
                if step["type"] == "menu" and "{" not in step.get("target", ""):
                    if not c.execute(
                        "SELECT 1 FROM menus WHERE key=?", (step.get("target"),)
                    ).fetchone():
                        raise ValueError("القائمة المرتبطة بخطوة غير موجودة")
            if data.get("id"):
                old = one(c, "workflows", data["id"])
                fid = old["id"]
                c.execute(
                    "UPDATE workflows SET name=?,enabled=?,steps=?,revision=revision+?,updated=? WHERE id=?",
                    (
                        data["name"],
                        int(bool(data.get("enabled", True))),
                        json.dumps(steps, ensure_ascii=False),
                        int(json.loads(old["steps"]) != steps),
                        now(),
                        fid,
                    ),
                )
            else:
                fid = c.execute(
                    "INSERT INTO workflows(name,steps,enabled,created,updated) VALUES(?,?,?,?,?)",
                    (
                        data["name"],
                        json.dumps(steps, ensure_ascii=False),
                        int(bool(data.get("enabled", True))),
                        now(),
                        now(),
                    ),
                ).lastrowid
            audit(c, request.actor["id"], "workflow.saved", fid, {"steps": len(steps)})
        return jsonify(ok=True, id=fid)

    @app.post("/api/studio/<operation>")
    @require("menus")
    def studio(operation):
        d = request.get_json()
        with db() as c:
            if operation == "clone-menu":
                result = menu_clone(
                    c,
                    int(d["id"]),
                    d.get("key", ""),
                    d.get("name", ""),
                    request.actor["id"],
                )
            elif operation == "move-button":
                button_move(c, int(d["id"]), d.get("direction"), request.actor["id"])
                result = d["id"]
            elif operation == "bind-screen":
                screen = c.execute(
                    "SELECT * FROM menus WHERE key=?", (d.get("screen"),)
                ).fetchone()
                if not screen:
                    raise ValueError("رسالة الشاشة غير موجودة")
                layout = d.get("layout", "")
                if (
                    layout
                    and not c.execute(
                        "SELECT 1 FROM menus WHERE key=?", (layout,)
                    ).fetchone()
                ):
                    raise ValueError("تخطيط الأزرار غير موجود")
                c.execute(
                    "UPDATE menus SET layout_key=? WHERE key=?", (layout, screen["key"])
                )
                result = screen["id"]
                audit(
                    c, request.actor["id"], "screen.bound", result, {"layout": layout}
                )
            else:
                raise ValueError("إجراء محرر غير معروف")
        return jsonify(ok=True, id=result)

    @app.get("/api/stats")
    @require("stats")
    def statistics():
        with db() as c:
            start = request.args.get("start", "")
            end = request.args.get("end", "9999")
            for value in (start, end):
                if value not in ("", "9999"):
                    try:
                        datetime.fromisoformat(value)
                    except ValueError:
                        raise ValueError("الفترة الزمنية غير صالحة")
            if len(end) == 10:
                end += "T23:59:59.999999+00:00"
            if start and start > end:
                raise ValueError("بداية الفترة يجب ألا تتجاوز نهايتها")
            result = stats(c, start, end)
        if request.args.get("format") == "csv":
            f = io.StringIO()
            w = csv.writer(f)
            w.writerow(["metric", "value"])
            for k, v in result.items():
                if not isinstance(v, list):
                    w.writerow([k, v / 100 if k not in ("users", "orders") else v])
            return Response(
                "\ufeff" + f.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment; filename=report.csv"},
            )
        return jsonify(result)

    @app.get("/api/data/<table>")
    @require()
    def listing(table):
        if table not in TABLE_PERM or not allowed(request.actor, TABLE_PERM[table]):
            return jsonify(error="غير مصرح"), 403
        page = max(1, int(request.args.get("page", 1)))
        size = 25
        with db() as c:
            cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})")]
            where = []
            args = []
            if "deleted" in cols:
                where.append("deleted=0")
            query = request.args.get("q", "").strip()
            if query:
                searchable = [k for k in cols if k not in ("password", "payload")]
                where.append(
                    "("
                    + " OR ".join(f"CAST({k} AS TEXT) LIKE ?" for k in searchable)
                    + ")"
                )
                args.extend(["%" + query + "%"] * len(searchable))
            for k in (
                "status",
                "user_id",
                "ticket_id",
                "menu_id",
                "order_id",
                "entity",
                "broadcast_id",
            ):
                if k in cols and request.args.get(k):
                    where.append(f"{k}=?")
                    args.append(request.args[k])
            if table == "expenses":
                for arg, op in (("start", ">="), ("end", "<=")):
                    if request.args.get(arg):
                        date.fromisoformat(request.args[arg])
                        where.append("occurred_on" + op + "?")
                        args.append(request.args[arg])
            clause = " WHERE " + " AND ".join(where) if where else ""
            total = c.execute(
                f"SELECT COUNT(*) FROM {table}" + clause, args
            ).fetchone()[0]
            order_by = "id DESC"
            if table == "menus":
                order_by = "CASE WHEN key IN ('home','services','topup','account','myorders','support','maintenance','error','expired') THEN 0 WHEN key LIKE 'layout_%' THEN 1 WHEN key LIKE 'label_%' THEN 3 ELSE 2 END,id"
            if table == "services":
                order_by = "position,id"
            rr = rows(
                c,
                f"SELECT * FROM {table}"
                + clause
                + f" ORDER BY {order_by} LIMIT ? OFFSET ?",
                args + [size, (page - 1) * size],
            )
            if table == "users":
                for r in rr:
                    r["order_count"] = c.execute(
                        "SELECT COUNT(*) FROM orders WHERE user_id=?", (r["id"],)
                    ).fetchone()[0]
                    r["completed_orders"] = c.execute(
                        "SELECT COUNT(*) FROM orders WHERE user_id=? AND status='completed'",
                        (r["id"],),
                    ).fetchone()[0]
                    r["pending_orders"] = c.execute(
                        "SELECT COUNT(*) FROM orders WHERE user_id=? AND status='pending'",
                        (r["id"],),
                    ).fetchone()[0]
                    r["total_topups"] = c.execute(
                        "SELECT COALESCE(SUM(amount),0) FROM topups WHERE user_id=? AND status='approved'",
                        (r["id"],),
                    ).fetchone()[0]
            if table == "staff":
                rr = [clean_staff(r) for r in rr]
            if table == "topups":
                for r in rr:
                    r.pop("payload", None)
            if table == "broadcasts":
                for r in rr:
                    r["report"] = rows(
                        c,
                        "SELECT status,COUNT(*) count FROM deliveries WHERE broadcast_id=? GROUP BY status",
                        (r["id"],),
                    )
        return jsonify(
            items=rr, total=total, page=page, pages=max(1, (total + size - 1) // size)
        )

    @app.post("/api/data/<table>")
    @require()
    def save(table):
        perm = TABLE_PERM.get(table)
        if not perm or not allowed(request.actor, perm):
            return jsonify(error="غير مصرح"), 403
        d = request.get_json()
        rid = d.pop("id", None)
        actor = request.actor
        if table == "staff":
            if d.get("role", "admin") != "admin":
                raise ValueError("لا يمكن إضافة مالك آخر")
            permissions = d.get("permissions", [])
            if not isinstance(permissions, list) or any(
                p not in PERMISSIONS for p in permissions
            ):
                raise ValueError("صلاحيات غير صالحة")
            if actor["role"] != "owner" and not set(permissions).issubset(
                set(json.loads(actor["permissions"]))
            ):
                raise ValueError("لا يمكن منح صلاحيات لا تمتلكها")
            v = {
                "username": d.get("username", "").strip(),
                "permissions": json.dumps(permissions),
                "telegram_id": int(d["telegram_id"]) if d.get("telegram_id") else None,
                "enabled": int(bool(d.get("enabled", True))),
            }
            if not v["username"]:
                raise ValueError("اسم الدخول مطلوب")
            if d.get("password"):
                if len(d["password"]) < 12:
                    raise ValueError("كلمة المرور لا تقل عن 12 حرفًا")
                v["password"] = generate_password_hash(d["password"])
            elif not rid:
                raise ValueError("كلمة المرور مطلوبة")
        elif table in SCHEMAS:
            v = {}
            for k, typ in SCHEMAS[table].items():
                if k not in d:
                    continue
                val = d[k]
                if typ == "money":
                    val = cents(val)
                elif typ == "int":
                    val = int(val)
                elif typ == "bool":
                    val = int(bool(val))
                elif "|" in typ:
                    if val not in typ.split("|"):
                        raise ValueError("قيمة غير مسموحة: " + k)
                else:
                    val = str(val)
                v[k] = val
        else:
            raise ValueError("استخدم الإجراء المخصص لتعديل هذا السجل")
        with db() as c:
            before = one(c, table, rid) if rid else {}
            if (
                table == "staff"
                and rid
                and (before["role"] == "owner" or rid == actor["id"])
            ):
                raise ValueError("لا يمكن تعديل المالك أو صلاحياتك الذاتية")
            merged = {**before, **v}
            if (
                table == "menus"
                and rid
                and v.get("key", before["key"]) != before["key"]
            ):
                raise ValueError(
                    "معرف القائمة ثابت لحماية الأزرار المرتبطة؛ يمكنك تعديل الاسم والنص والنوع"
                )
            if table == "menus":
                check_key(merged.get("key", ""))
                if (
                    merged.get("layout_key")
                    and not c.execute(
                        "SELECT 1 FROM menus WHERE key=?", (merged["layout_key"],)
                    ).fetchone()
                ):
                    raise ValueError("تخطيط الأزرار المرتبط غير موجود")
            if table == "locales":
                import re

                if not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", merged.get("code", "")):
                    raise ValueError("رمز اللغة مثل ar أو en أو en-US")
                if before and merged["code"] != before["code"]:
                    raise ValueError("رمز اللغة ثابت لحفظ الترجمات")
            if table == "translations":
                if not c.execute(
                    "SELECT 1 FROM locales WHERE code=?", (merged.get("locale"),)
                ).fetchone():
                    raise ValueError("اللغة غير موجودة")
                token = merged.get("token", "")
                if not token.startswith(("menu:", "button:")):
                    raise ValueError("مفتاح الترجمة يبدأ بـ menu: أو button:")
            if table == "services":
                if (
                    not merged.get("name")
                    or merged.get("price", -1) < 0
                    or merged.get("cost", 0) < 0
                    or not 1
                    <= merged.get("min_qty", 100)
                    <= merged.get("max_qty", 100000)
                    <= 100000000
                ):
                    raise ValueError("تحقق من اسم الخدمة والسعر وحدود الكمية")
            if table == "services" and merged.get("image"):
                if merged["image"].startswith("upload:"):
                    media.asset(c, merged["image"], kind="photo", purpose="services")
                elif not merged["image"].startswith("https://"):
                    raise ValueError("الصورة يجب أن تكون رفعًا محليًا أو رابط HTTPS")
            if table == "broadcasts":
                kind = merged.get("kind", "text")
                body = merged.get("body", "")
                ref = merged.get("media", "")
                if len(body) > (4096 if kind == "text" else 1024):
                    raise ValueError(
                        "النص لا يتجاوز 4096 حرفًا أو 1024 حرفًا لوصف الوسائط"
                    )
                if kind != "text":
                    if not ref:
                        raise ValueError("ارفع ملفًا أو أدخل رابط الوسائط أولًا")
                    if ref.startswith("upload:"):
                        media.asset(c, ref, kind=kind, purpose="broadcasts")
            if table == "buttons":
                if merged.get("row_num", 0) < 0 or merged.get("col_num", 0) < 0:
                    raise ValueError("الصف والعمود لا يكونان سالبين")
                if (
                    merged.get("child_menu")
                    and not c.execute(
                        "SELECT 1 FROM menus WHERE key=?", (merged["child_menu"],)
                    ).fetchone()
                ):
                    raise ValueError("القائمة الفرعية غير موجودة")
                if merged.get("action") == "workflow":
                    one(c, "workflows", int(merged.get("target", 0)))
                if merged.get("action") == "menu":
                    if not c.execute(
                        "SELECT 1 FROM menus WHERE key=?", (merged.get("target"),)
                    ).fetchone():
                        raise ValueError("القائمة المستهدفة غير موجودة")
                if merged.get("kind") in ("url", "webapp") and not str(
                    merged.get("target", "")
                ).startswith("https://"):
                    raise ValueError("الرابط يجب أن يبدأ بـ https://")
                if merged.get("permission") and merged["permission"] not in PERMISSIONS:
                    raise ValueError("صلاحية غير معروفة")
            if table == "inventory":
                v.update(updated=now(), updated_by=str(actor["id"]))
                if not rid:
                    v.update(created=now(), added_by=str(actor["id"]))
            if table in ("staff", "broadcasts") and not rid:
                v["created"] = now()
            if table == "staff":
                if not rid:
                    v["added_by"] = str(actor["id"])
                elif "password" in v:
                    v["auth_version"] = before["auth_version"] + 1
            if table == "broadcasts" and rid and before["status"] != "draft":
                raise ValueError("لا يمكن تعديل إذاعة بدأت؛ أنشئ إذاعة جديدة")
            if not v:
                raise ValueError("لا توجد تعديلات لحفظها")
            if rid:
                c.execute(
                    f"UPDATE {table} SET "
                    + ",".join(k + "=?" for k in v)
                    + " WHERE id=?",
                    list(v.values()) + [rid],
                )
            else:
                rid = c.execute(
                    f"INSERT INTO {table}("
                    + ",".join(v)
                    + ") VALUES("
                    + ",".join("?" for _ in v)
                    + ")",
                    list(v.values()),
                ).lastrowid
            audit(
                c,
                actor["id"],
                table + ".save",
                rid,
                {
                    "fields": list(v),
                    "before": {k: x for k, x in before.items() if k != "password"},
                },
            )
        return jsonify(ok=True, id=rid)

    @app.post("/api/delete/<table>/<int:rid>")
    @require()
    def delete(table, rid):
        if table not in (
            "services",
            "inventory",
            "staff",
            "menus",
            "buttons",
        ) or not allowed(request.actor, TABLE_PERM[table]):
            return jsonify(error="غير مصرح"), 403
        with db() as c:
            before = one(c, table, rid)
            if table == "staff":
                if before["role"] == "owner" or rid == request.actor["id"]:
                    raise ValueError("لا يمكن حذف المالك أو حسابك")
                c.execute("UPDATE staff SET enabled=0 WHERE id=?", (rid,))
            elif table in ("services", "inventory"):
                c.execute(f"UPDATE {table} SET deleted=1 WHERE id=?", (rid,))
            elif table == "menus":
                if (
                    c.execute(
                        "SELECT 1 FROM menus WHERE layout_key=?", (before["key"],)
                    ).fetchone()
                    or c.execute(
                        "SELECT 1 FROM buttons WHERE child_menu=?", (before["key"],)
                    ).fetchone()
                ):
                    raise ValueError(
                        "القائمة مستخدمة كتخطيط أو كقائمة فرعية؛ أزل الروابط أولًا"
                    )
                if before["key"] in (
                    "home",
                    "services",
                    "topup",
                    "account",
                    "myorders",
                    "support",
                    "maintenance",
                    "error",
                    "expired",
                ):
                    raise ValueError("قائمة نظام أساسية: يمكنك تعديلها دون حذفها")
                if c.execute(
                    "SELECT 1 FROM buttons WHERE action='menu' AND target=?",
                    (before["key"],),
                ).fetchone():
                    raise ValueError("أزل الأزرار المؤدية للقائمة أولًا")
                c.execute("DELETE FROM buttons WHERE menu_id=?", (rid,))
                c.execute("DELETE FROM menus WHERE id=?", (rid,))
            else:
                c.execute("DELETE FROM buttons WHERE id=?", (rid,))
            audit(
                c,
                request.actor["id"],
                table + ".delete",
                rid,
                {k: v for k, v in before.items() if k != "password"},
            )
        return jsonify(ok=True)

    @app.post("/api/action/<action>")
    @require()
    def action(action):
        perms = {
            "order": "orders",
            "topup": "topups_approve",
            "topup_note": "topups",
            "broadcast_retry": "broadcasts",
            "balance": "balances",
            "user": "users_manage",
            "ticket": "support",
            "reply": "support",
            "broadcast": "broadcasts",
            "proof": "topups",
            "retry_notification": "audit",
        }
        if action not in perms or not allowed(request.actor, perms[action]):
            return jsonify(error="غير مصرح"), 403
        d = request.get_json()
        actor = request.actor["id"]
        with db() as c:
            if action == "order":
                if d.get("status"):
                    order_status(
                        c, int(d["id"]), d["status"], actor, note=d.get("note", "")
                    )
                else:
                    o = one(c, "orders", d["id"])
                    if "cost" in d and cents(d["cost"]) < 0:
                        raise ValueError("تكلفة التنفيذ لا تكون سالبة")
                    c.execute(
                        "UPDATE orders SET note=?,cost=?,updated=? WHERE id=?",
                        (
                            d.get("note", o["note"]),
                            cents(d["cost"]) if "cost" in d else o["cost"],
                            now(),
                            o["id"],
                        ),
                    )
            elif action == "topup_note":
                t = one(c, "topups", d["id"])
                c.execute(
                    "UPDATE topups SET note=?,updated=? WHERE id=?",
                    (d.get("note", ""), now(), t["id"]),
                )
            elif action == "broadcast_retry":
                b = one(c, "broadcasts", d["id"])
                if b["status"] not in ("completed", "stopped", "paused"):
                    raise ValueError("أوقف الإذاعة قبل إعادة محاولة الفاشلة")
                c.execute(
                    "UPDATE deliveries SET status='pending',error='' WHERE broadcast_id=? AND status='failed'",
                    (b["id"],),
                )
                c.execute(
                    "UPDATE broadcasts SET status='paused' WHERE id=?", (b["id"],)
                )
            elif action == "topup":
                topup_review(c, int(d["id"]), d["accept"], d.get("reason", ""), actor)
            elif action == "balance":
                if not d.get("reason", "").strip() or not d.get("key"):
                    raise ValueError("السبب ومعرف العملية مطلوبان")
                delta = cents(d["amount"])
                if not delta:
                    raise ValueError("المبلغ لا يمكن أن يكون صفرًا")
                ledger(
                    c,
                    int(d["user_id"]),
                    delta,
                    d["reason"],
                    actor,
                    "manual:" + d["key"],
                )
            elif action == "user":
                u = one(c, "users", d["id"])
                status = d.get("status", u["status"])
                if status not in ("active", "blocked"):
                    raise ValueError("حالة غير صالحة")
                c.execute(
                    "UPDATE users SET status=?,note=? WHERE id=?",
                    (status, d.get("note", u["note"]), u["id"]),
                )
            elif action in ("ticket", "reply"):
                t = one(c, "tickets", d["id"])
                if action == "reply":
                    ticket_message(c, t["id"], actor, d["body"], True)
                else:
                    if d["status"] not in ("open", "processing", "closed"):
                        raise ValueError("حالة غير صالحة")
                    c.execute(
                        "UPDATE tickets SET status=?,updated=? WHERE id=?",
                        (d["status"], now(), t["id"]),
                    )
                    notify(
                        c,
                        t["user_id"],
                        render(
                            c,
                            "notification_ticket_status",
                            "🎧 SUP-{id}: {status}",
                            {
                                "id": f"{t['id']:05d}",
                                "status": state_label(c, d["status"]),
                            },
                        ),
                    )
            elif action == "proof":
                t = one(c, "topups", d["id"])
                proof = (
                    json.loads(t["proof"])
                    if t["proof"].startswith("{")
                    else {"type": "text", "value": t["proof"]}
                )
                if proof.get("type") in ("photo", "document"):
                    notify(
                        c,
                        request.actor["telegram_id"] or setting(c, "owner_telegram_id"),
                        "",
                        method=(
                            "sendPhoto" if proof["type"] == "photo" else "sendDocument"
                        ),
                        extra={
                            proof["type"]: proof["value"],
                            "caption": f"TOP-{t['id']:05d}",
                        },
                    )
                else:
                    return jsonify(ok=True, proof=proof.get("value", ""))
            elif action == "retry_notification":
                n = one(c, "notifications", d["id"])
                if n["status"] != "failed":
                    raise ValueError("يمكن إعادة محاولة الإشعارات الفاشلة فقط")
                c.execute(
                    "UPDATE notifications SET status='pending',attempts=0,error='' WHERE id=?",
                    (n["id"],),
                )
            elif action == "broadcast":
                b = one(c, "broadcasts", d["id"])
                status = d["status"]
                transitions = {
                    "draft": {"running", "stopped"},
                    "running": {"paused", "stopped"},
                    "paused": {"running", "stopped"},
                }
                if status not in transitions.get(b["status"], set()):
                    raise ValueError("انتقال إذاعة غير مسموح")
                if b["status"] == "draft" and status == "running":
                    if not b["body"] and not b["media"]:
                        raise ValueError("محتوى الإذاعة فارغ")
                    filt = {
                        "all": "1=1",
                        "active": "status='active'",
                        "balance": "balance>0",
                        "orders": "EXISTS(SELECT 1 FROM orders WHERE orders.user_id=users.id)",
                    }[b["audience"]]
                    c.execute(
                        "INSERT OR IGNORE INTO deliveries(broadcast_id,user_id) SELECT ?,id FROM users WHERE "
                        + filt,
                        (b["id"],),
                    )
                c.execute(
                    "UPDATE broadcasts SET status=? WHERE id=?", (status, b["id"])
                )
            audit(c, actor, "action." + action, d.get("id", d.get("user_id", "")), d)
        return jsonify(ok=True)

    @app.post("/api/settings")
    @require("settings")
    def settings_save():
        d = request.get_json()
        permitted = {
            "brand",
            "maintenance",
            "maintenance_staff",
            "manual_enabled",
            "stars_enabled",
            "topup_min",
            "topup_max",
            "stars_rate",
            "transfer_instructions",
            "order_min",
            "order_max",
            "session_minutes",
            "owner_telegram_id",
            "language",
            "notifications_enabled",
            "web_url",
            "support_enabled",
            "customer_cancel_pending",
        }
        if set(d) - permitted:
            raise ValueError("إعداد غير معروف")
        with db() as c:
            current = {k: setting(c, k) for k in permitted}
            merged = {**current, **d}
            if (
                d.get("language")
                and not c.execute(
                    "SELECT 1 FROM locales WHERE code=? AND enabled=1", (d["language"],)
                ).fetchone()
            ):
                raise ValueError("اللغة الافتراضية غير مفعلة")
            if d.get("web_url") and not d["web_url"].startswith("https://"):
                raise ValueError("عنوان اللوحة يجب أن يستخدم HTTPS")
            if merged["maintenance"] not in ("off", "all", "orders", "topups"):
                raise ValueError("وضع صيانة غير صالح")
            for k in (
                "topup_min",
                "topup_max",
                "order_min",
                "order_max",
                "owner_telegram_id",
            ):
                if not isinstance(merged[k], int) or merged[k] < 0:
                    raise ValueError("قيمة رقمية غير صالحة: " + k)
            if (
                not 1 <= merged["stars_rate"] <= 100000
                or not 1 <= merged["session_minutes"] <= 1440
                or not 1 <= merged["topup_min"] <= merged["topup_max"]
                or not 1 <= merged["order_min"] <= merged["order_max"]
            ):
                raise ValueError("تحقق من الحدود المالية وسعر Stars ومدة الجلسة")
            if request.actor["role"] != "owner" and "owner_telegram_id" in d:
                raise ValueError("هوية المالك للمالك فقط")
            for k, v in d.items():
                put(c, k, v)
            audit(c, request.actor["id"], "settings.save", "system", d)
        return jsonify(ok=True)

    @app.post("/api/connect")
    @require("settings")
    def connect():
        from .telegram import call

        value = request.get_json().get("token", "").strip()
        if not value or ":" not in value:
            raise ValueError("أدخل توكن Telegram صحيحًا")
        try:
            me = call(value, "getMe", {})
            call(value, "deleteWebhook", {"drop_pending_updates": False})
            call(
                value,
                "setMyCommands",
                {
                    "commands": [
                        {"command": "start", "description": "القائمة الرئيسية"},
                        {"command": "paysupport", "description": "دعم المدفوعات"},
                    ]
                },
            )
        except Exception:
            return (
                jsonify(
                    error="تعذر التحقق من Telegram. تحقق من التوكن واتصال الخادم دون مشاركة التوكن."
                ),
                502,
            )
        with db() as c:
            old = setting(c, "bot_identity", {})
            put(c, "telegram_token", cipher().encrypt(value.encode()).decode())
            put(c, "bot_identity", me)
            if old.get("id") != me["id"]:
                put(c, "poll_offset", 0)
            audit(
                c,
                request.actor["id"],
                "bot.connected",
                me["id"],
                {"username": me.get("username")},
            )
        return jsonify(ok=True, bot=me)

    return app
