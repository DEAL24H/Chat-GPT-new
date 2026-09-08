"""Compatibility entrypoint for the single canonical DEAL24H Bot.

All Bot logic lives in bot/deal_bot.py. This file contains no discovery or
adapter logic and only preserves the previous automation entrypoint.
"""
from bot.deal_bot import main

if __name__ == "__main__":
    main()
