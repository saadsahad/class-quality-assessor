"""Experimental: calibrate the facts-judge (qa/facts_pipeline.py) on the same 10 labelled recordings,
side by side with main's saved results. Does not touch calib_out/results.json (main's cache).

    python calibrate_facts.py [--model M]
"""
import argparse, csv, json, os, zipfile
from collections import Counter

from calibrate import load_recordings  # reuse: VTT/mp4 pairing from the zip, nothing extracted
from qa.config import JUDGE_MODEL
from qa.facts_pipeline import assess_facts_vtt

GRADES = ["Poor", "Average", "Good", "Excellent"]
OUT = "calib_out"


def run_once(rec, model):
    r = assess_facts_vtt(rec["vtt"], model=model, media_duration_s=rec["duration"])
    f = r["facts"]
    return {
        "scores": r["scores"],
        "weighted": r["rating"]["weighted"],
        "grade": r["rating"]["grade"],
        "override_reason": r["rating"].get("override_reason"),
        "na": r["rating"].get("na", []),
        "cost": r["cost_usd"],
        # counts only, for the audit trail - no quotes, no names
        "facts": {
            "minutes_to_content": f.minutes_to_content, "greeted_by_name": f.greeted_by_name,
            "check_in_questions": f.check_in_questions, "late_joiner_present": f.late_joiner_present,
            "late_joiner_welcome": f.late_joiner_welcome, "addressed_by_name": f.addressed_by_name,
            "named_child_questions": f.named_child_questions, "specific_praise": f.specific_praise,
            "generic_praise": f.generic_praise, "flat_acknowledgements": f.flat_acknowledgements,
            "recap": f.recap, "homework_set": f.homework_set, "goodbye": f.goodbye,
            "tutor_talk_minutes": f.tutor_talk_minutes, "media_minutes": f.media_minutes,
        },
        "dropped": f.notes["dropped"],
    }


def metrics(pairs):
    ex = sum(t == p for t, p in pairs)
    wi = sum(abs(GRADES.index(t) - GRADES.index(p)) <= 1 for t, p in pairs)
    two_plus = [t for t, p in pairs if abs(GRADES.index(t) - GRADES.index(p)) >= 2]
    return ex, wi, two_plus, Counter(pairs)


def print_confusion(cm):
    print("  true \\ pred    " + "".join(f"{g[:7]:>9}" for g in GRADES))
    for t in GRADES:
        print(f"  {t:12s}  " + "".join(f"{cm.get((t, p), 0):>9}" for p in GRADES))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=JUDGE_MODEL)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    res_path = os.path.join(OUT, "results_facts.json")
    results = json.load(open(res_path)) if os.path.exists(res_path) else {}
    labels = list(csv.DictReader(open(os.path.join(OUT, "labels.csv"))))
    lab_by_rid = {f"{r['batch']}-{r['date']}": r["grade"] for r in labels}
    import glob, os as _os

    zpath = glob.glob(_os.path.expanduser("~/Documents/humaniti-data/*.zip"))[0]
    with zipfile.ZipFile(zpath) as z:
        recs = load_recordings(z, labels)

    def save():
        json.dump(results, open(res_path, "w"), indent=1)

    for rid, rec in recs.items():
        key = f"{rid}|{args.model}"
        if key in results.get("runs", {}):
            continue
        try:
            results.setdefault("runs", {})[key] = run_once(rec, args.model)
        except Exception as e:  # messages may contain transcript text: type only
            print(f"{rid}: FAILED {type(e).__name__}: {e}", flush=True)
            continue
        r = results["runs"][key]
        print(f"{rid:17s} label={lab_by_rid[rid]:9s} computed={r['grade']} ({r['weighted']})  ${r['cost']:.3f}", flush=True)
        save()

    runs = results.get("runs", {})
    done = {rid: runs[f"{rid}|{args.model}"] for rid in recs if f"{rid}|{args.model}" in runs}
    total_cost = sum(r["cost"] for r in done.values())

    # side by side with main's saved results (same model, same recordings)
    main_path = os.path.join(OUT, "results.json")
    main_results = json.load(open(main_path))["runs"] if os.path.exists(main_path) else {}

    print(f"\n== Facts judge vs main, {args.model} (in-sample)")
    print(f"{'recording':17s} {'label':9s} | {'main (shipped)':>18s} | {'facts judge':>14s}")
    facts_pairs, main_pairs = [], []
    for rid in sorted(recs):
        lab = lab_by_rid[rid]
        mk = f"{rid}|{args.model}"
        main_grade = main_results[mk][0]["grade"] if mk in main_results else None
        fr = done.get(rid)
        facts_grade = fr["grade"] if fr else None
        if main_grade:
            main_pairs.append((lab, main_grade))
        if facts_grade:
            facts_pairs.append((lab, facts_grade))
        override = f" [{fr['override_reason'][:40]}...]" if fr and fr.get("override_reason") else ""
        print(f"{rid:17s} {lab:9s} | {main_grade or '-':>14s}   | {facts_grade or '-':>10s}{override}")

    for name, pairs in (("Main (shipped: rule-based, cut 3.0)", main_pairs), ("Facts judge", facts_pairs)):
        ex, wi, two_plus, cm = metrics(pairs)
        poor_ok = any(t == "Poor" and p == "Poor" for t, p in pairs)
        avg_ok = any(t == "Average" and p == "Average" for t, p in pairs)
        n_poor_ok = sum(1 for t, p in pairs if t == "Poor" and p == "Poor")
        print(f"\n== {name}: exact {ex}/{len(pairs)}  within-one {wi}/{len(pairs)}  2+ off: {two_plus or 'none'}  "
              f"Poor correct: {n_poor_ok}/4  Average correct at least once: {avg_ok}")
        print_confusion(cm)

    print(f"\n== Facts judge total cost: ${total_cost:.2f} over {len(done)} calls")


if __name__ == "__main__":
    main()
