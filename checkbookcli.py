#!/usr/bin/env python3
"""
Improved CLI for checkbook (Linux/Ubuntu friendly)
- Uses XDG data dir (~/.local/share/checkbookcli/checkbook.json)
- Adds argparse-based subcommands for scripting / automation
- Keeps interactive menu when run without arguments
- Uses file locking (fcntl) for safe concurrent access on Unix
- Adds CSV export and safer parsing/validation
"""

import argparse
import csv
import datetime
import fcntl
import json
import os
import pathlib
import sys
import textwrap
from typing import Dict, List

# Data storage (XDG-friendly)
XDG_DATA_HOME = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
APP_DIR = os.path.join(XDG_DATA_HOME, "checkbookcli")
DATA_FILE = os.path.join(APP_DIR, "checkbook.json")
LOCK_FILE = os.path.join(APP_DIR, ".lock")

# Default in-memory structure
data = {"accounts": {}, "transactions": []}

# ---------- Persistence ----------

def ensure_app_dir():
    pathlib.Path(APP_DIR).mkdir(parents=True, exist_ok=True)


def _locked_open(path, mode="r+"):
    """Open a file and acquire an exclusive lock. Caller must close file."""
    f = open(path, mode, encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    except Exception:
        f.close()
        raise
    return f


def load_data():
    """Load data from DATA_FILE into global `data`. Creates file if missing."""
    global data
    ensure_app_dir()
    # If file doesn't exist, initialize with defaults
    if not os.path.exists(DATA_FILE):
        data = {"accounts": {}, "transactions": []}
        save_data()
        return

    # Use a shared read lock to avoid races with writers
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            data = json.load(f)
        except json.JSONDecodeError:
            print("Warning: data file is corrupted. Starting with empty dataset.")
            data = {"accounts": {}, "transactions": []}
        except Exception as e:
            print(f"Error loading data: {e}")
            data = {"accounts": {}, "transactions": []}
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass

    if "accounts" not in data:
        data["accounts"] = {}
    if "transactions" not in data:
        data["transactions"] = []


def save_data():
    """Atomically write `data` to DATA_FILE with exclusive lock."""
    ensure_app_dir()
    tmp = DATA_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            # Lock file while writing
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        print(f"Error saving data: {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass

# ---------- Helpers ----------

def new_id(d: Dict[str, Dict]) -> str:
    if not d:
        return "1"
    nums = []
    for k in d.keys():
        try:
            nums.append(int(k))
        except Exception:
            continue
    return str(max(nums) + 1 if nums else 1)


def ask_date(prompt: str = "Date (YYYY-MM-DD, blank = today): ") -> str:
    s = input(prompt).strip()
    if not s:
        return datetime.date.today().isoformat()
    try:
        datetime.datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        print("Invalid date. Using today.")
        return datetime.date.today().isoformat()


def format_currency(amount: float) -> str:
    return f"{amount:.2f}"

# ---------- Accounts ----------

def list_accounts(out=sys.stdout):
    if not data.get("accounts"):
        print("No accounts.")
        return
    print("\nACCOUNTS:", file=out)
    for aid, a in sorted(data["accounts"].items(), key=lambda x: int(x[0])):
        print(f"{aid}. {a['name']} - Balance: {format_currency(a['balance'])}", file=out)


def create_account(name: str = None, balance: float = 0.0):
    if name is None:
        name = input("Account name (e.g. Checking, Savings): ").strip()
        if not name:
            print("Name required.")
            return
    aid = new_id(data["accounts"])
    data["accounts"][aid] = {"name": name, "balance": float(balance)}
    save_data()
    print(f"Created account {aid}: {name} (Balance: {format_currency(float(balance))})")
    return aid


def select_account(prompt: str = "Select account ID: ") -> str:
    if not data.get("accounts"):
        print("No accounts.")
        return None
    list_accounts()
    aid = input(prompt).strip()
    if aid not in data["accounts"]:
        print("Account not found.")
        return None
    return aid

# ---------- Transactions ----------

def record_transaction(tx_type: str, account_id: str = None, amount: float = None, date: str = None, memo: str = ""):
    if tx_type not in ("DEPOSIT", "WITHDRAW"):
        raise ValueError("Invalid transaction type")

    if not data.get("accounts"):
        print("Create an account first.")
        return

    if account_id is None:
        account_id = select_account()
        if not account_id:
            return
    elif account_id not in data["accounts"]:
        print("Account not found.")
        return

    if date is None:
        date = ask_date()
    else:
        # validate
        try:
            datetime.datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            print("Invalid date format, using today.")
            date = datetime.date.today().isoformat()

    if amount is None:
        amt_str = input(f"Amount to {tx_type.lower()}: ").strip()
        try:
            amount = float(amt_str)
        except ValueError:
            print("Invalid amount.")
            return
    else:
        amount = float(amount)

    if tx_type == "WITHDRAW" and amount > data["accounts"][account_id]["balance"]:
        print("Insufficient funds.")
        return

    if not memo:
        memo = input("Memo / note (optional): ").strip()

    tx = {
        "date": date,
        "account_id": account_id,
        "type": tx_type,
        "amount": amount,
        "memo": memo,
    }
    data["transactions"].append(tx)

    if tx_type == "DEPOSIT":
        data["accounts"][account_id]["balance"] += amount
    else:
        data["accounts"][account_id]["balance"] -= amount

    save_data()
    print(f"{tx_type} recorded.")


def list_transactions(out=sys.stdout, account_id: str = None, limit: int = None):
    txs: List[Dict] = data.get("transactions", [])
    if account_id:
        txs = [t for t in txs if t.get("account_id") == account_id]
    if not txs:
        print("No transactions.")
        return
    print("\nTRANSACTIONS:", file=out)
    for i, t in enumerate(txs, start=1):
        a = data["accounts"].get(t["account_id"], {}).get("name", "UNKNOWN")
        print(
            f"{i}. {t['date']} | {t['type']:8} | {t['amount']:10.2f} | Account: {a} | {t['memo']}",
            file=out,
        )


def delete_transaction(index: int = None):
    txs = data.get("transactions", [])
    if not txs:
        print("No transactions to delete.")
        return

    if index is None:
        list_transactions()
        s = input("Enter transaction number to DELETE (or blank to cancel): ").strip()
        if not s:
            print("Cancelled.")
            return
        try:
            idx = int(s)
        except ValueError:
            print("Invalid number.")
            return
    else:
        idx = int(index)

    if idx < 1 or idx > len(txs):
        print("Out of range.")
        return

    tx = txs[idx - 1]
    aid = tx["account_id"]
    if aid not in data["accounts"]:
        print("Account missing. Deleting transaction only.")
    else:
        amt = tx["amount"]
        if tx["type"] == "DEPOSIT":
            data["accounts"][aid]["balance"] -= amt
        elif tx["type"] == "WITHDRAW":
            data["accounts"][aid]["balance"] += amt

    print("Deleting transaction:")
    a_name = data["accounts"].get(aid, {}).get("name", "UNKNOWN")
    print(
        f"{idx}. {tx['date']} | {tx['type']} | {tx['amount']:.2f} | Account: {a_name} | {tx['memo']}"
    )
    confirm = input("Are you sure? (y/N): ").strip().lower()
    if confirm == "y":
        del data["transactions"][idx - 1]
        save_data()
        print("Transaction deleted and balance adjusted.")
    else:
        print("Cancelled.")


def export_csv(path: str):
    ensure_app_dir()
    txs = data.get("transactions", [])
    if not txs:
        print("No transactions to export.")
        return
    try:
        with open(path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["date", "account_id", "account_name", "type", "amount", "memo"])
            for t in txs:
                writer.writerow([
                    t.get("date"),
                    t.get("account_id"),
                    data.get("accounts", {}).get(t.get("account_id"), {}).get("name", ""),
                    t.get("type"),
                    t.get("amount"),
                    t.get("memo"),
                ])
        print(f"Exported {len(txs)} transactions to {path}")
    except Exception as e:
        print(f"Error exporting CSV: {e}")

# ---------- Menus (interactive) ----------


def accounts_menu():
    while True:
        print("\n--- Accounts ---")
        print("1. List accounts")
        print("2. Create account")
        print("0. Back")
        op = input("Option: ").strip()
        if op == "1":
            list_accounts()
        elif op == "2":
            create_account()
        elif op == "0":
            break
        else:
            print("Invalid option.")


def main_menu():
    load_data()
    while True:
        print("\n=== SIMPLE CHECKBOOK (CLI) ===")
        print("1. Accounts")
        print("2. Record DEPOSIT")
        print("3. Record WITHDRAWAL")
        print("4. List transactions")
        print("5. Delete a transaction (wrong input)")
        print("6. Export transactions to CSV")
        print("0. Exit")
        op = input("Option: ").strip()

        if op == "1":
            accounts_menu()
        elif op == "2":
            record_transaction("DEPOSIT")
        elif op == "3":
            record_transaction("WITHDRAW")
        elif op == "4":
            list_transactions()
        elif op == "5":
            delete_transaction()
        elif op == "6":
            p = input("Path to CSV file: ").strip() or "checkbook_export.csv"
            export_csv(p)
        elif op == "0":
            print("Goodbye.")
            break
        else:
            print("Invalid option.")

# ---------- CLI (argparse) ----------


def build_parser():
    parser = argparse.ArgumentParser(description="Checkbook CLI (BankFlow-MultiCuenta)")
    sub = parser.add_subparsers(dest="cmd")

    # accounts list / create
    p_accounts = sub.add_parser("accounts", help="Manage accounts")
    p_accounts_sub = p_accounts.add_subparsers(dest="subcmd")
    p_accounts_sub.add_parser("list", help="List accounts")
    p_ac_create = p_accounts_sub.add_parser("create", help="Create account")
    p_ac_create.add_argument("name")
    p_ac_create.add_argument("--balance", type=float, default=0.0)

    # transactions
    p_tx = sub.add_parser("tx", help="Transactions operations")
    p_tx_sub = p_tx.add_subparsers(dest="subcmd")

    p_deposit = p_tx_sub.add_parser("deposit", help="Record a deposit")
    p_deposit.add_argument("account_id")
    p_deposit.add_argument("amount", type=float)
    p_deposit.add_argument("--date")
    p_deposit.add_argument("--memo", default="")

    p_withdraw = p_tx_sub.add_parser("withdraw", help="Record a withdrawal")
    p_withdraw.add_argument("account_id")
    p_withdraw.add_argument("amount", type=float)
    p_withdraw.add_argument("--date")
    p_withdraw.add_argument("--memo", default="")

    p_list = p_tx_sub.add_parser("list", help="List transactions")
    p_list.add_argument("--account_id", required=False)
    p_list.add_argument("--limit", type=int, required=False)

    p_del = p_tx_sub.add_parser("delete", help="Delete transaction by its index in list")
    p_del.add_argument("index", type=int)

    # export
    p_export = sub.add_parser("export", help="Export transactions to CSV")
    p_export.add_argument("path")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd is None:
        # interactive
        main_menu()
        return

    load_data()

    if args.cmd == "accounts":
        if args.subcmd == "list":
            list_accounts()
        elif args.subcmd == "create":
            create_account(name=args.name, balance=args.balance)
        else:
            parser.print_help()

    elif args.cmd == "tx":
        if args.subcmd == "deposit":
            record_transaction("DEPOSIT", account_id=args.account_id, amount=args.amount, date=args.date, memo=args.memo)
        elif args.subcmd == "withdraw":
            record_transaction("WITHDRAW", account_id=args.account_id, amount=args.amount, date=args.date, memo=args.memo)
        elif args.subcmd == "list":
            list_transactions(account_id=getattr(args, "account_id", None), limit=getattr(args, "limit", None))
        elif args.subcmd == "delete":
            delete_transaction(index=args.index)
        else:
            parser.print_help()

    elif args.cmd == "export":
        export_csv(args.path)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
