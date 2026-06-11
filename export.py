"""
carousel-factory - export.py
Turn one HTML file into a folder of Instagram-ready slide PNGs.

USAGE:
    python export.py                          # everything under ./carousels + ./examples
    python export.py path/to/folder           # one carousel folder, or a root of many
    python export.py path/to/carousel.html    # one file
    python export.py --size 1080x1350         # output size (default 1080x1350, IG portrait)

HOW IT FINDS SLIDES (in priority order):
    1. elements with class="slide"
    2. elements with id="s1", "s2", ... (legacy)

OUTPUT:
    <carousel_folder>/slides/slide_01.png ... slide_NN.png

SETUP (once):
    pip install playwright
    playwright install chromium
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

SCRIPT_DIR = Path(__file__).parent
DEFAULT_ROOTS = [SCRIPT_DIR / "carousels", SCRIPT_DIR / "examples"]

OUT_W, OUT_H = 1080, 1350  # overridable via --size


async def find_slides(page):
    """Return bounding boxes for every slide, however the author marked them."""
    boxes = await page.evaluate(
        """() => {
            let els = [...document.querySelectorAll('.slide')];
            if (!els.length) {
                els = [];
                for (let i = 1; i <= 50; i++) {
                    const el = document.getElementById('s' + i);
                    if (!el) break;
                    els.push(el);
                }
            }
            return els.map(el => {
                const r = el.getBoundingClientRect();
                return { x: r.x, y: r.y, width: r.width, height: r.height };
            });
        }"""
    )
    return boxes


async def export_carousel(browser, html_file: Path) -> None:
    out_dir = html_file.parent / "slides"
    out_dir.mkdir(parents=True, exist_ok=True)

    # First pass at natural size to measure the slides
    probe = await browser.new_page(viewport={"width": 1400, "height": 1200})
    await probe.set_content(html_file.read_text(encoding="utf-8"), wait_until="networkidle")
    boxes = await find_slides(probe)
    await probe.close()
    if not boxes:
        print("    !! no slides found (need class='slide' or ids s1..sN) - skipping")
        return

    slide_w = boxes[0]["width"]
    scale = OUT_W / slide_w  # render at device scale so output is exactly OUT_W wide

    page = await browser.new_page(
        viewport={"width": int(slide_w) + 120, "height": int(sum(b["height"] for b in boxes)) + 400},
        device_scale_factor=scale,
    )
    await page.set_content(html_file.read_text(encoding="utf-8"), wait_until="networkidle")
    await page.wait_for_timeout(2500)  # let webfonts settle

    boxes = await find_slides(page)
    for i, b in enumerate(boxes, 1):
        out_path = out_dir / f"slide_{i:02d}.png"
        await page.screenshot(path=str(out_path), clip=b)
        print(f"    slide {i}/{len(boxes)}  ->  {out_path.relative_to(html_file.parent)}")

    await page.close()


def find_carousels(target: Path) -> list[Path]:
    if target.is_file() and target.suffix == ".html":
        return [target]
    if (target / "carousel.html").exists():
        return [target / "carousel.html"]
    return sorted(p for p in target.glob("**/carousel.html") if "slides" not in p.parts)


async def main():
    global OUT_W, OUT_H
    args = [a for a in sys.argv[1:]]
    targets = []
    for a in list(args):
        if a == "--size":
            idx = args.index(a)
            OUT_W, OUT_H = map(int, args[idx + 1].lower().split("x"))
            args.remove(args[idx + 1]); args.remove(a)
        else:
            targets.append(Path(a).resolve())
    if not targets:
        targets = [r for r in DEFAULT_ROOTS if r.exists()]

    files = []
    for t in targets:
        files += find_carousels(t)
    if not files:
        print("\nNo carousels found. Point me at a folder containing carousel.html\n")
        return

    print(f"\nFound {len(files)} carousel(s):")
    for f in files:
        print(f"  - {f.parent.name}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            for html_file in files:
                print(f">> Exporting: {html_file.parent.name}")
                await export_carousel(browser, html_file)
                print()
        finally:
            await browser.close()
    print("All done.\n")


if __name__ == "__main__":
    asyncio.run(main())
