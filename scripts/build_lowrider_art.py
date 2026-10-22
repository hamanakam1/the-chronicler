#!/usr/bin/env python3
"""Regenerate the lowrider ASCII art embedded in ``chronicler.ascii_art``.

The art is a hand-composed, chop-top LA lowrider with wire wheels, chrome
trim and a slammed stance, followed by a smaller cruise line of cars in the
background. Run this script to refresh the art after editing it here::

    python3 scripts/build_lowrider_art.py

It rewrites the ``LOWRIDER_ART`` constant in ``src/chronicler/ascii_art.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "src" / "chronicler" / "ascii_art.py"

W, H = 78, 24


def make_grid() -> list[list[str]]:
    return [[" "] * W for _ in range(H)]


def put(grid, row: int, col: int, text: str) -> None:
    for i, ch in enumerate(text):
        r, c = row, col + i
        if 0 <= r < H and 0 <= c < W:
            grid[r][c] = ch


def wheel(grid, cx: int, cy: int, r: int) -> None:
    """A round wire wheel: rim outline, wire spokes, polished hub."""
    inside = set()
    for row in range(cy - r + 1, cy + r):
        for col in range(cx - r + 1, cx + r):
            if (row - cy) ** 2 + (col - cx) ** 2 <= (r - 1) ** 2:
                inside.add((row, col))

    for row, col in inside:
        dr, dc = row - cy, col - cx
        if dr * dc > 0 or abs(dr) == abs(dc):
            grid[row][col] = ":"

    for row in range(cy - 1, cy + 2):
        for col in range(cx - 2, cx + 3):
            grid[row][col] = "O"

    for row in range(cy - r, cy + r + 1):
        grid[row][cx - r] = "."
        grid[row][cx + r] = "."
    for col in range(cx - r, cx + r + 1):
        grid[cy - r][col] = "."
        grid[cy + r][col] = "'"


def hero_car() -> list[str]:
    """The chop-top lowrider: chopped top, chrome trim, wire wheels."""
    tyres = make_grid()
    wheel(tyres, 20, 17, 5)
    wheel(tyres, 57, 17, 5)

    body = make_grid()
    put(body, 0, 32, "____________________")
    put(body, 1, 27, "____/                    \\______")
    put(body, 2, 22, "____/                            \\______")
    put(body, 3, 17, "/                                     \\____")
    put(body, 4, 16, "|   ____________         [] _________    |")
    put(body, 5, 15, "|  |          |____________|         |   |")
    put(body, 6, 15, "|  |__________|            |_________|   |")
    put(body, 7, 15, "|=========================================|")
    put(body, 8, 15, "|   O                                    O  |")
    put(body, 9, 14, "|                                          |")
    put(body, 10, 14, "|                                          |")
    put(body, 11, 14, "|__________________________________________|")
    put(body, 11, 15, "|=")
    put(body, 11, 45, "=|")

    canvas = make_grid()
    for r in range(H):
        for c in range(W):
            canvas[r][c] = tyres[r][c] if tyres[r][c] != " " else body[r][c]
    put(canvas, 23, 6, "=" * 66)
    return ["".join(r).rstrip() for r in canvas]


# The background cruise: smaller block-font cars staggered down the street.
CAR = r"""
                                       _     _ 
                                      | |   | |
                                      | |   | |
                                      | |   | |
                              _   _ _   _| |__ | |__   ___  _ __   ___  _ __ 
                             | | | | | | | '_ \| '_ \ / _ \| '_ \ / _ \| '__|
                             | |_| | |_| | | | | | | |  _/| | | |  _/| |   
                              \___/ \___/|_| |_|_| |_| |_| |_| |_| |_|  |_| 
"""

LOW = r"""
                                      _       _ 
                                     | |     | |
                                     | |     | |
                             _   _  | |     | |  _   _ 
                            | | | | | |     | | | | | |
                            | |_| | | |___  | |_| |_| |
                             \___/  \____/  \___/ \___/ 
"""


def cruise_line() -> list[str]:
    """Two cars staggered down the street, receding to the right."""
    width, height = 140, 18
    grid = [[" "] * width for _ in range(height)]
    blocks = [(CAR, 2, 1), (LOW, 70, 7)]
    for art, col, row in blocks:
        for i, line_text in enumerate(art.strip("\n").split("\n")):
            if row + i >= height:
                continue
            for j, ch in enumerate(line_text):
                c = col + j
                if 0 <= c < width:
                    grid[row + i][c] = ch
    return ["".join(r).rstrip() for r in grid]


def build() -> str:
    hero = hero_car()
    cruise = cruise_line()
    lines = [""] + hero
    lines.append("")
    lines.extend(cruise)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    art = build()
    text = TARGET.read_text()
    new_text, count = re.subn(
        r'LOWRIDER_ART = r""".*?"""',
        lambda _m: 'LOWRIDER_ART = r"""' + art + '"""',
        text,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("could not find the LOWRIDER_ART constant to rewrite")
    TARGET.write_text(new_text)
    print(art)
    print(f"\nrewrote LOWRIDER_ART in {TARGET.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
