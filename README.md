# 8x8 class quality assessor

Upload a Zoom transcript (`.vtt`) of an 8x8 online chess class for children and get a **Poor / Average / Good / Excellent**
rating with checked evidence. A recording (audio or video) can be added to give the class length, or uploaded on its own
(no transcript), in which case it is transcribed here with faster-whisper. The Zoom transcript is faster and more accurate.
For a very large recording, upload the transcript or an audio-only file (an `.m4a` is about a tenth of the size), or paste a link.
Hosted on **Streamlit Community Cloud**, deployed from this repository (see "Hosting" below).
This is a prototype, tested on 10 labelled recordings (see below): treat ratings as a first screen, not a verdict.

## How it works
0. **No transcript?** A 2-minute speed probe measures transcription speed on the server's CPU. If the whole class fits in the time budget (default 10 minutes, `WHISPER_BUDGET_MIN`) it is transcribed in full; otherwise the opening, the closing and evenly spaced windows are transcribed, and the result shows a **partial-transcript banner** with the percentage covered. Automatic transcripts have no speaker labels, so talk-share signals and late-joiner hints are not used.
1. The Zoom transcript is parsed. Speaker labels are devices, so they are replaced by `S1, S2...` (S1 talks most) before anything leaves the process.
2. One Claude call scores the criteria below (1 to 4, or N/A) and returns verbatim quotes with timestamps, plus any stretches of played media (e.g. YouTube) so these are never quoted as the tutor — or three calls, scored by the per-criterion median, when the weighted score lands within 0.35 of a grade boundary. A core-criteria rule can then override the weighted grade (see "Grading rule" below).
3. Every quote is re-checked against the transcript within ±30 s; anything that cannot be confirmed is dropped. A score of 3 or 4 with no verified quote is capped at 2.
4. The rating is **computed in code** from the criterion scores. The model's own overall view is shown only as a cross-check.
5. A weighted score within 0.25 of a grade boundary is shown as **borderline** between the two grades.
6. Whether the class opening and ending are in the transcript is decided from timestamps versus the recording length plus greeting/goodbye talk; a part is marked N/A only if the data shows it is missing.

| Criterion | Weight |
|---|---|
| Rapport at the start | 0.22 |
| Welcoming new joiners | 0.13 |
| Warmth and energy | 0.25 |
| Lesson wrap-up | 0.15 |
| Questions and lesson flow | 0.05 |
| Fair turns for every child | report-only (not in the grade) |

Weights are renormalised over whatever criteria were actually scored (N/A criteria are left out, not treated as a 0).

Grade boundaries on the weighted score (1 to 4): Poor below 2.0, Average below 2.75, Good below 3.0, otherwise Excellent.
Poor and Average are the original locked cuts; the Excellent cut was moved from 3.4 to 3.0 post-hoc — see "Excellent cut-point (post-hoc)" below. The weights are locked and were **not validated** by calibration (see results); a core-criteria rule can also override the grade the weighted score gives (see "Grading rule" below).

## Privacy
- The password screen is the only thing shown until the correct password is entered.
- Uploads and downloaded links are handled in a temporary folder that is deleted afterwards (even on errors); an upload also sits in server memory until the browser session ends. Nothing is stored, cached or logged; the original file name is never written to disk.
- A pasted link is fetched by the server: only http(s) links to public addresses are accepted (private, local and link-local addresses are refused, including after redirects), downloads are capped at 2 GB, and Google Drive links use the Drive downloader. The file must be shared as "Anyone with the link".
- Names are masked (`[Name A]`) in everything displayed — **best effort, not guaranteed**: known names (from device labels and the judge's own list), close spelling variants of them, and names used in direct address (e.g. "Hi Dhruv,") are masked, but an unusual misspelling that is neither reported by the judge nor caught by fuzzy matching, in a position that isn't direct address, can slip through. Only transcript text goes to the model, with device labels pseudonymised.
- **XSRF protection is turned off** (`enableXsrfProtection = false` in `.streamlit/config.toml`) so that file uploads work when the app is embedded in a page. The password screen protects the app's pages, but it does not protect Streamlit's upload endpoint, which exists for any visitor and holds a file in memory only until that session ends. Nothing is stored. If uploads fail once deployed, `enableCORS = false` is the next setting to try.
- On Streamlit Community Cloud an uploaded recording is processed on Streamlit's servers, so it leaves your machine. The app is public behind a password; keep the password and API key in the app's secrets, never in the repository.
- Each run is cost-guarded: the worst case (counted input tokens plus the output ceiling) is estimated first and the run is refused above $0.20. The actual cost is shown after every run.

## Hosting on Streamlit Community Cloud
The app is deployed from the public GitHub repository. On [share.streamlit.io](https://share.streamlit.io): **Create app**, then **Yup, I have an app**, then set Repository to this repo, Branch `main`, Main file path `app.py`. Under **Advanced settings** choose Python 3.12 and paste the secrets (TOML, with your own values):

```toml
APP_PASSWORD = "choose-a-password"
ANTHROPIC_API_KEY = "your-key"
# optional: JUDGE_MODEL = "claude-sonnet-5-5", WHISPER_BUDGET_MIN = "10"
```

`packages.txt` installs `ffmpeg` and `requirements.txt` the Python packages. Settings come from `st.secrets` or environment variables.

Things to expect on the free tier (limits quoted from Streamlit's documentation, approximate and subject to change):
- **Memory:** about 2.7 GB at most, shared by the uploaded file (held in memory while the session lasts), the Whisper model and the audio being processed. Very large recordings can crash the app: upload the `.vtt`, or an audio-only file, or paste a link (links are streamed to disk, not memory).
- **CPU:** up to 2 cores, so transcription without a Zoom transcript is slow, and the first run also downloads the Whisper model (about 150 MB). The 2-minute probe measures the real speed and falls back to a partial transcript, with a banner, when the budget would be exceeded.
- **Sleep:** an app with no traffic for 12 hours goes to sleep; the first visitor has to click "Yes, get this app back up!" and wait for it to start. Open the app yourself shortly before a test.
- **Public URL:** anyone with the link sees the password screen; the repository is public too, so it must never contain data, `.env`, `calib_out/` or keys (run `python check_push.py` before every push).

## Live app checks
From testing the deployed app directly (not the offline checks above):
- A 340 MB video upload worked both with a Zoom transcript attached and with no transcript (transcribed on the server).
- A 38-minute class with no transcript took about 5-6 minutes to transcribe on the free tier.
- A direct link to a public `.mp4` was tested and downloaded correctly; that particular recording gave a clean "no speech found" message rather than a crash.
- The wrong-password screen shows nothing else — no title, no uploader, no app content.
- The Google Drive link input has **not** been tested against a live Drive file; `qa/media.py`'s Drive handling is covered only by mocked tests.

## Configuration (app secrets)
| Name | Purpose |
|---|---|
| `APP_PASSWORD` | required; password for the screen |
| `ANTHROPIC_API_KEY` | required; never printed or logged |
| `JUDGE_MODEL` | optional; defaults to `claude-sonnet-5-5` |
| `WHISPER_BUDGET_MIN` | optional; transcription time budget in minutes, default 10 |
| `WHISPER_MODEL` | optional; faster-whisper model, default `base` |

## Calibration results (10 labelled recordings, Sonnet, effort low)
Labels come from the QA notes; "Poor" combines "weak" and "known quality issues". Recordings are identified by batch and date.

**Per recording, original rubric versus the in-sample rescore.** The rescore sets `fair_turns` to report-only and re-weights the remaining criteria; it was run once on the same 10 recordings, so it is **in-sample and not independent evidence**. Grade boundaries are unchanged in both columns.

| Recording | QA label | Original: computed (weighted) | Rescore, fair_turns report-only (in-sample) |
|---|---|---|---|
| B491, 2026-06-29 | Excellent | Good (3.25) | Good (3.06) |
| B472, 2026-08-24 | Excellent | Good (3.14) | Good (3.17) |
| B552, 2026-09-02 | Good | Good (3.31) | Excellent (3.44) |
| B435, 2026-07-25 | Good | Average (2.54) | Average (2.40) |
| B516, 2026-09-03 | Average | Average (2.43) | Average (2.54) |
| B435, 2026-08-28 | Average | Average (2.20) | Average (2.25) |
| B558, 2026-09-05 | Poor | Good (3.06) | Good (2.78) |
| B482, 2026-09-02 | Poor | Average (2.68) | Average (2.57) |
| B392, 2026-09-02 | Poor | Average (2.65) | Average (2.56) |
| B441, 2026-08-26 | Poor | Average (2.59) | Average (2.46) |

| | Exact agreement | Within one grade |
|---|---|---|
| Original rubric | 3 / 10 | 9 / 10 |
| Rescore, fair_turns report-only (in-sample) | 2 / 10 | 9 / 10 |
| Leave-one-out, boundaries tuned on the other 9 (not adopted) | 0 / 10 | 4 / 10 |

Confusion matrices (rows are the QA label):

| Original | Poor | Average | Good | Excellent |
|---|---|---|---|---|
| Poor | 0 | 3 | 1 | 0 |
| Average | 0 | 2 | 0 | 0 |
| Good | 0 | 1 | 1 | 0 |
| Excellent | 0 | 0 | 2 | 0 |

| Rescore (in-sample) | Poor | Average | Good | Excellent |
|---|---|---|---|---|
| Poor | 0 | 3 | 1 | 0 |
| Average | 0 | 2 | 0 | 0 |
| Good | 0 | 1 | 0 | 1 |
| Excellent | 0 | 0 | 2 | 0 |

**Reading these honestly.** Within-one agreement is easy to reach with four grades. The rubric ranks the strongest classes above the rest, but it does not separate **Poor from Average**: mean weighted score by label (original) was Excellent 3.20, Good 2.92, Poor 2.75, Average 2.32. `rapport_start` followed the labels best; `fair_turns` did not (Poor classes averaged 3.25, Average classes 2.00), which is why it is report-only. Making it report-only did not improve exact agreement. With 10 recordings these numbers show direction, not precision.

**Stability (repeat runs on 3 recordings, original rubric).** No grade changed, and no criterion moved by more than 1 point, so the median-of-three rule never triggered. The weighted score still moves by about 0.1 to 0.3, comparable to the gaps between grade means.

| Recording | Weighted, run 1 / run 2 | Criteria that differed |
|---|---|---|
| B491, 2026-06-29 | 3.25 / 3.25 | none |
| B558, 2026-09-05 | 3.06 / 2.80 | rapport_start 3 to 2 |
| B516, 2026-09-03 | 2.43 / 2.30 | welcome_new 3 to 2 |

Calibration cost: $0.64 for 13 Sonnet runs (about $0.03 to $0.07 each).

## Grading rule: weighted average plus a core-criteria override (current)
Calibration above showed a real problem: across all 10 recordings the weighted-average grade **never predicted Poor or Excellent**, only Average or Good. Two free, in-sample checks on the already-saved scores were tried first (no prompt or weight changes, no new API calls):

- **The model's own overall rating** (shown in the app as a cross-check, never used for the grade) does no better: exact 3/10, within-one 9/10, and it also only ever says Average or Good.
- **A rule-based re-grading** of the same saved scores — Poor if a core criterion (rapport at the start, warmth and energy, welcoming new joiners) is 1, or two or more of those three are 2-or-below with none at 4; Excellent if most of them are 4 and none are 2-or-below; otherwise the weighted grade — reached exact 4/10, but flipped one true Average recording to Poor. That one regression meant it did not clear the bar at the time, so it was not adopted yet.

That ruled out a quick fix, so the judge prompt changed instead, in three ways, with the rubric weights and cut-points left exactly as locked:
1. `rapport_start` and `lesson_close` may be marked N/A only when `qa/coverage.py` finds that part of the class genuinely missing from the transcript; otherwise a skipped greeting or an abrupt ending must be scored (as low as 1), not waved through as "not shown". This is enforced in code, not just the prompt: if the judge still returns null when the data is there, the score is set to 1.
2. The full 1-4 scale is used explicitly, with a sharper anchor for warmth and energy (flat "okay, next" acknowledgements score 2; frequent specific praise and humour scores 4), so the judge stops defaulting to the middle.
3. A weighted score within 0.35 of a grade boundary now triggers two more judge runs automatically, scored by the per-criterion median, instead of one noisy call deciding a borderline case.

All 10 recordings were re-run once under the new prompt (Sonnet), and the core-criteria rule was re-checked against the new scores. This time it cleared the revised bar (exact agreement improves, no recording lands two or more grades from its label, and Poor is predicted correctly at least once) and **was adopted**: `qa/score.py` now applies it as an explicit second step after the weighted average, over the same locked weights and cuts. When the rule changes the grade, the result is shown as **borderline between the two grades**, with a one-line reason, e.g. *"Rated Poor by the core-criteria rule: rapport 2, warmth 2, welcoming 2, no strengths at 4. Weighted score 2.25 suggests Average."*

**Say this plainly: the rule trades some Average accuracy for Poor accuracy.** It was chosen because catching a poor class matters more for a QA tool than getting every Average class exactly right, and because the weighted average alone caught none of the Poor-labelled recordings. Concretely: the shipped version calls **both** true-Average recordings (B516, 2026-09-03 and B435, 2026-08-28) Poor — shown as borderline Poor/Average — as the cost of correctly catching three of the four Poor-labelled recordings.

**The grading rule itself was never revised; the bar used to decide whether to keep it was.** The core-criteria rule (Poor if a core criterion is 1, or two-or-more are 2-or-below with none at 4; Excellent if most are 4 with none 2-or-below) is the same rule throughout. What changed was the **keep criterion**: it was first checked under "keep only if exact agreement improves, Poor or Excellent appear correctly at least once, **and no recording regresses on an Average label**" — the rule-based re-grading of the old-prompt scores passed the first two conditions but failed the third (it flipped the true-Average B435, 28 Aug to Poor), so it was rejected under that bar. The bar was then relaxed to "exact agreement improves, no recording lands two or more grades from its label, and Poor or Excellent appear correctly at least once" — dropping the no-regression-on-Average condition specifically, since catching Poor classes was judged more important than protecting every Average call. Re-checked against the new-prompt scores under this relaxed bar, the same rule now clears it (and, as the paragraph above says, still costs both Average recordings). **It never reaches Excellent**: with only 10 labelled recordings, no combination tried has correctly separated Excellent from Good. **The model's own holistic rating compresses the same way** even under the new prompt (exact 3/10, within-one 9/10, still only ever Average or Good) — so the fix is specific to the core-criteria rule, not a side effect of the better prompt alone.

### Four versions, side by side (in-sample)

The last column is the **shipped** version: new prompt, the core-criteria override, and the Excellent cut at 3.0. The "New prompt, rule-based" column that preceded it (Excellent cut still at 3.4) is kept for comparison.

| Recording | QA label | Old prompt, weighted | Old prompt, rule-based | New prompt, weighted (cut 3.4) | New prompt, rule-based (cut 3.4) | **Shipped: rule-based, cut 3.0** |
|---|---|---|---|---|---|---|
| B491, 2026-06-29 | Excellent | Good (3.06) | Good | Good (3.06) | Good | Excellent |
| B472, 2026-08-24 | Excellent | Good (3.17) | Good | Good (3.27) | Good | Excellent |
| B552, 2026-09-02 | Good | Excellent (3.44) | Good | Good (2.90) | Good | Good |
| B435, 2026-07-25 | Good | Average (2.40) | Average | Average (2.40) | Average | Average |
| B516, 2026-09-03 | Average | Average (2.54) | Average | Average (2.06) | **Poor** | **Poor** |
| B435, 2026-08-28 | Average | Average (2.25) | **Poor** | Average (2.25) | **Poor** | **Poor** |
| B558, 2026-09-05 | Poor | **Good** (2.78) | **Good** | Average (2.40) | Average | Average |
| B482, 2026-09-02 | Poor | Average (2.57) | Average | Average (2.23) | Poor | Poor |
| B392, 2026-09-02 | Poor | Average (2.56) | Poor | Average (2.56) | Poor | Poor |
| B441, 2026-08-26 | Poor | Average (2.46) | Poor | Average (2.46) | Poor | Poor |

Bold marks a recording two or more grades from its label.

| Version | Exact | Within-one | 2+ grades off | Poor correct | Excellent correct |
|---|---|---|---|---|---|
| Old prompt, weighted (previously shipped) | 2/10 | 9/10 | B558 | no | no |
| Old prompt, rule-based (rejected: regressed B435 28 Aug) | 4/10 | 9/10 | B558 | yes | no |
| New prompt, weighted (cut 3.4) | 3/10 | 10/10 | none | no | no |
| New prompt, rule-based (cut 3.4) | 4/10 | 10/10 | none | yes (3 of 4) | no |
| **Shipped: new prompt, rule-based, cut 3.0** | **6/10** | **10/10** | **none** | **yes (3 of 4)** | **yes (2 of 2)** |

Confusion matrix for the shipped version (rows are the QA label):

| Shipped | Poor | Average | Good | Excellent |
|---|---|---|---|---|
| Poor | 3 | 1 | 0 | 0 |
| Average | 2 | 0 | 0 | 0 |
| Good | 0 | 1 | 1 | 0 |
| Excellent | 0 | 0 | 0 | 2 |

### Mean weighted score by label, new prompt (before any grade override)

| Label | n | Mean | Values |
|---|---|---|---|
| Poor | 4 | 2.41 | 2.23, 2.40, 2.46, 2.56 |
| Average | 2 | 2.16 | 2.06, 2.25 |
| Good | 2 | 2.65 | 2.40, 2.90 |
| Excellent | 2 | 3.17 | 3.06, 3.27 |

The Poor and Average means are not just close, they are **inverted: Poor 2.41, Average 2.16** — the weighted score alone ranks the Poor recordings *above* the Average ones. The weighted score cannot fix that by itself; it's exactly why the core-criteria override exists. Re-run cost: $1.90 across 13 top-level calls (10 recordings plus 3 stability checks); some of those calls made 2-3 Anthropic requests each under the new adaptive-median rule, which the dollar figure reflects even though the call count doesn't. Across this run the coverage-gated null-forcing (point 1 above) never had to fire in code — the judge's own prompt compliance was enough on these 10 recordings.

## Excellent cut-point (post-hoc)
The original Excellent cut, 3.4, made Excellent nearly unreachable: the best weighted score the judge ever produced across all 10 recordings was 3.27 (B472), below the cut. Re-grading the same saved scores with the cut at 3.0 instead gives **6/10 exact, 10/10 within-one** (in-sample, same weights, same other two cuts, same override) — but that result only holds for cuts **between 2.90 and 3.06**; outside that narrow band exact agreement drops back to 4-5/10. Leave-one-out — fitting only this cut on 9 recordings and testing on the held-out tenth — gives no real improvement: weighted-only scoring gets 3/10, and with the override included (which already fixes 3 of the 4 Poor recordings regardless of the cut) it gets 5/10 (versus 4/10 for the same rule at the old 3.4 cut, so at most one more recording, within run-to-run noise). Either way there is **no out-of-sample evidence** for 3.0 specifically; it is a post-hoc, in-sample choice, and true accuracy on an unseen recording is probably closer to 3-5 out of 10 than the in-sample 6/10 suggests.

## Tried and rejected
- **A local camera/face-detection check.** Offline, no API cost: 6 frames sampled per recording from the raw video (read from the data in memory, nothing extracted to disk) and checked for a detectable face with OpenCV's Haar cascade. Mean face-detected fraction was 0.42 for Poor-labelled recordings and 0.50 for Average-labelled ones (Good and Excellent were also 0.50) — it did not separate Poor from Average, so it was not built into the app. This was a one-off diagnostic script, not shipped code. A fuller run with a frame every 30 seconds (76 to 179 frames per recording) agreed: a face was detected in about 53% of frames for Poor, 51% for Average, 50% for Good and 60% for Excellent recordings, again with no separation.
- **Re-fitting all three cut-points** (not just the Excellent one) in leave-one-out gave 1/10 exact — far worse than keeping Poor and Average locked and only moving the Excellent cut. With 10 recordings, 2-4 per label, fitting more than one cut overfits badly.
- **A "facts judge"** (branch `facts-judge`, not merged, not shipped). Hypothesis: 1-4 opinion scores compress and invert Poor/Average; countable facts (named greetings, check-in questions, specific/generic/flat praise, recap/homework/goodbye, etc.), each backed by a verified quote and timestamp, scored by fixed code rules written before any run, might separate better. Run once on all 10 labelled recordings with Sonnet against a bar set in advance (exact ≥ 7/10, nothing two or more grades off, at least one Average correct, 3 of 4 Poor correct): it scored **5/10 exact, 7/10 within-one, three recordings two or more grades off, Poor correct 4/4, Average correct 0/2** — it reliably caught the Poor classes but failed the other three conditions. Cause: real specific-praise counts run 0-4 per class, so normalising the warmth rule per 10 minutes of tutor talk crushed it to 1 ("almost no praise") on 6 of 10 recordings regardless of actual quality, which cascaded into the Poor override almost everywhere. The one revision allowed under the same bar — scoring warmth on raw counts instead of a per-10-minute rate — was tested and made it worse (3/10 exact, and a true-Poor recording scored Excellent). Cost: $0.51 for the 10 calls. Tried and rejected; the code stays on the `facts-judge` branch for the record.

## Recording only (no Zoom transcript)
Three labelled recordings were also run **without** their transcript (audio transcribed by faster-whisper `base`, int8, 2 CPU threads, on a Mac, which is faster than the free Space) and compared with their transcript-based scores under the locked rubric. One run each, so this shows the path works, not how accurate it is.

| Recording | Transcription time | Transcript-based: weighted (grade) | Recording only: weighted (grade) |
|---|---|---|---|
| B491, 2026-06-29 | 142 s | 3.06 (Good) | 3.23 (Good, borderline Good/Excellent) |
| B558, 2026-09-05 | 119 s | 2.78 (Good, borderline) | 2.78 (Good, borderline) |
| B516, 2026-09-03 | 91 s | 2.54 (Average) | 2.65 (Average) |

- 14 of the 18 criterion scores were identical and the rest differed by one point; all three grades matched.
- A second run of B558 gave 2.45 (Average), and a run forced into partial mode (41% of the class, 1 minute budget) gave 2.78 (Good). Run-to-run noise (about 0.1 to 0.3) is as large as most of these differences.
- The 2-minute speed probe understated the speed on B558 because the first minutes are silent. The probe now checks that it heard speech and, if not, also times a chunk from the middle of the class. With the fix it projected 128 s against 119 s actual.
- A time budget can be overrun by up to 20% before sampling takes over; a window that does not fully fit is shortened, and the closing is kept before the rest of the opening.
- Cost of these runs: $0.21.

## Not built yet / known limits
- Camera, face and lighting checks and the branded-background check are not built.
- Effort `low` was used throughout; a `low` versus `medium` comparison on Sonnet has not been run.
- Fair turns cannot be measured without speaker identification and is reported but not graded.
- Transcripts in languages other than English (Zoom may mis-transcribe) are not handled specially.
