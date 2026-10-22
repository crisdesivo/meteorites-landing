"""Record the README demo GIF and screenshot of the interactive map (docs/index.html).

    pip install playwright && python -m playwright install chromium
    python scripts/record_demo.py

Drives a headless Chromium through a short scripted session, saves the video,
then converts it to assets/demo.gif with ffmpeg (must be on PATH).
Also writes assets/interactive.png. Fails if the page logs any JS error.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "index.html").as_uri()
ASSETS = ROOT / "assets"
W, H = 1280, 860


def set_range(page, sel, value):
    page.eval_on_selector(
        sel, "(el, v) => { el.value = v; el.dispatchEvent(new Event('input')); }", value
    )


def run(page):
    page.wait_for_timeout(2500)  # tiles + first paint

    # Mass filter: step up to >= 1 kg, then back.
    for v in (1, 2, 3, 4):
        set_range(page, "#mass", v)
        page.wait_for_timeout(500)
    page.wait_for_timeout(700)
    set_range(page, "#mass", 0)
    page.wait_for_timeout(500)

    # Only witnessed falls, then all again.
    page.click("label:has(#found)")
    page.wait_for_timeout(1600)
    page.click("label:has(#found)")
    page.wait_for_timeout(500)

    # Colour by year, then a time-lapse of the year range.
    page.click("label:has(input[value=year])")
    page.wait_for_timeout(600)
    for y in list(range(1850, 2014, 12)) + [2013]:
        set_range(page, "#year-max", y)
        page.wait_for_timeout(230)
    page.wait_for_timeout(900)

    # Quick views: Antarctica (most located finds) and Oman, back to fell/found colours.
    page.click("label:has(input[value=fall])")
    page.click("#views button[data-view=antarctica]")
    page.wait_for_timeout(2600)
    # Click the Yamato field dot: thousands of finds share these coordinates.
    pt = page.evaluate(
        "(() => { const p = meteoriteMap.map.latLngToContainerPoint([-71.5, 35.66667]);"
        " const r = document.getElementById('map').getBoundingClientRect();"
        " return [p.x + r.left, p.y + r.top]; })()"
    )
    page.mouse.move(pt[0] - 120, pt[1] - 60)
    page.mouse.move(pt[0], pt[1], steps=12)
    page.mouse.click(pt[0], pt[1])
    page.wait_for_timeout(2600)
    page.click("#views button[data-view=oman]")
    page.wait_for_timeout(2800)

    # Search for the heaviest meteorite, then back to the world view.
    page.click("#search")
    page.keyboard.type("Hoba", delay=120)
    page.keyboard.press("Enter")
    page.wait_for_timeout(3000)
    page.click("#views button[data-view=world]")
    page.wait_for_timeout(2600)


def main():
    ASSETS.mkdir(exist_ok=True)
    errors = []
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H},
                                  record_video_dir=tmp, record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        page.goto(PAGE)
        page.wait_for_function("window.meteoriteMap !== undefined")
        run(page)
        video = page.video.path()
        ctx.close()

        # Static screenshot in a fresh page (no video overhead).
        page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(PAGE)
        page.wait_for_function("window.meteoriteMap !== undefined")
        page.wait_for_timeout(3000)
        page.screenshot(path=ASSETS / "interactive.png")
        browser.close()

        if errors:
            raise SystemExit("Page errors:\n" + "\n".join(errors))

        shutil.copy(video, Path(tmp) / "demo.webm")
        # Trim the blank first second, 9 fps, 840 px wide, shared palette.
        vf = "fps=9,scale=840:-1:flags=lanczos"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.2", "-i", str(Path(tmp) / "demo.webm"),
             "-vf", f"{vf},split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];"
                    "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
             str(ASSETS / "demo.gif")],
            check=True,
        )
    for f in ("demo.gif", "interactive.png"):
        print(f"wrote assets/{f} ({(ASSETS / f).stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
