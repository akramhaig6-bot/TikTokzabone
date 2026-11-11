"""Operations for the dynamic menu builder; edits never execute Python from content."""

import re
from .store import *


def check_key(key):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,79}", key):
        raise ValueError(
            "معرّف القائمة يبدأ بحرف إنجليزي، ويحتوي حروفًا وأرقامًا وشرطة ونقطة فقط"
        )


def menu_clone(c, mid, key, name, actor):
    check_key(key)
    m = one(c, "menus", mid)
    new = c.execute(
        "INSERT INTO menus(name,key,text,kind,layout_key) VALUES(?,?,?,?,?)",
        (name or m["name"] + " — نسخة", key, m["text"], m["kind"], m["layout_key"]),
    ).lastrowid
    for btn in rows(
        c, "SELECT * FROM buttons WHERE menu_id=? ORDER BY row_num,col_num,id", (mid,)
    ):
        cols = [
            "label",
            "kind",
            "action",
            "target",
            "row_num",
            "col_num",
            "enabled",
            "permission",
            "child_menu",
            "style",
        ]
        c.execute(
            "INSERT INTO buttons(menu_id,"
            + ",".join(cols)
            + ") VALUES("
            + ",".join("?" for _ in range(len(cols) + 1))
            + ")",
            [new] + [btn[k] for k in cols],
        )
    audit(c, actor, "menu.cloned", new, {"from": mid, "key": key})
    return new


def button_move(c, bid, direction, actor):
    btn = one(c, "buttons", bid)
    row, col = btn["row_num"], btn["col_num"]
    if direction not in ("up", "down", "left", "right"):
        raise ValueError("اتجاه غير صالح")
    row = max(0, row + (-1 if direction == "up" else 1 if direction == "down" else 0))
    col = max(
        0, col + (-1 if direction == "right" else 1 if direction == "left" else 0)
    )
    occupied = c.execute(
        "SELECT id FROM buttons WHERE menu_id=? AND row_num=? AND col_num=? AND id!=?",
        (btn["menu_id"], row, col, bid),
    ).fetchone()
    if occupied:
        c.execute(
            "UPDATE buttons SET row_num=?,col_num=? WHERE id=?",
            (btn["row_num"], btn["col_num"], occupied["id"]),
        )
    c.execute("UPDATE buttons SET row_num=?,col_num=? WHERE id=?", (row, col, bid))
    audit(
        c,
        actor,
        "button.moved",
        bid,
        {"direction": direction, "row": row, "column": col},
    )
