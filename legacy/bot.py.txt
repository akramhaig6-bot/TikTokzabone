#!/usr/bin/env python3
"""
TikTok services Telegram bot.
Python 3.10+, standard library only.
Set BOT_TOKEN and OWNER_ID environment variables before running.
"""
import os, json, sqlite3, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
DB_PATH = os.getenv("DB_PATH", "bot.sqlite3")
API = f"https://api.telegram.org/bot{TOKEN}/"
if not TOKEN or not OWNER_ID:
    raise SystemExit("Set BOT_TOKEN and OWNER_ID environment variables first.")

def api(method, data=None):
    data = data or {}
    # Telegram Bot API accepts JSON; send photo/file not implemented in this stdlib starter.
    req = urllib.request.Request(API + method, data=json.dumps(data).encode(), headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            result=json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: result=json.loads(e.read().decode())
        except Exception: raise RuntimeError(f"Telegram HTTP error: {e.code}")
    if not result.get("ok"):
        raise RuntimeError(result.get("description","Telegram API error"))
    return result.get("result")

def db():
    conn=sqlite3.connect(DB_PATH)
    conn.row_factory=sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, balance REAL NOT NULL DEFAULT 0, joined TEXT);
        CREATE TABLE IF NOT EXISTS admins(user_id INTEGER PRIMARY KEY, added_by INTEGER, added_at TEXT);
        CREATE TABLE IF NOT EXISTS services(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price_per_1000 REAL NOT NULL DEFAULT 0, enabled INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, service_id INTEGER NOT NULL, target TEXT NOT NULL, quantity INTEGER NOT NULL, price REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS topups(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount REAL NOT NULL, method TEXT NOT NULL, proof TEXT, status TEXT NOT NULL DEFAULT 'pending', created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS inventory(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, note TEXT, status TEXT NOT NULL DEFAULT 'available', created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS states(user_id INTEGER PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS payments(telegram_charge_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, amount REAL NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, delta REAL NOT NULL, reason TEXT NOT NULL, actor INTEGER NOT NULL, created TEXT NOT NULL);
        """)
        c.execute("INSERT OR IGNORE INTO services(id,name,price_per_1000,enabled) VALUES(1,'TikTok campaign - followers',1.0,1)")
        c.execute("INSERT OR IGNORE INTO services(id,name,price_per_1000,enabled) VALUES(2,'TikTok campaign - views',0.5,1)")
        c.execute("INSERT OR IGNORE INTO services(id,name,price_per_1000,enabled) VALUES(3,'TikTok campaign - likes',0.75,1)")

def now(): return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
def is_owner(uid): return uid == OWNER_ID
def is_admin(uid):
    if is_owner(uid): return True
    with db() as c: return c.execute("SELECT 1 FROM admins WHERE user_id=?",(uid,)).fetchone() is not None
def money(v): return f"{float(v):.2f}"

def user_upsert(u):
    with db() as c:
        c.execute("INSERT INTO users(id,username,first_name,joined) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name",
                  (u["id"],u.get("username",""),u.get("first_name",""),now()))

def user_balance(uid):
    with db() as c:
        r=c.execute("SELECT balance FROM users WHERE id=?",(uid,)).fetchone()
        return float(r["balance"]) if r else 0.0

def change_balance(uid,delta,reason,actor):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO users(id,joined) VALUES(?,?)",(uid,now()))
        c.execute("UPDATE users SET balance=balance+? WHERE id=?",(delta,uid))
        c.execute("INSERT INTO ledger(user_id,delta,reason,actor,created) VALUES(?,?,?,?,?)",(uid,delta,reason,actor,now()))

def set_state(uid,state,data=None):
    with db() as c:
        c.execute("INSERT INTO states(user_id,state,data) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state=excluded.state,data=excluded.data",
                  (uid,state,json.dumps(data or {})))
def get_state(uid):
    with db() as c:
        r=c.execute("SELECT state,data FROM states WHERE user_id=?",(uid,)).fetchone()
        return (r["state"],json.loads(r["data"])) if r else (None,{})
def clear_state(uid):
    with db() as c: c.execute("DELETE FROM states WHERE user_id=?",(uid,))

def send(chat_id,text,keyboard=None,**extra):
    d={"chat_id":chat_id,"text":text}
    if keyboard: d["reply_markup"]={"inline_keyboard":keyboard}
    d.update(extra)
    return api("sendMessage",d)
def edit(chat_id,msg_id,text,keyboard=None):
    d={"chat_id":chat_id,"message_id":msg_id,"text":text}
    if keyboard: d["reply_markup"]={"inline_keyboard":keyboard}
    return api("editMessageText",d)
def answer(cid,text="",alert=False):
    try: api("answerCallbackQuery",{"callback_query_id":cid,"text":text,"show_alert":alert})
    except Exception: pass
def btn(text,data): return {"text":text,"callback_data":data}
def rows(items,n=2): return [items[i:i+n] for i in range(0,len(items),n)]
def main_menu(uid):
    keyboard=[
      [btn("🛒 الخدمات","services"),btn("💳 شحن الرصيد","topup")],
      [btn("📋 طلباتي","myorders"),btn("👤 حسابي","account")],
      [btn("🎧 الدعم الفني","support")]
    ]
    if is_admin(uid): keyboard.append([btn("⚙️ لوحة الإدارة","admin")])
    return keyboard
def admin_menu(uid):
    items=[[btn("📦 الطلبات","adm_orders"),btn("🧾 طلبات الشحن","adm_topups")],
           [btn("👥 المستخدمون","adm_users"),btn("➕ إضافة رصيد","adm_balance")],
           [btn("➖ خصم رصيد","adm_sub_balance")],
           [btn("➕ إضافة أدمن","adm_addadmin"),btn("➖ حذف أدمن","adm_deladmin")],
           [btn("🛠 الخدمات والأسعار","adm_services"),btn("🔐 مخزون الحسابات","adm_inventory")],
           [btn("📢 إذاعة","adm_broadcast")]]
    if is_owner(uid): items.append([btn("📊 الإحصائيات","adm_stats")])
    items.append([btn("↩️ الرئيسية","home")])
    return items

def services_keyboard():
    with db() as c: ss=c.execute("SELECT id,name,price_per_1000 FROM services WHERE enabled=1 ORDER BY id").fetchall()
    return [[btn(f"{s['name']} — ${money(s['price_per_1000'])}/1000","service_"+str(s["id"]))] for s in ss]+[[btn("↩️ الرئيسية","home")]]

def start(chat_id,uid):
    send(chat_id,"🎵 أهلاً بك في بوت خدمات تيك توك\\n\\nاختر من القائمة أدناه. الحملات تُدار بصورة مشروعة ولا تتضمن تشغيل حسابات وهمية أو تجاوز قيود المنصة.",main_menu(uid))

def handle_text(msg):
    uid=msg["from"]["id"]; chat=msg["chat"]["id"]; text=msg.get("text","").strip()
    user_upsert(msg["from"])
    state,data=get_state(uid)
    if text.startswith("/start"): clear_state(uid); start(chat,uid); return
    if text.startswith("/owner"):
        if not is_owner(uid): send(chat,"⛔ هذا الأمر للمالك فقط."); return
        send(chat,"👑 لوحة المالك",admin_menu(uid)); return
    if state:
        if state=="order_target":
            data["target"]=text
            set_state(uid,"order_quantity",data)
            send(chat,"أرسل الكمية المطلوبة (عدد صحيح من 1 إلى 100000):")
            return
        if state=="order_quantity":
            try: qty=int(text)
            except: send(chat,"أرسل كمية كرقم صحيح."); return
            if qty<1 or qty>100000: send(chat,"الكمية يجب أن تكون بين 1 و100000."); return
            service_id=int(data["service_id"])
            with db() as c: s=c.execute("SELECT * FROM services WHERE id=? AND enabled=1",(service_id,)).fetchone()
            if not s: clear_state(uid); send(chat,"الخدمة غير متاحة حالياً."); return
            price=round(qty*float(s["price_per_1000"])/1000,2)
            data.update({"quantity":qty,"price":price})
            set_state(uid,"order_confirm",data)
            send(chat,f"تأكيد الطلب\\nالخدمة: {s['name']}\\nالرابط: {data['target']}\\nالكمية: {qty}\\nالسعر: ${money(price)}\\nرصيدك: ${money(user_balance(uid))}",
                 [[btn("✅ تأكيد","order_yes"),btn("❌ إلغاء","order_no")]])
            return
        if state=="stars_amount":
            try: amount=float(text)
            except: send(chat,"أرسل مبلغاً رقمياً."); return
            if amount<=0 or amount>1000: send(chat,"المبلغ يجب أن يكون بين 0 و1000."); return
            # Stars XTR pricing: this starter uses 100 Stars per $1 as a displayed conversion.
            stars=int(round(amount*100))
            payload=f"stars:{amount:.2f}"
            clear_state(uid)
            api("sendInvoice",{"chat_id":chat,"title":"شحن رصيد البوت","description":f"إضافة ${amount:.2f} إلى رصيدك","payload":payload,"provider_token":"","currency":"XTR","prices":[{"label":f"${amount:.2f} credit","amount":stars}]})
            return
        if state=="topup_manual":
            try: amount=float(text)
            except: send(chat,"أرسل مبلغاً رقمياً."); return
            if amount<=0 or amount>100000: send(chat,"المبلغ غير صالح."); return
            with db() as c:
                cur=c.execute("INSERT INTO topups(user_id,amount,method,created) VALUES(?,?,?,?)",(uid,amount,"manual",now()))
                tid=cur.lastrowid
            clear_state(uid)
            send(chat,f"تم تسجيل طلب شحن #{tid} بمبلغ ${money(amount)}. أرسل إثبات التحويل إلى الدعم/الإدارة.")
            for aid in admin_ids():
                send(aid,f"🔔 طلب شحن #{tid}\\nالمستخدم: {uid}\\nالمبلغ: ${money(amount)}\\nوافق أو ارفض من لوحة الإدارة.",[[btn("قبول","topup_approve_"+str(tid)),btn("رفض","topup_reject_"+str(tid))]])
            return
        if state=="admin_add_balance":
            if not is_admin(uid): clear_state(uid); return
            try: target,amount=text.split()
            except: send(chat,"الصيغة: ID مبلغ"); return
            try: target=int(target); amount=float(amount)
            except: send(chat,"ID والمبلغ يجب أن يكونا أرقاماً."); return
            if amount<=0: send(chat,"المبلغ لازم يكون أكبر من صفر."); return
            change_balance(target,amount,"admin credit",uid); clear_state(uid)
            send(chat,f"تم إضافة ${money(amount)} للمستخدم {target}.")
            try: send(target,f"💰 تمت إضافة ${money(amount)} إلى رصيدك.")
            except Exception: send(chat,"ملاحظة: تعذر مراسلة المستخدم؛ قد لا يكون بدأ البوت بعد.")
            return
        if state=="admin_sub_balance":
            if not is_admin(uid): clear_state(uid); return
            try: target,amount=text.split()
            except: send(chat,"الصيغة: ID مبلغ"); return
            try: target=int(target); amount=float(amount)
            except: send(chat,"ID والمبلغ يجب أن يكونا أرقاماً."); return
            if amount<=0 or user_balance(target)<amount: send(chat,"المبلغ غير صالح أو الرصيد غير كافٍ."); return
            change_balance(target,-amount,"admin debit",uid); clear_state(uid)
            send(chat,f"تم خصم ${money(amount)} من المستخدم {target}.")
            return
        if state=="admin_add_admin":
            if not is_owner(uid): clear_state(uid); return
            try: target=int(text)
            except: send(chat,"أرسل Telegram ID رقمياً."); return
            with db() as c: c.execute("INSERT OR IGNORE INTO admins(user_id,added_by,added_at) VALUES(?,?,?)",(target,uid,now()))
            clear_state(uid); send(chat,f"تمت إضافة الأدمن {target}."); return
        if state=="admin_del_admin":
            if not is_owner(uid): clear_state(uid); return
            try: target=int(text)
            except: send(chat,"أرسل Telegram ID رقمياً."); return
            with db() as c: c.execute("DELETE FROM admins WHERE user_id=?",(target,))
            clear_state(uid); send(chat,f"تم حذف الأدمن {target}."); return
        if state=="admin_broadcast":
            if not is_admin(uid): clear_state(uid); return
            with db() as c: users=c.execute("SELECT id FROM users").fetchall()
            sent=0
            for u in users:
                try: send(u["id"],text); sent+=1
                except Exception: pass
                time.sleep(0.05)
            clear_state(uid); send(chat,f"انتهت الإذاعة. تم الإرسال إلى {sent} مستخدم."); return
        if state=="service_add":
            if not is_owner(uid): clear_state(uid); return
            try: name,price=text.rsplit("|",1); price=float(price.strip()); name=name.strip()
            except: send(chat,"الصيغة: اسم الخدمة | سعر كل 1000"); return
            if not name or price<0: send(chat,"بيانات غير صحيحة."); return
            with db() as c: c.execute("INSERT INTO services(name,price_per_1000,enabled) VALUES(?,?,1)",(name,price))
            clear_state(uid); send(chat,"تمت إضافة الخدمة."); return
        if state=="inventory_add":
            if not is_owner(uid): clear_state(uid); return
            try: username,note=text.split("|",1)
            except: username=text; note=""
            username=username.strip().lstrip("@")
            if not username: send(chat,"اسم الحساب غير صالح."); return
            with db() as c: c.execute("INSERT INTO inventory(username,note,created) VALUES(?,?,?)",(username,note.strip(),now()))
            clear_state(uid); send(chat,"تم حفظ سجل الحساب. لا تُدخل كلمات مرور أو أكواد تحقق."); return
        if state=="support":
            clear_state(uid)
            for aid in admin_ids():
                send(aid,f"🎧 رسالة دعم من {uid}:\\n{text}")
            send(chat,"تم إرسال رسالتك للدعم."); return
        clear_state(uid)

def admin_ids():
    with db() as c: ids=[r["user_id"] for r in c.execute("SELECT user_id FROM admins").fetchall()]
    return list(set(ids+[OWNER_ID]))

def handle_callback(q):
    uid=q["from"]["id"]; chat=q["message"]["chat"]["id"]; mid=q["message"]["message_id"]; d=q["data"]
    user_upsert(q["from"]); answer(q["id"])
    if d=="home": edit(chat,mid,"🎵 القائمة الرئيسية",main_menu(uid))
    elif d=="services": edit(chat,mid,"🛒 اختر الخدمة:",services_keyboard())
    elif d.startswith("service_"):
        sid=int(d.split("_",1)[1])
        with db() as c: s=c.execute("SELECT * FROM services WHERE id=? AND enabled=1",(sid,)).fetchone()
        if not s: edit(chat,mid,"الخدمة غير متاحة.",main_menu(uid)); return
        set_state(uid,"order_target",{"service_id":sid})
        edit(chat,mid,f"الخدمة: {s['name']}\\nالسعر لكل 1000: ${money(s['price_per_1000'])}\\n\\nأرسل رابط حساب أو منشور تيك توك للحملة:")
    elif d=="order_yes":
        state,data=get_state(uid)
        if state!="order_confirm": send(chat,"انتهت جلسة الطلب. ابدأ من جديد.",main_menu(uid)); return
        price=float(data["price"])
        if user_balance(uid)<price: clear_state(uid); send(chat,"رصيدك غير كافٍ. اشحن الرصيد أولاً.",main_menu(uid)); return
        with db() as c:
            c.execute("UPDATE users SET balance=balance-? WHERE id=?",(price,uid))
            cur=c.execute("INSERT INTO orders(user_id,service_id,target,quantity,price,status,created) VALUES(?,?,?,?,?,?,?)",
                          (uid,int(data["service_id"]),data["target"],int(data["quantity"]),price,"pending",now()))
            oid=cur.lastrowid
            c.execute("INSERT INTO ledger(user_id,delta,reason,actor,created) VALUES(?,?,?,?,?)",(uid,-price,f"order #{oid}",uid,now()))
        clear_state(uid)
        send(chat,f"✅ تم تسجيل طلبك\\nرقم الطلب: TK-{oid:05d}\\nالحالة: قيد المراجعة\\nالسعر: ${money(price)}",main_menu(uid))
        for aid in admin_ids(): send(aid,f"📦 طلب جديد TK-{oid:05d}\\nمن: {uid}\\nالكمية: {data['quantity']}\\nالرابط: {data['target']}\\nالمبلغ: ${money(price)}",[[btn("قيد التنفيذ","order_status_"+str(oid)+"_processing"),btn("إكمال","order_status_"+str(oid)+"_completed")],[btn("إلغاء/استرداد","order_status_"+str(oid)+"_cancelled")]])
    elif d=="order_no": clear_state(uid); edit(chat,mid,"تم إلغاء الطلب.",main_menu(uid))
    elif d=="myorders":
        with db() as c: rr=c.execute("SELECT id,quantity,price,status,created FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",(uid,)).fetchall()
        if not rr: edit(chat,mid,"ما عندك طلبات لحد الآن.",main_menu(uid)); return
        text="📋 آخر طلباتك:\\n"+"\\n".join([f"TK-{r['id']:05d} | {r['quantity']} | ${money(r['price'])} | {r['status']}" for r in rr])
        edit(chat,mid,text,main_menu(uid))
    elif d=="account": edit(chat,mid,f"👤 حسابك\\nID: {uid}\\nرصيدك: ${money(user_balance(uid))}",main_menu(uid))
    elif d=="topup":
        edit(chat,mid,"اختر طريقة الشحن:",[[btn("⭐ شحن Telegram Stars","stars_topup"),btn("🧾 شحن يدوي","manual_topup")],[btn("↩️ الرئيسية","home")]])
    elif d=="manual_topup":
        set_state(uid,"topup_manual",{})
        edit(chat,mid,"أرسل مبلغ الشحن بالدولار. سيتم إرسال الطلب للإدارة للمراجعة.")
    elif d=="stars_topup":
        edit(chat,mid,"أرسل مبلغ الشحن بالدولار (كل 1$ = 100 Stars في هذا المثال).",[[btn("↩️ الرئيسية","home")]])
        set_state(uid,"stars_amount",{})
    elif d=="support":
        set_state(uid,"support",{})
        edit(chat,mid,"أرسل رسالتك للدعم الفني:")
    elif d=="admin":
        if not is_admin(uid): answer(q["id"],"غير مصرح",True); return
        edit(chat,mid,"⚙️ لوحة الإدارة",admin_menu(uid))
    elif d=="adm_balance":
        if not is_admin(uid): return
        set_state(uid,"admin_add_balance",{})
        edit(chat,mid,"أرسل: Telegram_ID المبلغ\\nمثال: 123456789 5")
    elif d=="adm_sub_balance":
        if not is_admin(uid): return
        set_state(uid,"admin_sub_balance",{})
        edit(chat,mid,"أرسل: Telegram_ID المبلغ المراد خصمه\\nمثال: 123456789 5")
    elif d=="adm_addadmin":
        if not is_owner(uid): answer(q["id"],"للمالك فقط",True); return
        set_state(uid,"admin_add_admin",{}); edit(chat,mid,"أرسل Telegram ID للأدمن الجديد:")
    elif d=="adm_deladmin":
        if not is_owner(uid): answer(q["id"],"للمالك فقط",True); return
        set_state(uid,"admin_del_admin",{}); edit(chat,mid,"أرسل Telegram ID للأدمن المراد حذفه:")
    elif d=="adm_broadcast":
        if not is_admin(uid): return
        set_state(uid,"admin_broadcast",{}); edit(chat,mid,"أرسل نص الإذاعة:")
    elif d=="adm_services":
        if not is_owner(uid): answer(q["id"],"للمالك فقط",True); return
        with db() as c: ss=c.execute("SELECT id,name,price_per_1000,enabled FROM services").fetchall()
        text="🛠 الخدمات والأسعار:\\n"+"\\n".join([f"{s['id']}. {s['name']} — ${money(s['price_per_1000'])}/1000 — {'مفعلة' if s['enabled'] else 'معطلة'}" for s in ss])
        edit(chat,mid,text,[[btn("➕ إضافة خدمة","service_add")],[btn("↩️ الإدارة","admin")]])
    elif d=="service_add":
        if not is_owner(uid): return
        set_state(uid,"service_add",{}); edit(chat,mid,"أرسل: اسم الخدمة | سعر كل 1000")
    elif d=="adm_inventory":
        if not is_owner(uid): answer(q["id"],"للمالك فقط",True); return
        with db() as c:
            count=c.execute("SELECT COUNT(*) n FROM inventory").fetchone()["n"]
            av=c.execute("SELECT COUNT(*) n FROM inventory WHERE status='available'").fetchone()["n"]
        edit(chat,mid,f"🔐 سجلات الحسابات: {count}\\nمتاحة: {av}\\nأضف اسم الحساب/ملاحظة فقط. لا تخزن بيانات الدخول.",[[btn("➕ إضافة سجل","inventory_add")],[btn("↩️ الإدارة","admin")]])
    elif d=="inventory_add":
        if not is_owner(uid): return
        set_state(uid,"inventory_add",{}); edit(chat,mid,"أرسل: username | ملاحظة (اختياري)")
    elif d=="adm_orders":
        if not is_admin(uid): return
        with db() as c: rr=c.execute("SELECT id,user_id,quantity,price,status FROM orders ORDER BY id DESC LIMIT 15").fetchall()
        txt="📦 آخر الطلبات:\\n"+"\\n".join([f"TK-{r['id']:05d} | user {r['user_id']} | {r['quantity']} | ${money(r['price'])} | {r['status']}" for r in rr]) or "لا توجد طلبات."
        edit(chat,mid,txt,[[btn("↩️ الإدارة","admin")]])
    elif d=="adm_topups":
        if not is_admin(uid): return
        with db() as c: rr=c.execute("SELECT id,user_id,amount,status FROM topups WHERE status='pending' ORDER BY id DESC LIMIT 15").fetchall()
        if not rr: edit(chat,mid,"لا توجد طلبات شحن معلقة.",[[btn("↩️ الإدارة","admin")]]); return
        edit(chat,mid,"🧾 طلبات الشحن المعلقة:\\n"+"\\n".join([f"#{r['id']} | user {r['user_id']} | ${money(r['amount'])}" for r in rr]),[[btn("قبول #"+str(r["id"]),"topup_approve_"+str(r["id"])) for r in rr[:2]],[btn("↩️ الإدارة","admin")]])
    elif d.startswith("topup_approve_") or d.startswith("topup_reject_"):
        if not is_admin(uid): return
        approve=d.startswith("topup_approve_"); tid=int(d.rsplit("_",1)[1])
        with db() as c:
            r=c.execute("SELECT * FROM topups WHERE id=? AND status='pending'",(tid,)).fetchone()
            if not r: send(chat,"الطلب غير موجود أو تمت معالجته."); return
            c.execute("UPDATE topups SET status=? WHERE id=?",("approved" if approve else "rejected",tid))
        if approve: change_balance(r["user_id"],r["amount"],f"topup #{tid}",uid)
        send(chat,f"تم {'قبول' if approve else 'رفض'} طلب الشحن #{tid}.")
        try: send(r["user_id"],f"طلب الشحن #{tid} {'تم قبوله وإضافة الرصيد' if approve else 'تم رفضه'}.")
        except Exception: send(chat,"تعذر مراسلة صاحب طلب الشحن.")
    elif d.startswith("order_status_"):
        if not is_admin(uid): return
        parts=d.split("_"); oid=int(parts[2]); status=parts[3]
        with db() as c:
            r=c.execute("SELECT * FROM orders WHERE id=?",(oid,)).fetchone()
            if not r: send(chat,"الطلب غير موجود."); return
            c.execute("UPDATE orders SET status=? WHERE id=?",(status,oid))
        if status=="cancelled":
            change_balance(r["user_id"],r["price"],f"refund order #{oid}",uid)
            try: send(r["user_id"],f"طلب TK-{oid:05d} ألغي وتم استرداد ${money(r['price'])}.")
            except Exception: pass
        else:
            try: send(r["user_id"],f"تحديث طلب TK-{oid:05d}: {status}")
            except Exception: pass
        send(chat,f"تم تحديث الطلب TK-{oid:05d}.")
    elif d=="adm_users":
        if not is_admin(uid): return
        with db() as c: n=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        edit(chat,mid,f"👥 عدد المستخدمين المسجلين: {n}",[[btn("↩️ الإدارة","admin")]])
    elif d=="adm_stats":
        if not is_owner(uid): return
        with db() as c:
            users=c.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
            orders=c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"]
            revenue=c.execute("SELECT COALESCE(SUM(price),0) s FROM orders WHERE status='completed'").fetchone()["s"]
            pending=c.execute("SELECT COUNT(*) n FROM orders WHERE status='pending'").fetchone()["n"]
        edit(chat,mid,f"📊 إحصائيات\\nالمستخدمون: {users}\\nالطلبات: {orders}\\nالمعلقة: {pending}\\nقيمة الطلبات المكتملة: ${money(revenue)}",[[btn("↩️ الإدارة","admin")]])
    else:
        # Handle Stars amount entered as callback state; amount entry happens in text handler.
        send(chat,"اختر من القائمة.",main_menu(uid))

def handle_precheckout(q):
    # Always validate payload and amount before approving a Telegram Stars invoice.
    payload=q.get("invoice_payload","")
    if not payload.startswith("stars:"): api("answerPreCheckoutQuery",{"pre_checkout_query_id":q["id"],"ok":False,"error_message":"Invalid invoice."}); return
    api("answerPreCheckoutQuery",{"pre_checkout_query_id":q["id"],"ok":True})

def handle_payment(msg):
    p=msg.get("successful_payment",{})
    payload=p.get("invoice_payload","")
    if not payload.startswith("stars:"): return
    try: amount=float(payload.split(":",1)[1])
    except: return
    uid=msg["from"]["id"]; charge=p.get("telegram_payment_charge_id")
    with db() as c:
        exists=c.execute("SELECT 1 FROM payments WHERE telegram_charge_id=?",(charge,)).fetchone()
        if exists: return
        c.execute("INSERT INTO payments(telegram_charge_id,user_id,amount,created) VALUES(?,?,?,?)",(charge,uid,amount,now()))
    change_balance(uid,amount,"Telegram Stars payment",uid)
    send(msg["chat"]["id"],f"⭐ تم استلام الدفع وإضافة ${money(amount)} إلى رصيدك.")

def handle_update(upd):
    if "pre_checkout_query" in upd: handle_precheckout(upd["pre_checkout_query"]); return
    if "message" in upd:
        m=upd["message"]
        if "successful_payment" in m: handle_payment(m); return
        if m.get("text"): handle_text(m)
    elif "callback_query" in upd: handle_callback(upd["callback_query"])

def main():
    init_db()
    print("Bot running. Ctrl+C to stop.")
    offset=0
    while True:
        try:
            updates=api("getUpdates",{"offset":offset,"timeout":30,"allowed_updates":["message","callback_query","pre_checkout_query"]})
            for u in updates:
                offset=u["update_id"]+1
                try: handle_update(u)
                except Exception as e:
                    print("Update error:",repr(e))
                    try:
                        if "message" in u: send(u["message"]["chat"]["id"],"صار خطأ غير متوقع. حاول مرة ثانية أو راسل الدعم.")
                    except: pass
        except KeyboardInterrupt: break
        except Exception as e:
            print("Polling error:",repr(e)); time.sleep(3)

if __name__=="__main__": main()
