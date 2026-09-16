#!/usr/bin/env python3
"""Locate left/right end-effector (gripper) pixel positions in the Fig-4
fixed-base bimanual videos and export them for the on-site trajectory panel.

Owner directive 2026-09-16: the action-condition panel must show where the
end effectors actually ARE in the video frames (frame-accurate xy), not the
commanded robot-base displacements exported previously by
export_action_trajectories.py. Each condition video is analysed
independently, so generated footage that deviates from the commanded
actions is still plotted truthfully.

Method (deterministic, classical CV - no manual keyframes):
  1. Pool a temporal median over the four moving-gripper condition videos;
     static scene (table, background) survives, grippers do not.
  2. From that median, threshold the bright table surface into a polygon and
     collect pixels that are dark in every pooled frame (table-front box,
     edge cable) as a static-dark mask. Both masks remove non-gripper
     clutter before matching.
  3. Per frame: dark blobs inside the table polygon and outside the
     static-dark mask are matched to the two grippers by nearest prediction
     (constant-velocity model). When both grippers touch (sock folding) they
     form one component; k-means (k=2) seeded at the predictions splits it.
     Identity is carried through time, so conditions where the arms swap
     sides (xy-inverted) stay correctly labelled.
  4. Centroids are lightly median-filtered (detection jitter only) and
     exported in web-frame pixel coordinates.

The site video is the source video cropped: source[72:288] of 384x288 ->
384x216 (verified against public/media/actions/original.mp4). Coordinates
below are web-frame pixels, origin top-left, x right, y down.

Source: ~/Downloads/MiXWorld_网站素材交接_20260915/01_fig04_fixed_socks_action
        (read-only originals; outputs are new JSON files under public/media).
"""
import json
import os

import cv2
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

SRC = os.path.expanduser(
    "~/Downloads/MiXWorld_网站素材交接_20260915/01_fig04_fixed_socks_action"
)
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "media", "actions")

CONDITIONS = {
    "recorded": "original",
    "hold_right": "right_held",
    "xy_inverted": "xy_inverted",
    "hold_both": "both_held",
    "reverse_generated_end": "time_reversed",
}
# owner directive 2026-09-15: xy_inverted is presented for the first 16 s only
DURATION_CAP_S = {"xy_inverted": 16.0}

FPS = 10
CROP_Y = 72          # web frame = source frame rows [CROP_Y : CROP_Y + 216]
WEB_W, WEB_H = 384, 216

DARK_THR = 65        # grippers are matte black (gray ~15-45); table ~140-170,
                     # cast shadows mostly 60-100 and get cut here plus by the
                     # thick-core weighting in grip_point()
BRIGHT_THR = 110     # table surface vs dark floor / background
MIN_BLOB_AREA = 250  # px at 384x216; cables/shadows stay below
MAX_BLOB_AREA = 26000
MEDIAN_STEP = 3      # frame stride when pooling the scene median
MAX_MATCH_DIST = 60.0  # px gate for associating a blob to an arm prediction
REACQUIRE_MAX = 260.0  # px; gate ceiling while an arm is lost
OUTWARD_BIAS = 0.35    # px score discount per px of distance from the base corner
AREA_MATCH_FRAC = 0.3  # blob must be >= this fraction of the arm's reference area
SMALL_AREA_PENALTY = 140.0  # px score penalty scaled by area deficit below 0.55*ref
REF_CAP = 6500.0       # px; reference-area update cap (single-gripper scale)
PAIR_AREA_FRAC = 1.35  # blob/ref above this counts as both claws merged
FUSED_AREA_FRAC = 1.15  # blob/ref above this means claw fused with arm parts
DEEP_THR = 45          # near-black core; shadow-only blobs lack these pixels
MIN_DEEP_CORE = 60     # px of near-black core required in a blob
LOCAL_RADIUS = 30.0    # px; neighbourhood of a DT core used for its centroid
PAIR_MAX_STEP = 12.0   # px/frame clamp while claws are interlocked
MAX_STEP = 24.0        # px/frame; larger jumps are rejected as implausible
SMOOTH_WINDOW = 5      # median filter window over time (detection jitter only)
ENTRY_CORNER = {"left": (0.0, float(WEB_H)), "right": (float(WEB_W), float(WEB_H))}


def read_web_frames(path):
    cap = cv2.VideoCapture(path)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f[CROP_Y:CROP_Y + WEB_H])
    cap.release()
    return frames


def build_scene_model(moving_frames):
    """Table polygon + always-dark static clutter from the pooled median."""
    med = np.median(np.stack(moving_frames), axis=0).astype(np.uint8)
    gray = cv2.cvtColor(med, cv2.COLOR_BGR2GRAY)

    bright = (gray >= BRIGHT_THR).astype(np.uint8)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bright, 8)
    table = (lab == 1 + int(np.argmax(stats[1:, 4]))).astype(np.uint8)
    # fill internal holes (dark objects lying on the table)
    ff = table.copy()
    mask = np.zeros((WEB_H + 2, WEB_W + 2), np.uint8)
    cv2.floodFill(ff, mask, (0, 0), 1)
    table = table | (1 - ff)
    table = cv2.morphologyEx(table, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))

    contours, _ = cv2.findContours(table, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    poly = max(contours, key=cv2.contourArea)
    poly = cv2.approxPolyDP(poly, 1.5, True).reshape(-1, 2)
    table_mask = np.zeros((WEB_H, WEB_W), np.uint8)
    cv2.fillPoly(table_mask, [poly.astype(np.int32)], 255)

    static_dark = np.ones((WEB_H, WEB_W), np.uint8)
    for f in moving_frames:
        static_dark &= (cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) < DARK_THR).astype(np.uint8)
    static_dark = cv2.dilate(static_dark, np.ones((3, 3), np.uint8))
    static_dark &= table_mask  # clutter outside the table is cut by the polygon

    return table_mask, static_dark, poly


def dark_mask(frame, table_mask, static_dark):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dark = ((gray < DARK_THR).astype(np.uint8) * 255)
    dark = cv2.bitwise_and(dark, table_mask)
    cv2.bitwise_and(dark, 255 - static_dark, dst=dark)
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return dark, gray


def detect_blobs(dark, dist_tf, gray):
    n, lab, stats, cent = cv2.connectedComponentsWithStats(dark, 8)
    blobs = []
    for i in range(1, n):
        area = int(stats[i, 4])
        if area < MIN_BLOB_AREA or area > MAX_BLOB_AREA:
            continue
        mask = lab == i
        # cast shadows are grey (>=DEEP_THR); only true objects contain a
        # core of near-black pixels, so shadow-only blobs are discarded
        if int(((gray < DEEP_THR) & mask).sum()) < MIN_DEEP_CORE:
            continue
        gx, gy = grip_point(mask, dist_tf)
        x, y, w, h = (int(v) for v in stats[i, :4])
        blobs.append({"gx": gx, "gy": gy,
                      "cx": float(cent[i][0]), "cy": float(cent[i][1]),
                      "area": area, "mask": mask,
                      "bbox": (x, y, x + w, y + h)})
    return blobs


def grip_point(blob_mask, dist_tf):
    """Position estimate biased to the blob's thick core (the gripper body).

    Raw centroids are dragged onto cast shadows: they are dark enough to join
    the component but are thin sheets on the table. Weighting pixels by the
    squared distance-transform value (zeroed below a fraction of the blob's
    maximum) keeps the estimate on the gripper itself.
    """
    dt = dist_tf[blob_mask]
    w = np.where(dt >= max(2.5, 0.45 * dt.max()), dt * dt, 0.0)
    ys, xs = np.nonzero(blob_mask)
    wsum = w.sum()
    if wsum <= 0:
        return float(xs.mean()), float(ys.mean())
    return float((xs * w).sum() / wsum), float((ys * w).sum() / wsum)


def chain_end_point(blob_mask, dist_tf, corner):
    """End-effector estimate inside a component fused with arm parts.

    When an arm folds, claw, wrist and elbow join into one dark component and
    the thick-core point lands on the elbow disc. The end effector is the
    chain's far end: walk the component from the pixel nearest the arm's
    entry corner (where the forearm enters) and take the thick core of the
    geodesically farthest region. Anything attached beyond the claw - the
    held sock, cast shadows - is thin, so intersecting the far band with the
    distance-transform core keeps the estimate on the claw palm.
    """
    ys, xs = np.nonzero(blob_mask)
    start = int(np.argmin(np.hypot(xs - corner[0], ys - corner[1])))
    n = len(ys)
    neigh = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    cell = {yx: i for i, yx in enumerate(zip(ys.tolist(), xs.tolist()))}
    ind = []
    indptr = [0]
    for y, x in zip(ys.tolist(), xs.tolist()):
        for dy, dx in neigh:
            j = cell.get((y + dy, x + dx))
            if j is not None:
                ind.append(j)
        indptr.append(len(ind))
    data = np.ones(len(ind), np.float32)
    graph = csr_matrix((data, np.asarray(ind, np.int32),
                        np.asarray(indptr, np.int32)), shape=(n, n))
    geo = dijkstra(graph, indices=start)
    dt_all = dist_tf[ys, xs]
    core = dt_all >= max(2.5, 0.45 * dt_all.max())
    if not core.any():
        core = np.ones(n, bool)
    geo_core_max = geo[core].max()
    band = core & (geo >= 0.7 * geo_core_max)
    wgt = dt_all[band] ** 2
    ws = wgt.sum()
    if ws <= 0:
        return float(xs[band].mean()), float(ys[band].mean())
    return float((xs[band] * wgt).sum() / ws), float((ys[band] * wgt).sum() / ws)


def track_video(frames, table_mask, static_dark, init, ref_area):
    """Track both grippers through the frame sequence.

    Per frame, each arm is matched to the blob whose thick-core point is
    nearest to its constant-velocity prediction. Identity survives arms
    crossing sides (xy-inverted) because matching is temporal, not spatial,
    and a Voronoi guard rejects blobs sitting on the other arm's side.

    When both claws interlock over the sock they form one component whose
    single centroid is meaningless. Such frames switch to a pair mode: the
    component's two distance-transform cores (one per claw) are extracted and
    assigned by the left/right order frozen at pair onset — the claws fold
    side by side without swapping in these takes.
    """
    n_frames = len(frames)
    vel = {"left": np.zeros(2), "right": np.zeros(2)}
    pos = {"left": np.asarray(init["left"], float),
           "right": np.asarray(init["right"], float)}
    out = {"left": np.full((n_frames, 2), np.nan), "right": np.full((n_frames, 2), np.nan)}
    # Grippers are consistently thousands of px; cables, the table-front box
    # and leftover clutter are far smaller. Each arm only accepts blobs
    # comparable to its running reference area, which keeps thin clutter from
    # stealing (and then, via the step limit, permanently locking) a target.
    ref_area = {arm: float(ref_area[arm]) for arm in ("left", "right")}
    coast = {arm: 0 for arm in ("left", "right")}
    pair_of = None  # during interlock: {'left': core, 'right': core}

    for t, f in enumerate(frames):
        pos_pred = {k: pos[k] + vel[k] for k in pos}
        dark, gray = dark_mask(f, table_mask, static_dark)
        dist_tf = cv2.distanceTransform(dark, cv2.DIST_L2, 3)
        blobs = detect_blobs(dark, dist_tf, gray)

        # ---- pair mode: one interlocked component holding both claws ----
        # Trigger on area plus bbox containment of both predictions: the
        # component's centroid is meaningless (it is dragged toward whichever
        # arm's dark underside is connected), so distance-to-centroid tests
        # misfire exactly when the claws first touch.
        pair_blob = None
        for b in blobs:
            if b["area"] < PAIR_AREA_FRAC * min(ref_area.values()):
                continue
            bx0, by0, bx1, by1 = b["bbox"]
            inside = all(bx0 - 40 <= pos_pred[a][0] <= bx1 + 40 and
                         by0 - 40 <= pos_pred[a][1] <= by1 + 40
                         for a in ("left", "right"))
            if inside:
                pair_blob = b
                break
        if pair_blob is not None:
            if pair_of is None:
                # freeze which arm owns which side of the interlock; the claws
                # fold side by side without swapping in these takes
                order = sorted(("left", "right"), key=lambda a: pos[a][0])
                pair_of = {"first": order[0], "second": order[1]}
            ys, xs = np.nonzero(pair_blob["mask"])
            x_mid = float(xs.mean())
            for arm in ("left", "right"):
                pred = pos_pred[arm]
                near = np.hypot(xs - pred[0], ys - pred[1]) <= LOCAL_RADIUS
                if near.sum() >= 50:
                    dt_local = dist_tf[ys[near], xs[near]]
                    w = np.where(dt_local >= 0.45 * dt_local.max(), dt_local * dt_local, 0.0)
                    ws = w.sum()
                    new = [float((xs[near] * w).sum() / ws), float((ys[near] * w).sum() / ws)] \
                        if ws > 0 else [pred[0], pred[1]]
                else:
                    new = [pred[0], pred[1]]
                # anti-tunnelling: an estimate may not cross the component's
                # mid-line into the other claw's half
                if pair_of["first"] == arm and new[0] > x_mid + 6:
                    new[0] = x_mid + 6
                if pair_of["second"] == arm and new[0] < x_mid - 6:
                    new[0] = x_mid - 6
                new = np.asarray(new)
                step = float(np.hypot(*(new - pos[arm])))
                if step <= PAIR_MAX_STEP:
                    vel[arm] = 0.5 * vel[arm] + 0.5 * (new - pos[arm])
                    pos[arm] = new
                coast[arm] = 0
                out[arm][t] = pos[arm]
            continue

        # ---- normal mode: independent per-arm matching ----
        pair_of = None
        for arm in ("left", "right"):
            other = "right" if arm == "left" else "left"
            corner = ENTRY_CORNER[arm]
            pred = pos_pred[arm]
            coast[arm] += 1
            coast_prev = coast[arm]
            # while an arm is temporarily lost, widen the search gate so the
            # claw can be re-acquired once it reappears (still bounded; the
            # other arm is normally claimed by its own nearer prediction)
            gate = min(MAX_MATCH_DIST * (1 + coast[arm] / 12.0), REACQUIRE_MAX)
            best, best_score = None, 1e9
            for b in blobs:
                if b["area"] < AREA_MATCH_FRAC * ref_area[arm]:
                    continue
                d = float(np.hypot(b["gx"] - pred[0], b["gy"] - pred[1]))
                if d > gate:
                    continue
                # a blob nearer to the other arm's prediction belongs to the
                # other arm; never let a target tunnel across like that
                do = float(np.hypot(b["gx"] - pos_pred[other][0], b["gy"] - pos_pred[other][1]))
                if do < d - 5.0:
                    continue
                # among plausible candidates prefer the outward-most one: an
                # arm's dark joints sit between its base corner and the claw,
                # and the claw is always the far end of that chain. Joint and
                # clutter blobs are also systematically smaller than the claw,
                # so shrink their score when their area runs below ~half of
                # the arm's reference area.
                outward = float(np.hypot(b["gx"] - corner[0], b["gy"] - corner[1]))
                deficit = max(0.0, 0.55 - b["area"] / ref_area[arm])
                score = d - OUTWARD_BIAS * outward + SMALL_AREA_PENALTY * deficit / 0.55
                if score < best_score:
                    best, best_score = b, score
            if best is None:
                pos[arm] = pred                      # coast on the model
                vel[arm] *= 0.7
                out[arm][t] = pos[arm]
                continue
            coast[arm] = 0
            # the reference absorbs pair blobs only up to a single-gripper cap
            ref_area[arm] = 0.9 * ref_area[arm] + 0.1 * min(best["area"], REF_CAP)
            if best["area"] >= FUSED_AREA_FRAC * ref_area[arm]:
                # claw fused with arm parts (folded pose): aim at the
                # component's far end along the arm chain instead of its
                # thick-core point, which lands on the elbow disc. The chain
                # end is structurally meaningful, so the step clamp is skipped.
                new_pos = np.asarray(chain_end_point(best["mask"], dist_tf, corner))
                # clamped like any other update: during fast swings motion
                # blur can briefly extend the chain end; the clamp keeps the
                # estimate gliding back with the arm instead of teleporting
                step = float(np.hypot(*(new_pos - pos[arm])))
                if step <= MAX_STEP:
                    vel[arm] = 0.6 * vel[arm] + 0.4 * (new_pos - pos[arm])
                    pos[arm] = new_pos
                out[arm][t] = pos[arm]
                continue
            new = (best["gx"], best["gy"])
            step = float(np.hypot(new[0] - pos[arm][0], new[1] - pos[arm][1]))
            # after a lost phase, accept the re-acquisition jump outright;
            # the clamp only guards against single-frame hijacks while tracked
            max_step = gate if coast_prev >= 10 else MAX_STEP
            if step > max_step:
                # escaping outward (toward the claw, away from the base
                # corner) is the natural recovery from riding an arm joint
                corner_d_old = float(np.hypot(pos[arm][0] - corner[0], pos[arm][1] - corner[1]))
                corner_d_new = float(np.hypot(new[0] - corner[0], new[1] - corner[1]))
                if corner_d_new > corner_d_old + 12.0:
                    max_step = 2.0 * MAX_STEP
            if step <= max_step:
                vel[arm] = 0.6 * vel[arm] + 0.4 * (np.asarray(new) - pos[arm])
                pos[arm] = np.asarray(new)
            else:
                pos[arm] = pred                      # reject implausible jump
                vel[arm] *= 0.7
                coast[arm] = coast_prev              # still lost
            out[arm][t] = pos[arm]

    # median filter over time: kills residual detection jitter without
    # shifting real motion (grippers move slowly relative to the window)
    k = SMOOTH_WINDOW
    for arm in ("left", "right"):
        pad = k // 2
        padded = np.pad(out[arm], ((pad, pad), (0, 0)), mode="edge")
        out[arm] = np.stack(
            [np.median(padded[i:i + k], axis=0) for i in range(n_frames)]
        )
    return out


def render_overlay(frames, traj, path):
    """Debug helper: burn the tracked positions onto the frames."""
    colors = {"left": (255, 163, 77), "right": (82, 171, 255)}  # BGR
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), FPS,
                             (WEB_W, WEB_H))
    for t, f in enumerate(frames):
        img = f.copy()
        for arm in ("left", "right"):
            x, y = traj[arm][t]
            cv2.drawMarker(img, (int(round(x)), int(round(y))), colors[arm],
                           cv2.MARKER_CROSS, 21, 2)
            cv2.circle(img, (int(round(x)), int(round(y))), 7, colors[arm], 2)
            if t > 0:
                px, py = traj[arm][t - 1]
                cv2.line(img, (int(round(px)), int(round(py))),
                         (int(round(x)), int(round(y))), colors[arm], 1)
        writer.write(img)
    writer.release()


def main():
    os.makedirs(OUT, exist_ok=True)
    videos = {c: read_web_frames(f"{SRC}/{c}/prediction_high_full.mp4")
              for c in CONDITIONS}

    pooled = [f for c in ("recorded", "hold_right", "xy_inverted", "reverse_generated_end")
              for f in videos[c][::MEDIAN_STEP]]
    table_mask, static_dark, poly = build_scene_model(pooled)

    # initial poses from each condition's own first frame (arms start clearly
    # separated in every condition — including time_reversed, which begins at
    # the original prediction's final frame; verified against overlays)
    def initial_pose(frame0):
        dark, gray = dark_mask(frame0, table_mask, static_dark)
        dtf = cv2.distanceTransform(dark, cv2.DIST_L2, 3)
        blobs = sorted(detect_blobs(dark, dtf, gray), key=lambda b: -b["area"])[:2]
        assert len(blobs) == 2, f"expected 2 grippers in first frame, got {len(blobs)}"
        blobs.sort(key=lambda b: b["gx"])
        pos = {"left": (blobs[0]["gx"], blobs[0]["gy"]),
               "right": (blobs[1]["gx"], blobs[1]["gy"])}
        area = {"left": blobs[0]["area"], "right": blobs[1]["area"]}
        return pos, area

    import sys

    overlay_dir = None
    if "--overlay" in sys.argv:
        overlay_dir = "/tmp/gripper_debug"
        os.makedirs(overlay_dir, exist_ok=True)
        dbg = np.zeros((WEB_H, WEB_W, 3), np.uint8)
        dbg[table_mask > 0] = (60, 60, 60)
        dbg[static_dark > 0] = (0, 0, 255)
        cv2.polylines(dbg, [poly.astype(np.int32)], True, (0, 255, 0), 1)
        cv2.imwrite(f"{overlay_dir}/scene_model.png", dbg)

    for cond, name in CONDITIONS.items():
        frames = videos[cond]
        if name in DURATION_CAP_S:
            frames = frames[:int(DURATION_CAP_S[name] * FPS) + 1]
        init, ref0 = initial_pose(frames[0])
        traj = track_video(frames, table_mask, static_dark, init, ref0)
        n = len(frames)
        data = {
            "frame": {"width": WEB_W, "height": WEB_H, "crop_y": CROP_Y},
            "t": [round(i / FPS, 2) for i in range(n)],
            "duration_s": round((n - 1) / FPS, 2),
            "left": {"x": traj["left"][:, 0].round(1).tolist(),
                     "y": traj["left"][:, 1].round(1).tolist()},
            "right": {"x": traj["right"][:, 0].round(1).tolist(),
                      "y": traj["right"][:, 1].round(1).tolist()},
            "note": ("gripper centroids located directly in the video frames "
                     "(web-frame px, origin top-left); see "
                     "scripts/track_gripper_positions.py"),
        }
        with open(f"{OUT}/traj_{name}.json", "w") as f:
            json.dump(data, f, separators=(",", ":"))
        print(f"wrote traj_{name}.json ({n} frames)")
        if overlay_dir:
            render_overlay(frames, traj, f"{overlay_dir}/{name}.mp4")


if __name__ == "__main__":
    main()
