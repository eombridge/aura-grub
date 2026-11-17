#!/usr/bin/env python3
"""Generate minimalist aura-light and aura-dark GRUB2 theme assets.

Uses pure Pillow + Python stdlib (no numpy required) to render:
- Banding-free mesh-gradient backgrounds with subtle Gaussian dithering
- 9-slice frosted-glass selection boxes
- 9-slice pill progress bar assets
- 4x supersampled monochrome OS and power-utility icons
"""

from __future__ import annotations

import argparse
import math
import random
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = ROOT_DIR / "themes"


THEMES = {
    "aura-light": {
        "base": (244, 246, 251),
        "blobs": [
            # (cx_frac, cy_frac, rx_frac, ry_frac, color, alpha)
            (0.18, 0.22, 0.45, 0.45, (214, 224, 255), 220),  # soft periwinkle
            (0.82, 0.20, 0.44, 0.44, (206, 236, 255), 210),  # sky mist
            (0.75, 0.80, 0.48, 0.46, (255, 218, 232), 200),  # pastel rose
            (0.24, 0.82, 0.46, 0.44, (212, 244, 234), 195),  # pale mint
            (0.50, 0.48, 0.40, 0.36, (255, 255, 255), 140),  # center lift
        ],
        "noise_sigma": 2.2,
        "select_fill_top": (255, 255, 255, 130),
        "select_fill_bot": (255, 255, 255, 72),
        "select_shadow": (80, 95, 130, 32),
        "progress_bg": (30, 34, 45, 32),
        "progress_fg": (30, 34, 45, 150),
        "icon_color": (28, 32, 44, 235),
        "utility_color": (55, 62, 78, 200),
    },
    "aura-dark": {
        "base": (11, 13, 20),
        "blobs": [
            (0.20, 0.22, 0.46, 0.46, (44, 30, 86), 215),    # deep violet
            (0.82, 0.24, 0.45, 0.45, (18, 50, 76), 210),    # midnight cyan
            (0.74, 0.82, 0.46, 0.46, (56, 24, 64), 195),    # muted plum
            (0.22, 0.80, 0.44, 0.44, (16, 40, 56), 190),    # deep slate teal
            (0.50, 0.50, 0.38, 0.34, (28, 32, 52), 110),    # subtle center aura
        ],
        "noise_sigma": 2.4,
        "select_fill_top": (255, 255, 255, 42),
        "select_fill_bot": (255, 255, 255, 16),
        "select_shadow": (0, 0, 0, 64),
        "progress_bg": (255, 255, 255, 34),
        "progress_fg": (240, 244, 252, 185),
        "icon_color": (242, 244, 248, 238),
        "utility_color": (210, 216, 228, 195),
    },
}


def apply_dither_noise(img: Image.Image, sigma: float, seed: int = 42) -> Image.Image:
    """Add subtle zero-centered monochrome noise to prevent 8-bit gradient banding."""
    w, h = img.size
    rng = random.Random(seed)
    # Generate a fast tileable 256x256 noise patch and tile it, avoiding huge per-pixel Python loops.
    tile_size = 256
    noise_bytes = bytes(
        max(0, min(255, int(128 + rng.gauss(0, sigma))))
        for _ in range(tile_size * tile_size)
    )
    tile = Image.frombytes("L", (tile_size, tile_size), noise_bytes)
    noise_l = Image.new("L", (w, h))
    for y in range(0, h, tile_size):
        for x in range(0, w, tile_size):
            noise_l.paste(tile, (x, y))

    # Blend 50%-centered noise using soft-light / add-subtract via RGB conversion
    rgb = img.convert("RGB")
    r, g, b = rgb.split()
    offset = 128
    # ImageChops.add / subtract with scale=1, offset=-128 shifts noise around 0
    pos = noise_l.point(lambda p: max(0, p - offset))
    neg = noise_l.point(lambda p: max(0, offset - p))
    r = ImageChops.subtract(ImageChops.add(r, pos), neg)
    g = ImageChops.subtract(ImageChops.add(g, pos), neg)
    b = ImageChops.subtract(ImageChops.add(b, pos), neg)
    return Image.merge("RGB", (r, g, b))


def generate_background(theme_cfg: dict, width: int, height: int) -> Image.Image:
    """Render a smooth mesh-like aura gradient at 1/4 scale, blur, upscale, and dither."""
    sw, sh = max(240, width // 4), max(135, height // 4)
    canvas = Image.new("RGBA", (sw, sh), theme_cfg["base"] + (255,))

    for cx_f, cy_f, rx_f, ry_f, color, alpha in theme_cfg["blobs"]:
        layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        cx, cy = cx_f * sw, cy_f * sh
        rx, ry = rx_f * sw, ry_f * sh
        draw.ellipse(
            (cx - rx, cy - ry, cx + rx, cy + ry),
            fill=color + (alpha,),
        )
        layer = layer.filter(ImageFilter.GaussianBlur(radius=max(sw, sh) * 0.14))
        canvas = Image.alpha_composite(canvas, layer)

    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=max(sw, sh) * 0.05))
    upscaled = canvas.resize((width, height), Image.Resampling.BICUBIC)
    return apply_dither_noise(upscaled, sigma=theme_cfg["noise_sigma"])


def save_nine_slice(img: Image.Image, out_dir: Path, prefix: str, edge: int) -> None:
    """Slice an image into 9 GRUB2 pixmap pieces (*_nw, *_n, *_ne, *_w, *_c, *_e, *_sw, *_s, *_se)."""
    w, h = img.size
    if w < edge * 2 + 2 or h < edge * 2 + 2:
        raise ValueError(f"Image {w}x{h} too small for 9-slice edge={edge}")

    xs = [(0, edge), (edge, w - edge), (w - edge, w)]
    ys = [(0, edge), (edge, h - edge), (h - edge, h)]
    names = [
        ["nw", "n", "ne"],
        ["w", "c", "e"],
        ["sw", "s", "se"],
    ]
    for row_idx, (y0, y1) in enumerate(ys):
        for col_idx, (x0, x1) in enumerate(xs):
            piece = img.crop((x0, y0, x1, y1))
            piece.save(out_dir / f"{prefix}_{names[row_idx][col_idx]}.png")


def generate_select_box(theme_cfg: dict, out_dir: Path) -> None:
    """Generate an Apple-style translucent glass pill 9-slice with smooth corners."""
    scale = 2
    size = 64 * scale
    pad = 2 * scale
    radius = 10 * scale  # pad(2) + radius(10) = 12 <= edge(12) for seamless 9-slice corners

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    # 1. Soft diffused drop shadow
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        (pad, pad + scale, size - 1 - pad, size - 1 - pad + scale),
        radius=radius,
        fill=theme_cfg["select_shadow"],
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=2 * scale))
    img = Image.alpha_composite(img, shadow)

    # 2. Translucent vertical gradient fill so background shines through
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(grad)
    r1, g1, b1, a1 = theme_cfg["select_fill_top"]
    r2, g2, b2, a2 = theme_cfg["select_fill_bot"]
    for y in range(pad, size - pad):
        t = (y - pad) / max(1, (size - 2 * pad - 1))
        col = (
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
            int(a1 + (a2 - a1) * t),
        )
        g_draw.line((pad, y, size - 1 - pad, y), fill=col)

    mask = Image.new("L", (size, size), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.rounded_rectangle(
        (pad, pad, size - 1 - pad, size - 1 - pad),
        radius=radius,
        fill=255,
    )
    glass = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glass.paste(grad, (0, 0), mask)
    img = Image.alpha_composite(img, glass)

    img = img.resize((64, 64), Image.Resampling.LANCZOS)
    save_nine_slice(img, out_dir, "select", edge=12)

    # Matching transparent 9-slice for unselected items so icons never shift vertically on selection
    empty = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    save_nine_slice(empty, out_dir, "item", edge=12)


def generate_progress_bar(theme_cfg: dict, out_dir: Path) -> None:
    """Generate 9-slice pill progress bar background and fill."""
    for prefix, color in [
        ("progress_bar", theme_cfg["progress_bg"]),
        ("progress_highlight", theme_cfg["progress_fg"]),
    ]:
        img = Image.new("RGBA", (24, 12), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((0, 0, 23, 11), radius=5, fill=color)
        save_nine_slice(img, out_dir, prefix, edge=4)


def new_icon_canvas(size: int = 256) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def draw_fedora(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    # Rounded speech-bubble / squircle outline + clean stylized 'f' loop
    draw.rounded_rectangle((36, 36, 220, 220), radius=68, outline=color, width=18)
    # Inner 'f' stem & crossbar
    draw.arc((114, 72, 184, 142), start=180, end=355, fill=color, width=18)
    draw.line((123, 106, 123, 184), fill=color, width=18)
    draw.arc((74, 134, 132, 192), start=0, end=180, fill=color, width=18)
    draw.line((96, 132, 154, 132), fill=color, width=16)
    return img


def draw_ubuntu(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    cx, cy, r = 128, 128, 66
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=18)
    # 3 outer nodes
    for deg in (-90, 30, 150):
        rad = math.radians(deg)
        nx = cx + math.cos(rad) * 74
        ny = cy + math.sin(rad) * 74
        # Cutout ring behind node
        draw.ellipse((nx - 24, ny - 24, nx + 24, ny + 24), fill=(0, 0, 0, 0))
        draw.ellipse((nx - 16, ny - 16, nx + 16, ny + 16), fill=color)
    return img


def draw_arch(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    outer = [(128, 32), (218, 214), (168, 194), (128, 174), (88, 194), (38, 214)]
    draw.polygon(outer, fill=color)
    # Inner cutout notch
    notch = [(128, 126), (150, 176), (128, 166), (106, 176)]
    draw.polygon(notch, fill=(0, 0, 0, 0))
    return img


def draw_debian(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    # Clean concentric swirl arcs
    draw.arc((44, 40, 212, 208), start=130, end=420, fill=color, width=16)
    draw.arc((72, 68, 184, 180), start=150, end=400, fill=color, width=15)
    draw.arc((100, 96, 156, 152), start=160, end=370, fill=color, width=14)
    return img


def draw_linux(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    # Minimalist terminal/kernel rounded square + prompt >_
    draw.rounded_rectangle((36, 48, 220, 208), radius=34, outline=color, width=16)
    draw.line((76, 98, 114, 128), fill=color, width=16, joint="curve")
    draw.line((114, 128, 76, 158), fill=color, width=16, joint="curve")
    draw.line((126, 160, 176, 160), fill=color, width=16)
    return img


def draw_windows(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    gap = 12
    s = 72
    x0, y0 = 48, 48
    for row in range(2):
        for col in range(2):
            px = x0 + col * (s + gap)
            py = y0 + row * (s + gap)
            draw.rounded_rectangle((px, py, px + s, py + s), radius=10, fill=color)
    return img


def draw_macos(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    # Minimalist rounded squircle with subtle smile/finder-like emblem
    draw.rounded_rectangle((42, 42, 214, 214), radius=46, outline=color, width=16)
    draw.line((98, 92, 98, 118), fill=color, width=14)
    draw.line((158, 92, 158, 118), fill=color, width=14)
    draw.arc((82, 108, 174, 172), start=20, end=160, fill=color, width=14)
    return img


def draw_recovery(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    # Shield outline + plus cross
    shield = [(128, 36), (206, 68), (196, 154), (128, 218), (60, 154), (50, 68)]
    draw.polygon(shield, outline=color, width=16)
    draw.line((128, 90, 128, 162), fill=color, width=16)
    draw.line((92, 126, 164, 126), fill=color, width=16)
    return img


def draw_shutdown(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    # Drawn smaller inside 256x256 so utility icons look compact & secondary
    draw.arc((68, 72, 188, 192), start=-55, end=235, fill=color, width=16)
    draw.line((128, 56, 128, 120), fill=color, width=16)
    return img


def draw_restart(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    draw.arc((68, 68, 188, 188), start=30, end=315, fill=color, width=16)
    # Arrowhead at top-right
    arrow = [(174, 62), (194, 96), (154, 96)]
    draw.polygon(arrow, fill=color)
    return img


def draw_efi(color: tuple[int, int, int, int]) -> Image.Image:
    img, draw = new_icon_canvas()
    # Minimalist chip icon
    draw.rounded_rectangle((78, 78, 178, 178), radius=18, outline=color, width=14)
    draw.rounded_rectangle((106, 106, 150, 150), radius=6, fill=color)
    for pos in (104, 128, 152):
        draw.line((pos, 56, pos, 78), fill=color, width=10)
        draw.line((pos, 178, pos, 200), fill=color, width=10)
        draw.line((56, pos, 78, pos), fill=color, width=10)
        draw.line((178, pos, 200, pos), fill=color, width=10)
    return img


ICON_GENERATORS = {
    "fedora": (draw_fedora, "os"),
    "ubuntu": (draw_ubuntu, "os"),
    "arch": (draw_arch, "os"),
    "debian": (draw_debian, "os"),
    "linux": (draw_linux, "os"),
    "gnu-linux": (draw_linux, "os"),
    "windows": (draw_windows, "os"),
    "macosx": (draw_macos, "os"),
    "macos": (draw_macos, "os"),
    "recovery": (draw_recovery, "os"),
    "shutdown": (draw_shutdown, "utility"),
    "restart": (draw_restart, "utility"),
    "efi": (draw_efi, "utility"),
}


def build_theme(name: str, width: int, height: int, icon_size: int) -> Path:
    cfg = THEMES[name]
    out_dir = THEMES_DIR / name
    icons_dir = out_dir / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    bg = generate_background(cfg, width, height)
    bg.save(out_dir / "background.png", optimize=True)

    generate_select_box(cfg, out_dir)
    generate_progress_bar(cfg, out_dir)

    for icon_name, (fn, kind) in ICON_GENERATORS.items():
        color = cfg["icon_color"] if kind == "os" else cfg["utility_color"]
        hi_res = fn(color)
        icon = hi_res.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        icon.save(icons_dir / f"{icon_name}.png", optimize=True)

    return out_dir


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate aura-grub theme assets.")
    parser.add_argument("--width", type=int, default=1920, help="Background width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Background height (default: 1080)")
    parser.add_argument("--icon-size", type=int, default=64, help="Icon size in px (default: 64)")
    parser.add_argument(
        "--theme",
        choices=[*THEMES.keys(), "all"],
        default="all",
        help="Theme variant to build (default: all)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    targets = list(THEMES.keys()) if args.theme == "all" else [args.theme]
    for name in targets:
        out_dir = build_theme(name, args.width, args.height, args.icon_size)
        print(f"Generated {name} -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
