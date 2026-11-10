import json, os, sqlite3, secrets
from contextvars import ContextVar

CURRENT_LANGUAGE = ContextVar("language", default=None)
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(os.environ.get("DATA_DIR", "data"))


def now():
    return datetime.now(timezone.utc).isoformat()


def cents(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or abs(n) > 100000000:
            raise ValueError("المبلغ خارج الحدود")
        return int((n * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError("المبلغ غير صالح")


def money(n):
    return f"{n/100:.2f}"


@contextmanager
def db():
    c = sqlite3.connect(ROOT / "system.sqlite3", timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(c, table, id):
    r = c.execute(f"SELECT * FROM {table} WHERE id=?", (id,)).fetchone()
    if not r:
        raise ValueError("السجل غير موجود")
    return dict(r)


def setting(c, key, default=None):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else default


def put(c, key, value):
    c.execute(
        "INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def audit(c, actor, action, entity, data):
    c.execute(
        "INSERT INTO audit(actor,action,entity,data,created) VALUES(?,?,?,?,?)",
        (str(actor), action, str(entity), json.dumps(data, ensure_ascii=False), now()),
    )


STATE_LABELS = {
    "pending": "قيد المراجعة",
    "review": "قيد المراجعة",
    "processing": "قيد التنفيذ",
    "completed": "مكتمل",
    "cancelled": "ملغي",
    "refunded": "مسترد",
    "approved": "مقبول",
    "rejected": "مرفوض",
    "awaiting_payment": "بانتظار الدفع",
    "awaiting_proof": "بانتظار الإثبات",
    "open": "مفتوحة",
    "closed": "مغلقة",
    "manual": "تحويل يدوي",
    "stars": "Telegram Stars",
}


def state_label(c, status):
    return render(c, "status_" + status, STATE_LABELS.get(status, status))


def locale_for(c, uid):
    row = c.execute("SELECT language FROM users WHERE id=?", (uid,)).fetchone()
    return row[0] if row and row[0] else setting(c, "language", "ar")


def translate(c, token, default, language=None):
    language = language or CURRENT_LANGUAGE.get() or setting(c, "language", "ar")
    row = c.execute(
        "SELECT text FROM translations WHERE locale=? AND token=?", (language, token)
    ).fetchone()
    return row[0] if row else default


def render(c, key, default, values=None, language=None):
    r = c.execute("SELECT text FROM menus WHERE key=?", (key,)).fetchone()
    if not r:
        c.execute(
            "INSERT INTO menus(key,name,text,kind) VALUES(?,?,?,?)",
            (key, key, default, "text"),
        )
        result = default
    else:
        result = r[0]
    result = translate(c, "menu:" + key, result, language)
    for k, v in (values or {}).items():
        result = result.replace("{" + k + "}", str(v))
    return result


def notify(c, uid, text, method="sendMessage", extra=None):
    if method == "sendMessage" and len(text) > 4000:
        # Telegram limits text messages to 4096 characters. Keep navigation on the last chunk.
        for start in range(0, len(text), 4000):
            notify(
                c,
                uid,
                text[start : start + 4000],
                method,
                extra if start + 4000 >= len(text) else None,
            )
        return
    payload = (
        {"chat_id": uid, "text": text} if method == "sendMessage" else {"chat_id": uid}
    )
    payload.update(extra or {})
    c.execute(
        "INSERT INTO notifications(payload,created) VALUES(?,?)",
        (json.dumps({"method": method, "data": payload}, ensure_ascii=False), now()),
    )


def staff_notify(c, permission, text):
    if not setting(c, "notifications_enabled", True):
        return
    owner = setting(c, "owner_telegram_id", 0)
    if owner:
        notify(c, owner, text)
    for a in rows(c, "SELECT * FROM staff WHERE enabled=1"):
        if (
            permission in json.loads(a["permissions"])
            and a["telegram_id"]
            and a["telegram_id"] != owner
        ):
            notify(c, a["telegram_id"], text)


def ledger(c, uid, delta, reason, actor, key, order_id=None, payment_id=None):
    old = c.execute("SELECT * FROM ledger WHERE operation_key=?", (key,)).fetchone()
    if old:
        if old["user_id"] != uid or old["delta"] != delta or old["reason"] != reason:
            raise ValueError("معرف العملية مستخدم لبيانات مختلفة")
        return old["id"]
    u = one(c, "users", uid)
    after = u["balance"] + delta
    if after < 0:
        raise ValueError("الرصيد غير كافٍ. اشحن رصيدك ثم عد إلى الطلب المحفوظ.")
    c.execute("UPDATE users SET balance=? WHERE id=?", (after, uid))
    cur = c.execute(
        "INSERT INTO ledger(user_id,delta,before_balance,after_balance,reason,actor,operation_key,order_id,payment_id,created,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            uid,
            delta,
            u["balance"],
            after,
            reason,
            str(actor),
            key,
            order_id,
            payment_id,
            now(),
            (
                "refund"
                if key.startswith("refund:")
                else (
                    "order"
                    if order_id
                    else (
                        "payment"
                        if payment_id
                        else "topup" if key.startswith("topup:") else "adjustment"
                    )
                )
            ),
        ),
    )
    notify(
        c,
        uid,
        render(
            c,
            "notification_balance",
            "💳 {reason}\nالمبلغ: ${delta}\nالرصيد الجديد: ${balance}\nLED-{id}",
            {
                "reason": reason,
                "delta": money(delta),
                "balance": money(after),
                "id": f"{cur.lastrowid:05d}",
            },
            language=locale_for(c, uid),
        ),
    )
    return cur.lastrowid


PERMISSIONS = [
    "stats",
    "expenses",
    "orders",
    "topups",
    "topups_approve",
    "users",
    "users_manage",
    "balances",
    "services",
    "inventory",
    "support",
    "broadcasts",
    "settings",
    "menus",
    "staff",
    "ledger",
    "audit",
]


def init():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with db() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS workflows(id INTEGER PRIMARY KEY,name TEXT NOT NULL,steps TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,revision INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS flow_runs(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),workflow_id INTEGER NOT NULL REFERENCES workflows(id),revision INTEGER NOT NULL DEFAULT 1,step INTEGER NOT NULL DEFAULT 0,variables TEXT NOT NULL,status TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS topup_drafts(user_id INTEGER PRIMARY KEY REFERENCES users(id),state TEXT NOT NULL,data TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS button_context(code TEXT PRIMARY KEY,user_id INTEGER NOT NULL,button_id INTEGER NOT NULL,data TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS reply_context(user_id INTEGER PRIMARY KEY,buttons TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS locales(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS translations(id INTEGER PRIMARY KEY,locale TEXT NOT NULL REFERENCES locales(code),token TEXT NOT NULL,text TEXT NOT NULL,UNIQUE(locale,token));
CREATE TABLE IF NOT EXISTS assets(id INTEGER PRIMARY KEY,name TEXT NOT NULL,stored_name TEXT UNIQUE NOT NULL,mime TEXT NOT NULL,kind TEXT NOT NULL,size INTEGER NOT NULL,purpose TEXT NOT NULL,actor TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN ('expense','fee')),amount INTEGER NOT NULL CHECK(amount!=0),reason TEXT NOT NULL,occurred_on TEXT NOT NULL,actor TEXT NOT NULL,operation_key TEXT UNIQUE NOT NULL,reversed_from INTEGER UNIQUE REFERENCES expenses(id),created TEXT NOT NULL);
CREATE TRIGGER IF NOT EXISTS expenses_no_update BEFORE UPDATE ON expenses BEGIN SELECT RAISE(ABORT,'immutable expense'); END;
CREATE TRIGGER IF NOT EXISTS expenses_no_delete BEFORE DELETE ON expenses BEGIN SELECT RAISE(ABORT,'immutable expense'); END;
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS staff(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'admin',telegram_id INTEGER UNIQUE,permissions TEXT NOT NULL DEFAULT '[]',enabled INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL,last_active TEXT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT,first_name TEXT,balance INTEGER NOT NULL DEFAULT 0 CHECK(balance>=0),status TEXT NOT NULL DEFAULT 'active',note TEXT NOT NULL DEFAULT '',created TEXT NOT NULL,last_active TEXT);
CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY,name TEXT NOT NULL,price INTEGER NOT NULL CHECK(price>=0),cost INTEGER NOT NULL DEFAULT 0,min_qty INTEGER NOT NULL DEFAULT 100,max_qty INTEGER NOT NULL DEFAULT 100000,description TEXT NOT NULL DEFAULT '',image TEXT NOT NULL DEFAULT '',target_type TEXT NOT NULL DEFAULT 'any',enabled INTEGER NOT NULL DEFAULT 1,deleted INTEGER NOT NULL DEFAULT 0,position INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),service_id INTEGER NOT NULL REFERENCES services(id),service_name TEXT NOT NULL,target TEXT NOT NULL,quantity INTEGER NOT NULL,price INTEGER NOT NULL,cost INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'pending',note TEXT NOT NULL DEFAULT '',request_key TEXT UNIQUE NOT NULL,refunded INTEGER NOT NULL DEFAULT 0,debit_id INTEGER,refund_id INTEGER,created TEXT NOT NULL,updated TEXT NOT NULL,completed TEXT);
CREATE TABLE IF NOT EXISTS topups(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),amount INTEGER NOT NULL CHECK(amount>0),method TEXT NOT NULL,status TEXT NOT NULL,proof TEXT NOT NULL DEFAULT '',note TEXT NOT NULL DEFAULT '',reason TEXT NOT NULL DEFAULT '',payload TEXT UNIQUE,stars INTEGER,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,charge_id TEXT UNIQUE NOT NULL,topup_id INTEGER UNIQUE NOT NULL REFERENCES topups(id),user_id INTEGER NOT NULL REFERENCES users(id),amount INTEGER NOT NULL,currency TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),delta INTEGER NOT NULL,before_balance INTEGER NOT NULL,after_balance INTEGER NOT NULL,reason TEXT NOT NULL,actor TEXT NOT NULL,operation_key TEXT UNIQUE NOT NULL,order_id INTEGER,payment_id INTEGER,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY,username TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'available',deleted INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL,updated TEXT NOT NULL,added_by TEXT NOT NULL,updated_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),subject TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',order_id INTEGER REFERENCES orders(id),created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,ticket_id INTEGER NOT NULL REFERENCES tickets(id),actor TEXT NOT NULL,body TEXT NOT NULL,attachment TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS menus(id INTEGER PRIMARY KEY,name TEXT NOT NULL,key TEXT UNIQUE NOT NULL,text TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'inline');
CREATE TABLE IF NOT EXISTS buttons(id INTEGER PRIMARY KEY,menu_id INTEGER NOT NULL REFERENCES menus(id),label TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'callback',action TEXT NOT NULL,target TEXT NOT NULL DEFAULT '',row_num INTEGER NOT NULL DEFAULT 0,col_num INTEGER NOT NULL DEFAULT 0,enabled INTEGER NOT NULL DEFAULT 1,permission TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS sessions(user_id INTEGER PRIMARY KEY,state TEXT NOT NULL,data TEXT NOT NULL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(user_id INTEGER PRIMARY KEY,data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,entity TEXT NOT NULL,data TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS broadcasts(id INTEGER PRIMARY KEY,body TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'text',media TEXT NOT NULL DEFAULT '',audience TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries(id INTEGER PRIMARY KEY,broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id),user_id INTEGER NOT NULL REFERENCES users(id),status TEXT NOT NULL DEFAULT 'pending',error TEXT NOT NULL DEFAULT '',UNIQUE(broadcast_id,user_id));
CREATE TABLE IF NOT EXISTS updates(id INTEGER PRIMARY KEY,created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS expenses_date ON expenses(occurred_on,kind);
CREATE INDEX IF NOT EXISTS orders_user ON orders(user_id,id);
CREATE INDEX IF NOT EXISTS notifications_status ON notifications(status,id);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT,'immutable audit'); END;
""")
        if "checkout_started" not in [
            r[1] for r in c.execute("PRAGMA table_info(topups)")
        ]:
            c.execute(
                "ALTER TABLE topups ADD COLUMN checkout_started INTEGER NOT NULL DEFAULT 0"
            )
        for table, column, definition in [
            ("menus", "layout_key", "TEXT NOT NULL DEFAULT ''"),
            ("buttons", "child_menu", "TEXT NOT NULL DEFAULT ''"),
            ("users", "language", "TEXT NOT NULL DEFAULT ''"),
            ("staff", "auth_version", "INTEGER NOT NULL DEFAULT 0"),
            ("staff", "added_by", "TEXT NOT NULL DEFAULT ''"),
            ("ledger", "kind", "TEXT NOT NULL DEFAULT 'adjustment'"),
            ("ledger", "status", "TEXT NOT NULL DEFAULT 'posted'"),
        ]:
            if column not in [r[1] for r in c.execute(f"PRAGMA table_info({table})")]:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        c.execute("INSERT OR IGNORE INTO locales(code,name) VALUES('ar','العربية')")
        defaults = {
            "web_url": "",
            "support_enabled": True,
            "customer_cancel_pending": True,
            "brand": "TikTok Services",
            "maintenance": "off",
            "maintenance_staff": True,
            "manual_enabled": True,
            "stars_enabled": True,
            "topup_min": 100,
            "topup_max": 100000,
            "stars_rate": 100,
            "transfer_instructions": "يرجى التواصل مع الدعم للحصول على بيانات التحويل قبل الدفع.",
            "order_min": 1,
            "order_max": 10000000,
            "expenses": 0,
            "fees": 0,
            "session_minutes": 30,
            "owner_telegram_id": 0,
            "language": "ar",
            "notifications_enabled": True,
        }
        for k, v in defaults.items():
            if c.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone() is None:
                put(c, k, v)
        if not c.execute("SELECT 1 FROM services").fetchone():
            for i, (name, price) in enumerate(
                [
                    ("👥 متابعو تيك توك", 100),
                    ("👁 مشاهدات تيك توك", 50),
                    ("❤️ إعجابات تيك توك", 75),
                ]
            ):
                c.execute(
                    "INSERT INTO services(name,price,position) VALUES(?,?,?)",
                    (name, price, i),
                )
        if not c.execute("SELECT 1 FROM menus").fetchone():
            menus = [
                (
                    "home",
                    "القائمة الرئيسية",
                    "🎵 أهلاً بك في TikTok Services Bot\n\nمرحباً بك في عالم خدمات تيك توك.\n🛒 طلب الخدمات\n💳 شحن رصيدك\n📋 متابعة طلباتك\n👤 إدارة حسابك\n🎧 التواصل مع الدعم الفني\n\nاختر ما تريد من القائمة أدناه.",
                ),
                (
                    "services",
                    "الخدمات",
                    "🛒 قائمة الخدمات\nاختر الخدمة التي تريد طلبها. الأسعار محسوبة حسب الكمية.",
                ),
                ("topup", "شحن الرصيد", "💳 اختر طريقة الشحن المناسبة لك."),
                ("account", "الحساب", "👤 حسابك الشخصي"),
                ("myorders", "الطلبات", "📋 طلباتك"),
                ("support", "الدعم", "🎧 كيف يمكننا مساعدتك؟"),
                (
                    "maintenance",
                    "الصيانة",
                    "🛠 البوت تحت الصيانة حاليًا. يرجى المحاولة لاحقًا.",
                ),
                (
                    "error",
                    "خطأ",
                    "❌ البيانات المدخلة غير صحيحة. يرجى المحاولة مرة أخرى.",
                ),
                (
                    "expired",
                    "انتهاء الجلسة",
                    "⌛ انتهت جلسة الاستخدام. يرجى بدء العملية من جديد.",
                ),
            ]
            for key, name, text in menus:
                c.execute(
                    "INSERT INTO menus(key,name,text) VALUES(?,?,?)", (key, name, text)
                )
            home = c.execute("SELECT id FROM menus WHERE key='home'").fetchone()[0]
            for i, (label, action) in enumerate(
                [
                    ("🛒 الخدمات", "services"),
                    ("💳 شحن الرصيد", "topup"),
                    ("📋 طلباتي", "myorders"),
                    ("👤 حسابي", "account"),
                    ("🎧 الدعم الفني", "support"),
                ]
            ):
                c.execute(
                    "INSERT INTO buttons(menu_id,label,action,row_num,col_num) VALUES(?,?,?,?,?)",
                    (home, label, action, i // 2, i % 2),
                )

        if not setting(c, "dated_expenses_migrated", False):
            for key, kind in (("expenses", "expense"), ("fees", "fee")):
                value = setting(c, key, 0)
                if value:
                    eid = c.execute(
                        "INSERT INTO expenses(kind,amount,reason,occurred_on,actor,operation_key,created) VALUES(?,?,?,?,?,?,?)",
                        (
                            kind,
                            value,
                            "ترحيل الرصيد المجمع السابق؛ راجع تاريخ الاستحقاق",
                            now()[:10],
                            "migration",
                            "legacy-" + key,
                            now(),
                        ),
                    ).lastrowid
                    audit(
                        c,
                        "migration",
                        "expense.imported",
                        eid,
                        {"amount": value, "occurred_on": now()[:10]},
                    )
                put(c, key, 0)
            put(c, "dated_expenses_migrated", True)

        # Install the full editable message catalog before connecting Telegram.
        catalog = json.loads((Path(__file__).parent / "catalog.json").read_text())
        for status, label in STATE_LABELS.items():
            catalog["messages"]["status_" + status] = label
        for key, default in catalog["messages"].items():
            c.execute(
                "INSERT OR IGNORE INTO menus(key,name,text,kind) VALUES(?,?,?,'text')",
                (key, default[:45].replace("\n", " "), default),
            )
        for key, buttons in catalog["layouts"].items():
            if c.execute("SELECT 1 FROM menus WHERE key=?", (key,)).fetchone():
                continue
            mid = c.execute(
                "INSERT INTO menus(key,name,text,kind) VALUES(?,?,?,'inline')",
                (key, key, ""),
            ).lastrowid
            for ri, row in enumerate(buttons):
                for ci, btn in enumerate(row):
                    c.execute(
                        "INSERT INTO buttons(menu_id,label,action,target,row_num,col_num) VALUES(?,?,?,?,?,?)",
                        (mid, btn["text"], "callback", btn["callback_data"], ri, ci),
                    )
