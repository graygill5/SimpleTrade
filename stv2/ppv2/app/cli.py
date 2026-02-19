from __future__ import annotations

import os

from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv

from .account import PaperAccount
from .analytics import analyze_market
from .db import init_db
from .config import db_path
from .stock_view import show  # defined below


HELP = f"""
Commands:
  {Fore.LIGHTGREEN_EX}buy{Style.RESET_ALL}  TICKER SHARES       -> buy  (AAPL) 5
  {Fore.LIGHTRED_EX}sell{Style.RESET_ALL} TICKER SHARES       -> sell (MSFT) 2
  \033[38;5;208mshow\033[0m TICKER              -> snapshot for a stock/index

  {Fore.LIGHTBLUE_EX}portfolio{Style.RESET_ALL}                -> show positions, P/L, cash, equity
  {Fore.LIGHTYELLOW_EX}history{Style.RESET_ALL}                  -> show trade history

  {Fore.LIGHTMAGENTA_EX}analyze{Style.RESET_ALL}                  -> market snapshot + AI take

  reset                    -> wipe state back to $1M
  help                     -> show this help
  clear                    -> clears terminal
  quit                     -> save snapshot and exit
"""


def main() -> None:
    load_dotenv()
    colorama_init(autoreset=False)

    acc_id = init_db(starting_cash=1_000_000.0, account_name="Main")
    acct = PaperAccount(acc_id)

    print(
        f"{Fore.RED}{Style.BRIGHT}ProfitPlug:{Style.RESET_ALL} "
        f"DB -> {Fore.BLACK}{Style.DIM}{db_path()}{Style.RESET_ALL}"
    )
    acct.portfolio()
    print(HELP)

    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaving & exiting...")
            acct.snapshot_on_exit()
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()

        if cmd == "buy" and len(parts) == 3:
            acct.buy(parts[1], int(parts[2]))
        elif cmd == "sell" and len(parts) == 3:
            acct.sell(parts[1], int(parts[2]))
        elif cmd == "portfolio":
            acct.portfolio()
        elif cmd == "history":
            acct.history()
        elif cmd == "analyze":
            analyze_market()
        elif cmd == "show" and len(parts) == 2:
            show(parts[1])
        elif cmd == "reset":
            acct.reset()
        elif cmd == "clear":
            os.system("cls" if os.name == "nt" else "clear")
            print(HELP)
        elif cmd in ("quit", "exit"):
            print("Saving & exiting...")
            acct.snapshot_on_exit()
            break
        elif cmd == "help":
            print(HELP)
        else:
            print("Unknown command. Type 'help'.")


if __name__ == "__main__":
    main()

