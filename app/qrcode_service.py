"""
QR code generation for short links.

This module exists to satisfy the "ambiguous requirement" scenario
documented in docs/scenarios.md: the original ask ("add QR code support")
specified neither the image format, delivery mechanism, nor persistence
model. The assumptions made here are:
  - Generated on-demand (not persisted) - QR codes are cheap to regenerate
    and this avoids storage/staleness concerns if the short URL is deleted.
  - Returned as PNG bytes via a dedicated endpoint (streamable, cacheable
    by HTTP caches) rather than embedded base64 in JSON, so it can be used
    directly as an <img src> without client-side decoding.
  - Fixed reasonable defaults (box_size, border) rather than exposing every
    QR knob as an API parameter, to keep the surface area small.
"""
import io

import qrcode


def generate_qr_png(data: str) -> bytes:
    img = qrcode.make(data, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
