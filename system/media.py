"""Private, bounded uploads. Browser filenames are never filesystem paths."""

import io
import json
import os
import secrets
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from . import store
from .store import db, one, now, audit

MAX_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
PURPOSES = {"services", "broadcasts", "support"}


def upload(file, purpose, actor):
    if purpose not in PURPOSES or not file or not file.filename:
        raise ValueError("اختر ملفًا والغرض من رفعه")
    raw = file.stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("حجم الملف يجب أن يكون أكبر من صفر وألا يتجاوز 20 ميجابايت")
    # Preserve Arabic display names; only a random stored_name becomes a disk path.
    original = Path(file.filename.replace("\\", "/")).name
    original = (
        "".join(ch for ch in original if ch.isprintable() and ch not in '<>"')[:120]
        or "attachment"
    )
    ext = Path(original).suffix.lower()
    kind, mime = "document", "application/octet-stream"
    if ext in (".jpg", ".jpeg", ".png", ".webp"):
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("الصورة لا تتجاوز 10 ميجابايت")
        try:
            with Image.open(io.BytesIO(raw)) as im:
                if (
                    im.format not in ("JPEG", "PNG", "WEBP")
                    or im.width * im.height > Image.MAX_IMAGE_PIXELS
                ):
                    raise ValueError("صيغة الصورة أو أبعادها غير صالحة")
                im.load()
                # Re-encode to remove metadata, scripts appended to files, and ambiguous formats.
                im.thumbnail((2560, 2560))
                output = io.BytesIO()
                im.convert("RGB").save(output, format="JPEG", quality=90)
                raw = output.getvalue()
        except (
            UnidentifiedImageError,
            OSError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            raise ValueError("الصورة تالفة أو غير آمنة") from None
        ext, kind, mime = ".jpg", "photo", "image/jpeg"
    elif ext == ".mp4" and len(raw) >= 12 and raw[4:8] == b"ftyp":
        kind, mime = "video", "video/mp4"
    elif ext == ".pdf" and raw.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif ext == ".txt":
        try:
            raw.decode("utf-8")
            if b"\x00" in raw:
                raise ValueError("ملف نصي غير صالح")
        except UnicodeDecodeError:
            raise ValueError("الملف النصي يجب أن يكون UTF-8") from None
        mime = "text/plain; charset=utf-8"
    else:
        raise ValueError(
            "الأنواع المقبولة: JPG، PNG، WEBP، MP4، PDF، TXT. لا يقبل النظام ملفات HTML أو SVG أو الملفات التنفيذية."
        )
    if purpose == "services" and kind != "photo":
        raise ValueError("الخدمات تقبل الصور فقط")
    folder = store.ROOT / "uploads"
    folder.mkdir(mode=0o700, exist_ok=True)
    stored_name = secrets.token_hex(24) + ext
    path = folder / stored_name
    try:
        with path.open("xb") as target:
            os.chmod(path, 0o600)
            target.write(raw)
        with db() as c:
            aid = c.execute(
                "INSERT INTO assets(name,stored_name,mime,kind,size,purpose,actor,created) VALUES(?,?,?,?,?,?,?,?)",
                (
                    Path(original).stem + ext,
                    stored_name,
                    mime,
                    kind,
                    len(raw),
                    purpose,
                    str(actor),
                    now(),
                ),
            ).lastrowid
            audit(
                c,
                actor,
                "media.upload",
                aid,
                {"name": original, "size": len(raw), "purpose": purpose, "kind": kind},
            )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {
        "id": aid,
        "ref": f"upload:{aid}",
        "kind": kind,
        "name": Path(original).stem + ext,
        "size": len(raw),
        "url": f"/api/media/{aid}",
    }


def asset(c, ref, kind=None, purpose=None):
    if (
        not isinstance(ref, str)
        or not ref.startswith("upload:")
        or not ref[7:].isdigit()
    ):
        raise ValueError("مرجع ملف غير صالح")
    row = one(c, "assets", int(ref[7:]))
    if kind and row["kind"] != kind:
        raise ValueError("نوع الملف المرفوع لا يطابق نوع الوسائط المختار")
    if purpose and row["purpose"] != purpose:
        raise ValueError("الملف المرفوع لا يخص هذا القسم")
    path = store.ROOT / "uploads" / row["stored_name"]
    if (
        path.parent.resolve() != (store.ROOT / "uploads").resolve()
        or not path.is_file()
        or path.is_symlink()
    ):
        raise ValueError("الملف غير موجود أو غير صالح؛ أعد رفعه")
    return row, path


def multipart(data):
    """Return a Bot API body; upload references become real multipart binary files."""
    files = {}
    for key in ("photo", "video", "document"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("upload:"):
            with db() as c:
                row, path = asset(c, value, kind=key)
            files[key] = (row, path)
    if not files:
        return json.dumps(data).encode(), "application/json"
    boundary = "tiktok-" + secrets.token_hex(24)
    chunks = []
    for key, value in data.items():
        chunks.append(f"--{boundary}\r\n".encode())
        if key in files:
            row, path = files[key]
            if path.stat().st_size > MAX_BYTES:
                raise ValueError("الملف يتجاوز الحد المسموح")
            filename = secure_filename(row["name"]) or "attachment"
            chunks.append(
                f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\nContent-Type: {row["mime"]}\r\n\r\n'.encode()
            )
            chunks.append(path.read_bytes())
        else:
            encoded = (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list, bool))
                else str(value)
            )
            chunks.append(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n{encoded}'.encode()
            )
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), "multipart/form-data; boundary=" + boundary
