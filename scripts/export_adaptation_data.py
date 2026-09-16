#!/usr/bin/env python3
"""Export verified adaptation measurements into the site's data directory.

Numbers are read programmatically from the research artifacts — never
hand-typed — so the web charts stay traceable to the measurement records.
"""
import hashlib
import json
from pathlib import Path

ART = Path("../iclr2027-mixworld/artifacts")
OUT = Path("./src/data/adaptation-results.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def r3(x):
    return round(x, 3)


# ---------- seen embodiments: transfer SSIM curves ----------
SEEN_SOURCES = [
    ("fixed", "Fixed-base", "rq2_fixed_transfer_ssim.json"),
    ("mobile", "Mobile-base", "rq2_mobile_transfer_ssim.json"),
    ("humanoid", "Humanoid (G1)", "rq2_humanoid_transfer_ssim.json"),
]
seen = []
for key, label, fname in SEEN_SOURCES:
    p = ART / fname
    d = json.loads(p.read_text())
    steps = d["checkpoint_steps"]
    last = steps[-1]
    curves = d["curves"]
    mix = curves["MiX-World"]
    wan = curves["Target-only"]  # Wan base fine-tuned on target data only
    points = [
        {
            "pct": round(100.0 * st / last, 1),
            "step": st,
            "mix": r3(v),
            "wan": r3(w),
        }
        for st, v, w in zip(steps, mix, wan)
    ]
    seen.append(
        {
            "id": key,
            "label": label,
            "task": d["task"],
            "validation_episodes": d["validation_episodes"],
            "metric": d["metric"],
            "points": points,
        }
    )

# ---------- unseen embodiments: matched-budget gains ----------
rows = json.loads((ART / "rq2_final_20260914" / "measured_rows.json").read_text())
BODIES = [
    ("franka_dual", "Dual-arm Franka", "Dual-arm Franka", "RoboTwin 2.0", "#0c797a"),
    ("ur5_dual", "Dual-arm UR5", "Dual-arm UR5", "RoboTwin 2.0", "#9b5ead"),
    ("franka_single", "Single-arm Franka", "LIBERO Franka", "LIBERO", "#5b728c"),
]
unseen = []
for key, label, body_name, env, color in BODIES:
    sub = [r for r in rows if r["body"] == body_name]
    # keep only budgets where BOTH initializations were measured (matched pairs)
    budgets = sorted(
        set((r["demos"], r["updates"]) for r in sub if r["demos"] > 0)
        & set((r["demos"], r["updates"]) for r in sub if r["method"] == "Wan")
        & set((r["demos"], r["updates"]) for r in sub if r["method"] == "MiX-World")
    )
    items = []
    for dm, up in budgets:
        w = next(r for r in sub if r["demos"] == dm and r["updates"] == up and r["method"] == "Wan")
        m = next(r for r in sub if r["demos"] == dm and r["updates"] == up and r["method"] == "MiX-World")
        items.append(
            {
                "demos": dm,
                "updates": up,
                "wan_psnr": round(w["psnr"], 2),
                "mix_psnr": round(m["psnr"], 2),
                "gain": round(m["psnr"] - w["psnr"], 2),
                "one_shot": dm == 1 and up == 100,
            }
        )
    unseen.append({"id": key, "label": label, "env": env, "color": color, "budgets": items})

out = {
    "provenance": {
        "generated_by": "scripts/export_adaptation_data.py",
        "sources": {
            "seen_curves": {
                str(ART / f): sha256(ART / f) for _, _, f in SEEN_SOURCES
            },
            "unseen_rows": {
                str(ART / "rq2_final_20260914/measured_rows.json"): sha256(
                    ART / "rq2_final_20260914/measured_rows.json"
                )
            },
        },
        "note": "All values read programmatically from measurement artifacts; see claims.json for approval state.",
    },
    "seen": seen,
    "unseen": unseen,
}
OUT.write_text(json.dumps(out, indent=2))
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
print("seen:", [(s['id'], len(s['points'])) for s in seen])
print("unseen:", [(u['id'], len(u['budgets'])) for u in unseen])
