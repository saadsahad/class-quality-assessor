"""Central settings. Model names and prices live here, never in call sites."""
import os

# Sonnet for calibration and the deployed app (Haiku scored every criterion about the same in testing).
# Override with the JUDGE_MODEL env var, e.g. claude-haiku-5-5 for cheap local runs.
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-sonnet-5-5")

# USD per million tokens (input, output), Anthropic API list prices.
# Haiku 5.5 is quoted for prompts up to 100K tokens; a 60 min VTT is well below that.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}

MAX_RUN_USD = 0.20
JUDGE_MAX_TOKENS = 8000  # ceiling incl. thinking; also the worst case used by the cost guard
JUDGE_EFFORT = os.environ.get("JUDGE_EFFORT", "low")
WHISPER_BUDGET_MIN = float(os.environ.get("WHISPER_BUDGET_MIN", "10"))
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base")
WHISPER_THREADS = int(os.environ.get("WHISPER_THREADS", "2"))  # the free Space has 2 vCPU

VERIFY_WINDOW_S = 30
VERIFY_MIN_RATIO = 85
VERIFY_MIN_WORDS = 3

CAMERA_PENALTY = 0.5

BORDERLINE_BAND = 0.25  # weighted score within this of a cut is shown as borderline between the two grades
