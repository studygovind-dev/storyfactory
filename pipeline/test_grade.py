#!/usr/bin/env python3
"""Checks that the cinematic grade and generated ambient music work with the ffmpeg on this machine."""
import subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import GRADE, ROOT, ensure_ambient  # noqa: E402

out = ROOT / "output" / "grade_test"
out.mkdir(parents=True, exist_ok=True)
for mood in ("emotional", "animal", "funny"):
    m = ensure_ambient(mood)
    assert m and m.exists(), f"ambient {mood} failed"
    print("ambient ok:", m.name, m.stat().st_size, "bytes")
r = subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=1080x1920:r=24", "-f", "lavfi", "-i", "sine=f=300",
                    "-i", str(ensure_ambient("emotional")), "-t", "5", "-filter_complex",
                    f"[0:v]{GRADE},vignette=PI/5,noise=alls=5:allf=t[v];[2:a]volume=0.12[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out / "grade.mp4")],
                   capture_output=True, text=True)
print(r.stderr[-800:])
sys.exit(r.returncode)
