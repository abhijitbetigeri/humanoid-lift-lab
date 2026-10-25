"""Smoke test for gemini-4-argon: confirms the key works and the model is reachable.

Usage: .venv/bin/python smoke.py
"""
import time

from google import genai

from argon_env import load_env

load_env()
client = genai.Client()

t0 = time.time()
interaction = client.interactions.create(
    model="gemini-4-argon",
    input="Reply with exactly: ARGON_OK",
    generation_config={"max_output_tokens": 32768, "thinking_level": "low"},
)
print("output :", interaction.output_text.strip())
print("seconds:", round(time.time() - t0, 1))
print("usage  :", getattr(interaction, "usage", None))
