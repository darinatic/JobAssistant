"""Offline prompt-evaluation harness (dev/CI only — not part of the deployed app).

Runs a resume-tailor prompt version over a small golden set of (CV, JD) cases and
scores each output with the app's DETERMINISTIC graders (honesty linter, keyword
coverage, one-page fit, structure). Objective, free, repeatable. See evals/run.py.
"""
