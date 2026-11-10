"""Read Telegram proof files on the server without exposing the bot token to a browser."""

import io
import re
import urllib.parse
import urllib.request
from PIL import Image, UnidentifiedImageError
from .media import MAX_BYTES


def retrieve(token, file_id, kind):
    from .telegram import call

    metadata = call(token, "getFile", {"file_id": file_id})
    path = metadata.get("file_path", "")
    if (
        not isinstance(path, str)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
        or path.startswith("/")
        or ".." in path.split("/")
    ):
        raise ValueError("مسار إثبات غير صالح")
    if metadata.get("file_size", 0) > MAX_BYTES:
        raise ValueError("الإثبات يتجاوز حد العرض: 20 ميجابايت")
    url = (
        "https://api.telegram.org/file/bot"
        + token
        + "/"
        + urllib.parse.quote(path, safe="/")
    )
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            content = response.read(MAX_BYTES + 1)
    except Exception:
        raise RuntimeError("تعذر تحميل إثبات الدفع من Telegram؛ حاول لاحقًا") from None
    if not content or len(content) > MAX_BYTES:
        raise ValueError("الإثبات فارغ أو يتجاوز حد العرض")
    if kind == "photo":
        try:
            with Image.open(io.BytesIO(content)) as im:
                if im.width * im.height > 20_000_000:
                    raise ValueError("أبعاد الإثبات كبيرة جدًا")
                im.load()
                im.thumbnail((2560, 2560))
                output = io.BytesIO()
                im.convert("RGB").save(output, "JPEG", quality=90)
                return output.getvalue(), "image/jpeg", ".jpg"
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise ValueError("صورة الإثبات غير صالحة") from None
    return (
        content,
        (
            "application/pdf"
            if content.startswith(b"%PDF-")
            else "application/octet-stream"
        ),
        ".pdf" if content.startswith(b"%PDF-") else ".bin",
    )
