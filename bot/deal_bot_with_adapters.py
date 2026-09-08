"""Compatibility entrypoint for the single canonical DEAL24H Bot.

All Bot logic lives in bot/deal_bot.py. This file contains no discovery or
adapter logic and only preserves the previous automation entrypoint.
"""
from __future__ import annotations
import sys
from pathlib import Path

# This file is invoked directly by GitHub Actions (python bot/...). When a
# Python file is launched by path, sys.path starts at /bot, so the repository
# root must be added before importing the canonical bot package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.deal_bot import main

if __name__ == "__main__":
    main()
