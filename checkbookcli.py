import json
import os
import datetime

DATA_FILE = "checkbook.json"

# Data structure:
# {
#   "accounts": {
#       "1": {"name": "Checking", "balance": 0.0},
#       "2": {"name": "Savings", "balance": 0.0}
#   },
#   "transactions": [
#       {
#          "date": "YYYY-MM-DD",
#          "account_id": "1",
#          "type": "DEPOSIT" / "WITHDRAW",
#          "amount": 100.0,
#          "memo": "Note"
#       },
#       ...
#   ]
# }

data = {
    "accounts": {},
    "transactions": []
}

# ---------- Persistence ----------

def load_data():
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            print("Error loading data. Starting empty.")
            data = {}
    else:
        data = {}

    if "accounts" not in data:
        data["accounts"] = {}
    if "transactions" not in data:
        data["transactions"] = []


def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

# ---------- Helpers ----------

def new_id(d):
    if not d:
        return "1"
    nums = []
    for k in d.keys():
        try:
            nums.append(int(k))
        except ValueError:
            continue
    return str(max(nums) + 1 if nums else 1)


def ask_date(prompt="Date (YYYY-MM-DD, blank = today): "):
    s = input(prompt).strip()
    if not s:
        return datetime.date.today().isoformat()
    try:
        datetime.datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        print("Invalid date. Using today.")
        return datetime.date.today().isoformat()

# ---------- Accounts ----------

def list_accounts():
    if not data["accounts"]:
        print("No accounts.")
        return
    print("\nACCOUNTS:")
    for aid, a in data["accounts"].items():
        print(f"{aid}. {a['name']} - Balance: {a['balance']:.2f}")


def create_account():
    name = input("Account name (e.g. Checking, Savings): ").strip()
    if not name:
        print("Name required.")
        return
    bal_str = input("Initial balance: ").strip()
    try:
        bal = float(bal_str or "0")
    except ValueError:
        print("Invalid amount. Using 0.")
        bal = 0.0

    aid = new_id(data["accounts"])
    data["accounts"][aid] = {"name": name, "balance": bal}
    save_data()
    print(f"Created account {aid}: {name} (Balance: {bal:.2f})")


def select_account(prompt="Select account ID: "):
    if not data["accounts"]:
        print("No accounts.")
        return None
    list_accounts()
    aid = input(prompt).strip()
    if aid not in data["accounts"]:
        print("Account not found.")
        return None
    return aid

# ---------- Transactions ----------

def record_transaction(tx_type):
    if tx_type not in ("DEPOSIT", "WITHDRAW"):
        return
    if not data["accounts"]:
        print("Create an account first.")
        return

    aid = select_account()
    if not aid:
        return

    date = ask_date()
    amt_str = input(f"Amount to {tx_type.lower()}: ").strip()
    try:
        amt = float(amt_str)
    except ValueError:
        print("Invalid amount.")
        return

    if tx_type == "WITHDRAW" and amt > data["accounts"][aid]["balance"]:
        print("Insufficient funds.")
        return

    memo = input("Memo / note (optional): ").strip()

    tx = {
        "date": date,
        "account_id": aid,
        "type": tx_type,
        "amount": amt,
        "memo": memo
    }
    data["transactions"].append(tx)

    if tx_type == "DEPOSIT":
        data["accounts"][aid]["balance"] += amt
    else:
        data["accounts"][aid]["balance"] -= amt

    save_data()
    print(f"{tx_type} recorded.")


def list_transactions():
    if not data["transactions"]:
        print("No transactions.")
        return
    print("\nTRANSACTIONS:")
    for i, t in enumerate(data["transactions"], start=1):
        a = data["accounts"].get(t["account_id"], {}).get("name", "UNKNOWN")
        print(
            f"{i}. {t['date']} | {t['type']:8} | {t['amount']:10.2f} | "
            f"Account: {a} | {t['memo']}"
        )

# ---------- Delete wrong transaction ----------

def delete_transaction():
    if not data["transactions"]:
        print("No transactions to delete.")
        return

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

    if idx < 1 or idx > len(data["transactions"]):
        print("Out of range.")
        return

    tx = data["transactions"][idx - 1]
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
        f"{idx}. {tx['date']} | {tx['type']} | {tx['amount']:.2f} | "
        f"Account: {a_name} | {tx['memo']}"
    )
    confirm = input("Are you sure? (y/N): ").strip().lower()
    if confirm == "y":
        del data["transactions"][idx - 1]
        save_data()
        print("Transaction deleted and balance adjusted.")
    else:
        print("Cancelled.")

# ---------- Menus ----------

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
        elif op == "0":
            print("Goodbye.")
            break
        else:
            print("Invalid option.")


if __name__ == "__main__":
    main_menu()
