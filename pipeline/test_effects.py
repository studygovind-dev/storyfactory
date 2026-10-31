#!/usr/bin/env python3
"""Renders test clips of the free effects (3D parallax, rain, dust, snow) from assets/fx/test.jpg
into output/fx_test/ so they can be checked before they go into real videos."""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from effects import ROOT, living_clip  # noqa: E402

out = ROOT / "output" / "fx_test"
out.mkdir(parents=True, exist_ok=True)
img = out / "test.png"
img.write_bytes((ROOT / "assets" / "fx" / "test.jpg").read_bytes())
for i, fx in enumerate(["none", "rain", "dust", "snow"]):
    t = time.time()
    living_clip(img, i, out / f"{fx}.mp4", 1080, 1920, fx)
    print(f"{fx}: {time.time() - t:.1f}s", flush=True)
