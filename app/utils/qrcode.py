"""QR code PNG generation."""
from __future__ import annotations

import io

import qrcode
from qrcode.constants import ERROR_CORRECT_M


def make_qr_png(data: str, box_size: int = 8) -> bytes:
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=box_size, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
