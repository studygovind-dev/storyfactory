"""
Free "living picture" effects for the daily stories (no paid video model):
  - 3D parallax: a small free AI model guesses how far away each part of the picture is,
    then near things slide more than far things, like a real camera moving.
  - weather / atmosphere layers: rain, snow, floating dust (drawn here, nothing downloaded).
Everything degrades gracefully: without the depth model a clip is a plain zoom.
"""
import random, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FX_DIR = ROOT / "assets" / "fx"
FPS = 24
_depth_pipe = None


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed:\n{' '.join(map(str, cmd))}\n{r.stderr[-1500:]}")


def depth_map(img):
    """Grey picture: white = near, black = far. None if the model is not installed."""
    out = img.with_name(img.stem + "_depth.png")
    if out.exists():
        return out
    global _depth_pipe
    if _depth_pipe is False:  # model already failed once this run
        return None
    try:
        if _depth_pipe is None:
            from transformers import pipeline
            _depth_pipe = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf")
        from PIL import Image
        _depth_pipe(Image.open(img).convert("RGB"))["depth"].save(out)
        return out
    except Exception as e:  # no torch/transformers, or download failed: plain zoom instead
        print(f"  (no 3D depth: {type(e).__name__}; using plain zoom)")
        _depth_pipe = False
        return None


def fx_loop(kind):
    """A 2-second looping layer (white on black) for rain / snow / dust, drawn once and cached."""
    out = FX_DIR / f"{kind}.mp4"
    if out.exists():
        return out
    from PIL import Image, ImageDraw, ImageFilter
    FX_DIR.mkdir(parents=True, exist_ok=True)
    w, h, n = 540, 960, 48
    rnd = random.Random(kind)
    if kind == "rain":
        drops = [(rnd.uniform(0, w), rnd.uniform(0, h), rnd.choice([1, 2])) for _ in range(170)]
    elif kind == "snow":
        drops = [(rnd.uniform(0, w), rnd.uniform(0, h), rnd.choice([1, 2, 3])) for _ in range(160)]
    else:  # dust: big soft warm specks drifting up
        drops = [(rnd.uniform(0, w), rnd.uniform(0, h), rnd.choice([2, 3, 4, 6])) for _ in range(45)]
    proc = subprocess.Popen(["ffmpeg", "-y", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", str(out)],
                            stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for f in range(n):
        im = Image.new("RGB", (w, h))
        d = ImageDraw.Draw(im)
        for k, (x, y, s) in enumerate(drops):
            if kind == "rain":  # falls 4 screen heights per loop
                yy = (y + f * 4 * h / n) % h
                d.line([(x, yy), (x - 3, yy + 22 * s)], fill=(105, 112, 125), width=s)
            elif kind == "snow":  # falls one screen height per loop, sways
                yy = (y + f * h / n) % h
                xx = x + 6 * ((f + k) % 12 - 6) / 6
                d.ellipse([xx - s, yy - s, xx + s, yy + s], fill=(235, 235, 240))
            else:
                yy = (y - f * h / (4 * n)) % h
                d.ellipse([x - s, yy - s, x + s, yy + s], fill=(255, 210, 140))
        if kind == "dust":
            im = im.filter(ImageFilter.GaussianBlur(2))
        im.save(proc.stdin, "PNG")
    proc.stdin.close()
    proc.wait()
    return out


def living_clip(img, i, out, w, h, fx="none", secs=5.0):
    """Still picture -> 5 s clip with 3D parallax, a slow push-in and an optional weather layer."""
    ww, hh = int(w * 1.12) // 2 * 2, int(h * 1.12) // 2 * 2   # margin hides the edges of the slide
    depth = depth_map(img)
    sign = 1 if i % 2 == 0 else -1                           # alternate the direction per scene
    zoom = f"scale=w='{w}*(1+0.06*t/{secs})':h='{h}*(1+0.06*t/{secs})':eval=frame,crop={w}:{h}"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-t", str(secs), "-i", str(img)]
    base = f"[0:v]scale={ww}:{hh}:force_original_aspect_ratio=increase,crop={ww}:{hh},setsar=1"
    if depth:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", str(secs), "-i", str(depth)]
        amp = 46 * sign  # how far (pixels) the nearest things slide over the clip
        move = f"(lum(X,Y)/255-0.45)*{amp}*(2*T/{secs}-1)"
        graph = (f"{base},format=gbrp[src];"
                 f"[1:v]format=gray,scale={ww // 2}:{hh // 2},split[a][b];"
                 f"[a]geq=lum='128+{move}',scale={ww}:{hh},format=gbrp[xm];"
                 f"[b]geq=lum='128+0.35*{move}',scale={ww}:{hh},format=gbrp[ym];"
                 f"[src][xm][ym]displace=edge=smear,crop={int(w * 1.06) // 2 * 2}:{int(h * 1.06) // 2 * 2},"
                 f"{zoom},format=gbrp[v0]")
    else:
        graph = f"{base},{zoom},format=gbrp[v0]"
    if fx in ("rain", "snow", "dust"):
        cmd += ["-stream_loop", "-1", "-i", str(fx_loop(fx))]
        k = 2 if depth else 1
        graph += (f";[{k}:v]scale={w}:{h},fps={FPS},format=gbrp[fx];"
                  f"[v0][fx]blend=all_mode=screen:shortest=1,format=yuv420p[v]")
    else:
        graph += ";[v0]format=yuv420p[v]"
    cmd += ["-filter_complex", graph, "-map", "[v]", "-t", str(secs), "-r", str(FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]
    _run(cmd)
