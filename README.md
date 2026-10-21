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
2. One Claude call scores the criteria below (1 to 4, or N/A) and returns verbatim quotes with timestamps, plus any stretches of played media (e.g. YouTube) so these are never quoted as the tutor.
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

Grade boundaries on the weighted score (1 to 4): Poor below 2.0, Average below 2.75, Good below 3.4, otherwise Excellent.
These boundaries and the weights are locked; they were **not validated** by calibration (see results).

## Privacy
- The password screen is the only thing shown until the correct password is entered.
- Uploads and downloaded links are handled in a temporary folder that is deleted afterwards (even on errors); an upload also sits in server memory until the browser session ends. Nothing is stored, cached or logged; the original file name is never written to disk.
- A pasted link is fetched by the server: only http(s) links to public addresses are accepted (private, local and link-local addresses are refused, including after redirects), downloads are capped at 2 GB, and Google Drive links use the Drive downloader. The file must be shared as "Anyone with the link".
- Names are masked (`[Name A]`) in everything displayed. Only transcript text goes to the model, with device labels pseudonymised.
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
