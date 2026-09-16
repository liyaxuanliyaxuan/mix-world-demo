#!/usr/bin/env python3
"""Render end-effector trajectory SVGs for the four action-control conditions.

Reads the handover raw_action.npy arrays (14D absolute ee pose: per arm
[x,y,z,rx,ry,rz,gripper]) and writes one self-contained SVG per condition:
  - top-down XY path of both grippers in the local (initial-pose) frame,
    with dots at the paper's display times (0 / 4.8 / 9.6 / 12 / 14.4 / 16.8 / 19.2 s)
  - gripper open-state strip over the full 38.4 s
Pure-Python + numpy; no matplotlib. Deterministic; originals are read-only.
"""
import numpy as np
import os

SRC = "~/Downloads/MiXWorld_网站素材交接_20260915/01_fig04_fixed_socks_action"
OUT = "./public/media/actions"
CONDITIONS = ["recorded", "hold_right", "xy_inverted", "hold_both"]
NAMES = {
    "recorded": "original",
    "hold_right": "right_held",
    "xy_inverted": "xy_inverted",
    "hold_both": "both_held",
}
FPS = 10
TIME_MARKS_S = [0, 4.8, 9.6, 12.0, 14.4, 16.8, 19.2]
C_LEFT, C_RIGHT = "#2c6e9e", "#d4883a"
INK, GRID = "#5a5f5b", "#e7e4dc"

W, H = 640, 420
PLOT = (10, 10, 620, 270)        # x, y, w, h
GRIP = (10, 320, 620, 70)


def poly(ax, x0, y0, x1, y1, stroke, width, dash=None, opacity=1.0):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    op = f' opacity="{opacity}"' if opacity < 1 else ""
    ax.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{stroke}" stroke-width="{width}"{d}{op}/>')


def render(cond):
    a = np.load(f"{SRC}/{cond}/raw_action.npy")  # (385, 14)
    t = np.arange(len(a)) / FPS

    # local top-down XY displacement per gripper (col 0/1 = left x/y, 7/8 = right x/y)
    lx, ly = a[:, 0] - a[0, 0], a[:, 1] - a[0, 1]
    rx, ry = a[:, 7] - a[0, 7], a[:, 8] - a[0, 8]
    lo = min(lx.min(), ly.min(), rx.min(), ry.min())
    hi = max(lx.max(), ly.max(), rx.max(), ry.max())
    pad = 0.02 + (hi - lo) * 0.06
    lo, hi = lo - pad, hi + pad

    px, py, pw, ph = PLOT
    sx = lambda v: px + (v - lo) / (hi - lo) * pw
    sy = lambda v: py + ph - (v - lo) / (hi - lo) * ph
    tx = lambda tt: px + tt / 38.4 * pw

    ax = []
    # grid + axes
    for g in np.linspace(lo, hi, 5):
        poly(ax, px, sy(g), px + pw, sy(g), GRID, 1)
        poly(ax, sx(g), py, sx(g), py + ph, GRID, 1)
    poly(ax, px, py + ph, px + pw, py + ph, INK, 1)
    poly(ax, px, py, px, py + ph, INK, 1)

    def path(xs, ys, color):
        pts = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in zip(xs, ys))
        ax.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
        # time dots
        for tm in TIME_MARKS_S[1:]:
            k = int(round(tm * FPS))
            k = min(k, len(xs) - 1)
            ax.append(f'<circle cx="{sx(xs[k]):.1f}" cy="{sy(ys[k]):.1f}" r="3" fill="{color}" stroke="#fff" stroke-width="1.2"/>')
        ax.append(f'<circle cx="{sx(xs[0]):.1f}" cy="{sy(ys[0]):.1f}" r="4.5" fill="none" stroke="{color}" stroke-width="1.6"/>')

    path(lx, ly, C_LEFT)
    path(rx, ry, C_RIGHT)

    # axis labels (range in cm)
    for g, tt in [(lo, "0%"), (hi, "100%")]:
        pass
    ax.append(f'<text x="{px}" y="{py + ph + 16}" font-size="11" fill="{INK}" font-family="Inter,system-ui,sans-serif">X: {(hi-lo)*100:.0f} cm across</text>')
    ax.append(f'<text x="{px}" y="{py - 2}" font-size="11" fill="{INK}" font-family="Inter,system-ui,sans-serif">Top-down view — local XY (m)</text>')
    for tm in TIME_MARKS_S:
        x = tx(tm)
        if tm > 0:
            poly(ax, x, py + ph, x, py + ph + 5, INK, 1)
        ax.append(f'<text x="{x:.1f}" y="{py + ph + 28}" text-anchor="middle" font-size="10" fill="{INK}" font-family="Inter,system-ui,sans-serif">{tm:g}s</text>')

    # legend
    ax.append(f'<circle cx="{px + pw - 150}" cy="{py + 12}" r="4" fill="{C_LEFT}"/>')
    ax.append(f'<text x="{px + pw - 140}" y="{py + 16}" font-size="11" fill="{INK}" font-family="Inter,system-ui,sans-serif">Left</text>')
    ax.append(f'<circle cx="{px + pw - 80}" cy="{py + 12}" r="4" fill="{C_RIGHT}"/>')
    ax.append(f'<text x="{px + pw - 70}" y="{py + 16}" font-size="11" fill="{INK}" font-family="Inter,system-ui,sans-serif">Right</text>')

    # gripper strip (0..5 raw -> open fraction), 150 downsampled points
    gx0, gy0, gw, gh = GRIP
    poly(ax, gx0, gy0, gx0, gy0 + gh, GRID, 1)
    poly(ax, gx0, gy0 + gh, gx0 + gw, gy0 + gh, INK, 1)
    for frac, col, ch, lab in [(1 / 3, C_LEFT, 6, "Left"), (2 / 3, C_RIGHT, 13, "Right")]:
        sig = a[:, ch] / 5.0
        idx = np.linspace(0, len(sig) - 1, 150).astype(int)
        pts = " ".join(f"{gx0 + (i / 149) * gw:.1f},{gy0 + gh - sig[i] * gh:.1f}" for i in range(150))
        ax.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.8"/>')
        ax.append(f'<text x="{gx0 + frac * gw - 24:.0f}" y="{gy0 - 6}" font-size="10" fill="{INK}" font-family="Inter,system-ui,sans-serif">{lab} gripper</text>')
    ax.append(f'<text x="{gx0}" y="{gy0 + gh + 16}" font-size="10" fill="{INK}" font-family="Inter,system-ui,sans-serif">Gripper open fraction — 0 to 38.4 s</text>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'role="img" aria-label="End-effector trajectory, {cond}">' + "".join(ax) + "</svg>")
    out = f"{OUT}/traj_{NAMES[cond]}.svg"
    with open(out, "w") as f:
        f.write(svg)
    print("wrote", out, len(svg), "bytes")


os.makedirs(OUT, exist_ok=True)
for c in CONDITIONS:
    render(c)
print("DONE")
