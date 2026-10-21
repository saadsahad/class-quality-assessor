"""8x8 class quality assessor. Password-gated; nothing is stored, results are masked, temp files are deleted."""
import hmac
import os
import time

import streamlit as st

# Streamlit Community Cloud provides secrets through st.secrets (and, for top-level keys, the environment).
# Copy anything we need into the environment BEFORE the qa modules read their settings. Values are never printed.
for _key in ("ANTHROPIC_API_KEY", "JUDGE_MODEL", "WHISPER_BUDGET_MIN", "WHISPER_MODEL", "WHISPER_THREADS"):
    if not os.environ.get(_key):
        try:
            _val = st.secrets.get(_key)
        except Exception:  # no secrets file configured
            _val = None
        if _val:
            os.environ[_key] = str(_val)

from qa.config import JUDGE_MODEL, MAX_RUN_USD
from qa.judge import CostGuardError
from qa.rubric import CRITERIA
from qa.service import assess_upload

st.set_page_config(page_title="Class quality assessor", page_icon="♟️", layout="centered")

LABELS = {
    "rapport_start": "Rapport at the start",
    "welcome_new": "Welcoming new joiners",
    "warmth_energy": "Warmth and energy",
    "fair_turns": "Fair turns for every child",
    "lesson_close": "Lesson wrap-up",
    "checklist": "Questions and lesson flow",
}


def _configured_password() -> str | None:
    pw = os.environ.get("APP_PASSWORD")
    if pw:
        return pw
    try:
        return st.secrets.get("APP_PASSWORD")
    except Exception:
        return None


def gate():
    """Nothing but the password box renders until this passes."""
    if st.session_state.get("authed"):
        return
    pw = _configured_password()
    if not pw:
        st.error("This app is not configured (APP_PASSWORD is missing).")
        st.stop()
    entered = st.text_input("Password", type="password")
    if entered:
        if hmac.compare_digest(entered.encode(), pw.encode()):
            st.session_state["authed"] = True
            st.rerun()
        time.sleep(1)  # slow down guessing
        st.error("Incorrect password.")
    st.stop()


def render(r: dict):
    rating = r["rating"]
    if rating["grade"] is None:
        st.subheader("Not enough evidence to rate this class")
    else:
        b = rating.get("borderline")
        st.subheader(f"{rating['grade']}" + (f" (borderline {b[0]} / {b[1]})" if b else ""))
        st.caption(
            f"Weighted score {rating['weighted']} of 4. "
            + ("Within 0.25 of a grade boundary, so treat the grade as uncertain. " if b else "")
            + "Calculated in code from the criterion scores below, not taken from the model's own verdict."
        )

    t = r["transcript"]
    if t["source"] == "whisper":
        st.info(
            "Transcribed automatically from the recording (no Zoom transcript): speakers are not identified "
            "and names or chess terms may be misheard. A Zoom transcript is faster and more accurate."
        )
        if t["partial"]:
            st.warning(
                f"Partial transcript: about {t['covered_pct']}% of the class was transcribed (the opening, the closing and "
                f"sampled parts in between) to stay within the {round(t['budget_s'] / 60)} minute time budget. "
                "Criteria that need the whole class are less certain."
            )
        if t.get("language") and t["language"] != "en":
            st.warning(f"The detected language is '{t['language']}', so evidence quotes are in that language and the rating is less reliable.")

    cov = r["coverage"]
    if cov["start"] == "absent" or cov["end"] == "absent":
        st.warning(f"The transcript appears to miss the class opening ({cov['start']}) or ending ({cov['end']}); affected criteria are not scored.")
    if cov["media_s"] is None:
        st.info("No recording length was available, so missing openings or endings could not be ruled out.")

    st.markdown("#### Criteria")
    for name, c in r["criteria"].items():
        score = "N/A" if c["score"] is None else f"{c['score']} / 4"
        tag = "" if c["in_grade"] else "  ·  shown for information, not used in the grade"
        with st.expander(f"{LABELS[name]}: {score}{tag}"):
            if c["note"] != "ok":
                st.caption(c["note"])
            if c["thin_evidence"]:
                st.caption("⚠️ Thin evidence: fewer than 2 verified quotes support this score.")
            st.write(c["rationale"])
            for e in c["evidence"]:
                who = f", {e['speaker']}" if t["has_speakers"] else ""
                st.markdown(f"> {e['quote']}  \n> <small>{int(e['ts'] // 60):02d}:{int(e['ts'] % 60):02d}{who}</small>", unsafe_allow_html=True)
            st.caption(f"{c['verified_count']} quote(s) verified, {c['dropped']} discarded (could not be confirmed in the transcript).")

    with st.expander("Class signals"):
        sig = r["signals"]
        if sig:
            table = (
                "| Signal | Value |\n|---|---|\n"
                f"| Class length | {sig.get('duration_min', '–')} min |\n"
                f"| Tutor talk share | {round(sig['most_talkative_share'] * 100) if sig.get('most_talkative_share') is not None else '–'}% |\n"
                f"| Words per minute | {sig.get('words_per_min', '–')} |\n"
                f"| Questions per 10 min | {sig.get('questions_per_10min', '–')} |\n"
                f"| Quiet time | {sig.get('dead_air_pct', '–')}% |\n"
                f"| Speakers heard | {sig.get('distinct_speaker_labels', '–')} |\n"
            )
            st.markdown(table)
        elif t["source"] == "whisper":
            st.caption("These signals need speaker labels, which automatic transcripts don't have.")
        if r["media_segments"]:
            st.caption("Played media (excluded from evidence): " + ", ".join(f"{m['start']}–{m['end']}" for m in r["media_segments"]))
    st.caption(
        f"Model's own overall view (not used for the grade): {r['model_cross_check']['rating']}.  \n"
        f"Cost of this run: ${r['cost_usd']:.3f} (limit ${MAX_RUN_USD:.2f}) with {JUDGE_MODEL}."
    )


gate()

st.title("Class quality assessor")
st.caption(
    "Upload a Zoom class transcript to get a Poor / Average / Good / Excellent rating with checked evidence. "
    "Nothing is stored. Uploaded files are processed in memory and in a temporary folder that is deleted, "
    "names are masked in the results, and only transcript text goes to the model."
)

vtt = st.file_uploader("Zoom transcript (.vtt). Recommended: faster and more accurate", type=["vtt"])
media = st.file_uploader(
    "Recording (audio or video). With a transcript it is only used for the class length; without one it is transcribed here, which takes several minutes.",
    type=["mp4", "m4a", "mp3", "wav", "mov", "webm", "mkv"],
)
link = st.text_input(
    "Or paste a Google Drive or direct link to the recording (used only when no file is uploaded)",
    help="For Google Drive, set sharing to 'Anyone with the link'. The file is streamed to a temporary file and deleted afterwards.",
    disabled=bool(media),
)
n_students = st.number_input("Number of students (optional, 0 = unknown)", min_value=0, max_value=12, value=0)

if (media or link.strip()) and not vtt:
    st.info("No transcript uploaded: the recording will be transcribed here. A Zoom transcript (.vtt) is faster and more accurate if you have one.")

if st.button("Assess class", type="primary", disabled=not (vtt or media or link.strip())):
    bar = st.progress(0.0, text="Starting") if not vtt else None
    try:
        with st.spinner("Reading the class and checking the evidence..."):
            result = assess_upload(
                vtt.getvalue() if vtt else None,
                media if media else (link.strip() or None),  # the upload is streamed to disk, not copied in memory
                media.name if media else "",
                int(n_students),
                progress=(lambda f, msg: bar.progress(f, text=msg)) if bar else None,
            )
        if bar:
            bar.empty()
        render(result)
    except CostGuardError as e:
        st.error(str(e))
    except ValueError as e:
        st.error(str(e))
    except Exception as e:  # messages can contain transcript text, so show only the type
        st.error(f"Something went wrong ({type(e).__name__}). Nothing was saved.")
