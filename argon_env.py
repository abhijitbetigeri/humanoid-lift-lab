"""Loads GEMINI_API_KEY from .env next to this file."""
import os
import pathlib


def load_env():
    env = pathlib.Path(__file__).with_name(".env")
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is empty: add it to .env")
