"""Extract editable default templates and static button layouts; never executes bot code."""

import ast, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
catalog = {}
layouts = {}
HOME = [[{"text": "🏠 الرئيسية", "callback_data": "home"}]]


def constant(node):
    if isinstance(node, ast.Name) and node.id == "HOME":
        return HOME
    if isinstance(node, ast.List):
        return [constant(n) for n in node.elts]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return constant(node.left) + constant(node.right)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "b"
    ):
        return {
            "text": ast.literal_eval(node.args[0]),
            "callback_data": ast.literal_eval(node.args[1]),
        }
    return ast.literal_eval(node)


for path in (ROOT / "system").glob("*.py"):
    for node in ast.walk(ast.parse(path.read_text())):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        name = node.func.id
        if name in ("say", "text", "render"):
            ki, di = (2, 3) if name == "say" else (1, 2)
            try:
                key = ast.literal_eval(node.args[ki])
                default = ast.literal_eval(node.args[di])
                if isinstance(key, str) and isinstance(default, str):
                    catalog.setdefault(key, default)
            except (IndexError, ValueError, TypeError):
                pass
            if name == "say":
                kwargs = {k.arg: k.value for k in node.keywords}
                try:
                    layout = constant(kwargs.get("layout") or node.args[6])
                    buttons = constant(kwargs.get("buttons") or node.args[5])
                    if isinstance(layout, str):
                        layouts[layout] = buttons
                except (IndexError, ValueError, TypeError):
                    pass
        if name == "b":
            try:
                label = ast.literal_eval(node.args[0])
                if (
                    isinstance(label, str)
                    and " — " not in label
                    and not label[:1].isdigit()
                ):
                    catalog.setdefault(
                        "label_" + hashlib.sha256(label.encode()).hexdigest()[:12],
                        label,
                    )
            except (IndexError, ValueError, TypeError):
                pass
(ROOT / "system/catalog.json").write_text(
    json.dumps({"messages": catalog, "layouts": layouts}, ensure_ascii=False, indent=2)
    + "\n"
)
print(f"{len(catalog)} messages/labels, {len(layouts)} static layouts")
