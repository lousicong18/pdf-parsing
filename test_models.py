"""Connectivity test for all VLM models using the existing vlm client."""

import base64
import json
import sys
import time

import httpx

from src.parser import vlm
from src.utils.metrics import new_task_metrics

# Create a proper 100x100 red PNG (some models reject 1x1)
def _make_test_png():
    import struct, zlib
    w, h = 100, 100
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr_data = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    raw = b''
    for _ in range(h):
        raw += b'\x00' + b'\xff\x00\x00' * w
    compressed = zlib.compress(raw)
    idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
    iend_crc = zlib.crc32(b'IEND') & 0xffffffff
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    return sig + ihdr + idat + iend

_PNG_BYTES = _make_test_png()


def main():
    with open("models.json", encoding="utf-8") as f:
        models = json.load(f)

    print(f"Loaded {len(models)} models, test image: {len(_PNG_BYTES)} bytes\n")
    metrics = new_task_metrics()

    results = {}
    for name, cfg in models.items():
        print(f"=== {name} (model={cfg['model']}, base={cfg['base_url']}) ===")
        t0 = time.time()
        try:
            text = vlm.vlm_describe(_PNG_BYTES, metrics, model_name=name)
            dt = time.time() - t0
            print(f"  ✅ {text[:80]!r}  ({dt:.2f}s)")
            results[name] = True
        except Exception as e:
            dt = time.time() - t0
            detail = ""
            if hasattr(e, 'response'):
                try:
                    detail = e.response.text[:300]
                except:
                    detail = str(e.response.status_code)
            print(f"  ❌ {type(e).__name__}: {e}  ({dt:.2f}s)")
            if detail:
                print(f"     Response: {detail}")
            results[name] = False
        print()

    print("=" * 50)
    for name, ok in results.items():
        print(f"  {name:20s} {'✅' if ok else '❌'}")
    print()
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
