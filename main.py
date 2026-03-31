# main.py
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv
import os

from funcs import (
    init_db, PaperAccount, analyze_market, HELP,
    get_db_path, show, info, connections,
    create_account, list_accounts, get_account_id_by_name,
    show_active_account, delete_account
)

load_dotenv()

def main():
    colorama_init(autoreset=False)
    acc_id = init_db(starting_cash=1_000_000.0, account_name="Main")
    acct = PaperAccount(acc_id)

    print(
        f"{Fore.RED}{Style.BRIGHT}ProfitPlug: {Style.RESET_ALL}"
        f"Your data is stored here -> "
        f"{Fore.BLACK}{Style.DIM}{get_db_path()}{Style.RESET_ALL}"
    )

    show_active_account(acc_id)
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

        elif cmd == "connections" and len(parts) == 2:
            connections(parts[1])

        elif cmd == "accounts":
            list_accounts()

        elif cmd == "whoami":
            show_active_account(acct.account_id)

        elif cmd == "create_account" and len(parts) >= 2:
            name = " ".join(parts[1:])
            create_account(name)

        elif cmd == "switch_account" and len(parts) >= 2:
            name = " ".join(parts[1:])
            new_id = get_account_id_by_name(name)
            if new_id is None:
                print(f"✖ Account '{name}' not found.")
            else:
                acct.snapshot_on_exit()
                acct = PaperAccount(new_id)
                print(f"✓ Switched to account '{name}'")
                show_active_account(acct.account_id)

        elif cmd == "delete_account" and len(parts) >= 2:
            name = " ".join(parts[1:])
            delete_id = get_account_id_by_name(name)

            if delete_id is None:
                print(f"✖ Account '{name}' not found.")
            elif delete_id == acct.account_id:
                print("✖ Cannot delete the active account. Switch first.")
            else:
                delete_account(name)

        elif cmd == "reset":
            acct.reset()

        elif cmd == "info":
            if len(parts) == 1:
                info("list")
            else:
                info(" ".join(parts[1:]))
                print("Tip: info rsi | info 'moving average' | info macro | info all")

        elif cmd == "clear":
            os.system('cls' if os.name == 'nt' else 'clear')
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