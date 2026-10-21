"""Calibrate on the labelled recordings. VTTs and mp4 headers are read from the zip in memory; nothing is
extracted. Only scores, grades and costs are written to calib_out/ (gitignored): no quotes, rationales or names.

    python calibrate.py [--model M] [--stability B491-2026-06-29 B558-2026-09-05 B516-2026-09-03]
"""
import argparse, csv, glob, itertools, json, os, statistics, struct, sys, zipfile
from collections import Counter

from qa.config import JUDGE_MODEL
from qa.ingest import parse_vtt
from qa.pipeline import assess_vtt
from qa.rubric import CRITERIA, CUTS
from qa.score import compute_rating, grade_for

GRADES = ["Poor", "Average", "Good", "Excellent"]
OUT = "calib_out"
DEFAULT_STABILITY = ["B491-2026-06-29", "B558-2026-09-05", "B516-2026-09-03"]


def mp4_duration(f):
    f.seek(0, 2); size = f.tell(); pos = 0
    while pos < size:
        f.seek(pos); hdr = f.read(16)
        sz, typ = struct.unpack(">I4s", hdr[:8]); off = 8
        if sz == 1: sz = struct.unpack(">Q", hdr[8:16])[0]; off = 16
        elif sz == 0: sz = size - pos
        if typ == b"moov":
            f.seek(pos + off); data = f.read(4096); i = data.find(b"mvhd"); v = data[i + 4]
            ts, dur = struct.unpack(">IQ", data[i + 24:i + 36]) if v == 1 else struct.unpack(">II", data[i + 16:i + 24])
            return dur / ts
        pos += sz


def load_recordings(z, labels):
    """Pair each labelled (batch, date) with its mp4 duration and the VTT whose end best matches it."""
    names = z.namelist()
    out = {}
    for row in labels:
        rid = f"{row['batch']}-{row['date']}"
        mp4 = [n for n in names if n.endswith(".mp4") and os.path.basename(n).startswith(row["batch"]) and row["date"] in n]
        assert len(mp4) == 1, f"{rid}: {len(mp4)} mp4 matches"
        with z.open(mp4[0]) as f:
            dur = mp4_duration(f)
        best = None
        for v in [n for n in names if n.endswith(".vtt") and os.path.basename(n).startswith(row["batch"])]:
            text = z.read(v).decode("utf-8", "replace")
            gap = abs(dur - parse_vtt(text)[-1].end)
            if best is None or gap < best[0]:
                best = (gap, text)
        out[rid] = {"grade": row["grade"], "duration": dur, "vtt": best[1]}
    return out


def run_once(rec, model):
    r = assess_vtt(rec["vtt"], model=model, media_duration_s=rec["duration"])
    return {
        "scores": {k: v["score"] for k, v in r["criteria"].items()},
        "weighted": r["rating"]["weighted"],
        "grade": r["rating"]["grade"],
        "na": r["rating"].get("na", []),
        "notes": {k: v["note"] for k, v in r["criteria"].items() if v["note"] != "ok"},
        "cross_check": r["model_cross_check"]["rating"],
        "coverage": {k: r["coverage"][k] for k in ("start", "end")},
        "cost": r["cost_usd"],
    }


def tune_cuts(items):
    """items: [(weighted, grade)]. Grid over midpoints; maximise exact, then within-one, then stay near the defaults."""
    ws = sorted({w for w, _ in items})
    cand = [ws[0] - 0.01] + [(a + b) / 2 for a, b in zip(ws, ws[1:])] + [ws[-1] + 0.01]
    default = [c for c, _ in CUTS]
    best = None
    for cuts in itertools.combinations(cand, 3):
        pred = [GRADES.index(grade_for(w, list(zip(cuts, GRADES)))) for w, _ in items]
        true = [GRADES.index(g) for _, g in items]
        exact = sum(p == t for p, t in zip(pred, true))
        within = sum(abs(p - t) <= 1 for p, t in zip(pred, true))
        key = (exact, within, -sum(abs(a - b) for a, b in zip(cuts, default)))
        if best is None or key > best[0]:
            best = (key, cuts)
    return list(zip(best[1], GRADES))


def metrics(pairs):
    exact = sum(p == t for t, p in pairs)
    within = sum(abs(GRADES.index(p) - GRADES.index(t)) <= 1 for t, p in pairs)
    cm = Counter(pairs)
    return exact, within, cm


def print_confusion(cm):
    print("  true \\ pred    " + "".join(f"{g[:7]:>9}" for g in GRADES))
    for t in GRADES:
        print(f"  {t:12s}  " + "".join(f"{cm.get((t, p), 0):>9}" for p in GRADES))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=JUDGE_MODEL)
    ap.add_argument("--stability", nargs="*", default=DEFAULT_STABILITY)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    res_path = os.path.join(OUT, "results.json")
    results = json.load(open(res_path)) if os.path.exists(res_path) else {}
    labels = list(csv.DictReader(open(os.path.join(OUT, "labels.csv"))))
    zpath = glob.glob(os.path.expanduser("~/Documents/humaniti-data/*.zip"))[0]
    with zipfile.ZipFile(zpath) as z:
        recs = load_recordings(z, labels)

    def save():
        json.dump(results, open(res_path, "w"), indent=1)

    for rid, rec in recs.items():
        key = f"{rid}|{args.model}"
        if key in results.get("runs", {}):
            continue
        try:
            results.setdefault("runs", {})[key] = [run_once(rec, args.model)]
        except Exception as e:  # messages may contain transcript text: type only
            print(f"{rid}: FAILED {type(e).__name__}", flush=True)
            continue
        r = results["runs"][key][0]
        print(f"{rid:17s} label={rec['grade']:9s} computed={r['grade']} ({r['weighted']})  ${r['cost']:.3f}", flush=True)
        save()

    # stability: one extra run on a few recordings; a third only if any criterion moves by more than 1
    for rid in args.stability:
        key = f"{rid}|{args.model}"
        runs = results.get("runs", {}).get(key)
        if not runs:
            continue
        if len(runs) == 1:
            runs.append(run_once(recs[rid], args.model)); save()
        a, b = runs[0], runs[1]
        drift = max((abs(a["scores"][k] - b["scores"][k]) for k in a["scores"] if a["scores"][k] is not None and b["scores"][k] is not None), default=0)
        if drift > 1 and len(runs) == 2:
            runs.append(run_once(recs[rid], args.model)); save()

    runs = results["runs"]
    done = {rid: runs[f"{rid}|{args.model}"] for rid in recs if f"{rid}|{args.model}" in runs}
    total_cost = sum(r["cost"] for rs in done.values() for r in rs)

    print(f"\n== Per recording ({args.model}), first run")
    items = []
    for rid, rs in done.items():
        r = rs[0]
        if r["weighted"] is None:
            print(f"{rid}: no grade ({r['notes']})"); continue
        items.append((rid, recs[rid]["grade"], r["weighted"], r["grade"]))
        print(f"{rid:17s} {recs[rid]['grade']:9s} -> {r['grade']:9s} w={r['weighted']:.2f}  cross-check={r['cross_check']:9s} N/A={r['na']}")

    print("\n== Mean weighted score by label")
    for g in GRADES:
        w = [x[2] for x in items if x[1] == g]
        if w:
            print(f"  {g:9s} n={len(w)} mean={statistics.mean(w):.2f}  values={[round(v, 2) for v in sorted(w)]}")

    print(f"\n== Default cuts {[c for c, _ in CUTS]} (not tuned)")
    ex, wi, cm = metrics([(t, p) for _, t, _, p in items])
    print(f"  exact {ex}/{len(items)}   within-one {wi}/{len(items)}")
    print_confusion(cm)

    print("\n== Leave-one-out (cuts tuned on the other recordings only)")
    loo = []
    for i, (rid, t, w, _) in enumerate(items):
        cuts = tune_cuts([(x[2], x[1]) for j, x in enumerate(items) if j != i])
        loo.append((t, grade_for(w, cuts)))
    ex, wi, cm = metrics(loo)
    print(f"  exact {ex}/{len(items)}   within-one {wi}/{len(items)}")
    print_confusion(cm)
    print("  cuts tuned on all (for reference only, not applied):", [round(c, 2) for c, _ in tune_cuts([(x[2], x[1]) for x in items])])

    print("\n== Stability")
    for rid in args.stability:
        rs = done.get(rid)
        if not rs or len(rs) < 2:
            continue
        a, b = rs[0], rs[1]
        diffs = {k: (a["scores"][k], b["scores"][k]) for k in a["scores"] if a["scores"][k] != b["scores"][k]}
        d = max((abs(x - y) for x, y in diffs.values() if x is not None and y is not None), default=0)
        line = f"  {rid}: grades {a['grade']}/{b['grade']}  weighted {a['weighted']}/{b['weighted']}  criteria that differ: {diffs or 'none'}  max drift {d}"
        if len(rs) == 3:
            med = {k: statistics.median([r["scores"][k] for r in rs if r["scores"][k] is not None] or [0]) for k in a["scores"]}
            med = {k: (int(v) if v else None) for k, v in med.items()}
            line += f"  -> third run, median grade {compute_rating(med)['grade']}"
        print(line)

    print(f"\n== Total cost: ${total_cost:.2f} over {sum(len(rs) for rs in done.values())} judge runs")


if __name__ == "__main__":
    main()
