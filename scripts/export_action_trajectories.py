#!/usr/bin/env python3
"""SUPERSEDED 2026-09-16: do not run. This exported commanded robot-base
displacements (local-frame XY), which do not correspond to the video frames.
The action panel now plots frame-accurate gripper positions produced by
scripts/track_gripper_positions.py, which overwrites the same traj_*.json
files with video-measured coordinates.

Export per-condition end-effector trajectory data as JSON for the
on-video animated overlay (canvas).

Source: handover raw_action.npy (14D absolute ee pose, per arm
[x,y,z,rx,ry,rz,gripper]). Emits local-frame XY (meters) + gripper open
fraction (0..1) at 10 fps, plus bounds shared by all four conditions so the
overlay scale never jumps when switching conditions. Replaces the earlier
static SVG export. Deterministic; originals read-only.
"""
import json
import numpy as np

SRC = "~/Downloads/MiXWorld_网站素材交接_20260915/01_fig04_fixed_socks_action"
OUT = "./public/media/actions"
CONDITIONS = {
    "recorded": "original",
    "hold_right": "right_held",
    "xy_inverted": "xy_inverted",
    "hold_both": "both_held",
    "reverse_generated_end": "time_reversed",
}
FPS = 10
PAD = 0.03  # meters
# owner directive 2026-09-15: xy_inverted is presented for the first 16 s only
DURATION_CAP_S = {"xy_inverted": 16.0}


def series(a, cap=None):
    n = len(a)
    if cap is not None:
        n = min(n, int(round(cap * FPS)) + 1)
    t = (np.arange(n) / FPS).round(2).tolist()
    return {
        "t": t,
        "duration_s": round((n - 1) / FPS, 2),
        "left": {
            "x": (a[:n, 0] - a[0, 0]).round(4).tolist(),
            "y": (a[:n, 1] - a[0, 1]).round(4).tolist(),
            "grip": (a[:n, 6] / 5.0).round(3).tolist(),
        },
        "right": {
            "x": (a[:n, 7] - a[0, 7]).round(4).tolist(),
            "y": (a[:n, 8] - a[0, 8]).round(4).tolist(),
            "grip": (a[:n, 13] / 5.0).round(3).tolist(),
        },
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    bounds = [float("inf"), float("-inf"), float("inf"), float("-inf")]  # x0,x1,y0,y1
    data = {}
    for cond, name in CONDITIONS.items():
        a = np.load(f"{SRC}/{cond}/raw_action.npy")
        s = series(a, cap=DURATION_CAP_S.get(name))
        data[name] = s
        for arm in ("left", "right"):
            bounds[0] = min(bounds[0], min(s[arm]["x"]))
            bounds[1] = max(bounds[1], max(s[arm]["x"]))
            bounds[2] = min(bounds[2], min(s[arm]["y"]))
            bounds[3] = max(bounds[3], max(s[arm]["y"]))
    shared = {
        "bounds": {
            "xmin": round(bounds[0] - PAD, 4), "xmax": round(bounds[1] + PAD, 4),
            "ymin": round(bounds[2] - PAD, 4), "ymax": round(bounds[3] + PAD, 4),
        },
        "note": "local end-effector XY (m), gripper open fraction 0..1; source raw_action.npy",
    }
    for name, s in data.items():
        s.update(shared)
        with open(f"{OUT}/traj_{name}.json", "w") as f:
            json.dump(s, f, separators=(",", ":"))
        print("wrote", f"traj_{name}.json")


if __name__ == "__main__":
    import os
    main()
