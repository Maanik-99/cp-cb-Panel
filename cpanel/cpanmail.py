#!/usr/bin/env python3
"""
Continuous Email Cycler with Auto‑Check every 3 seconds.
Press Alt+V to delete current email and create a new random one.
"""

import secrets
import string
import requests
import imaplib
import email
from email.policy import default
import threading
import time
import sys
from typing import Dict, Optional

# Disable SSL warnings
import urllib3
urllib3.disable_warnings()

# =========================================================
# CONFIGURATION – Your cPanel credentials
# =========================================================
CPANEL_HOST = "https://admiredentalbristol.com:2083"
CPANEL_USER = "admirebristol"
API_TOKEN   = "O7EKK7GDGS1TCBYZC6AFOXPG63SUP6ZW"

TIMEOUT = 15
EMAIL_DOMAIN = "admiredentalbristol.com"
QUOTA_MB = 250
PASSWORD_LENGTH = 16
USERNAME_LENGTH = 8
IMAP_PORT = 993
IMAP_SERVER = None   # None = use EMAIL_DOMAIN

# Check interval (seconds)
CHECK_INTERVAL = 3

# =========================================================
# API URLs
# =========================================================
LIST_EMAILS_URL = f"{CPANEL_HOST}/execute/Email/list_pops"
DELETE_EMAIL_URL = f"{CPANEL_HOST}/execute/Email/delete_pop"
CREATE_EMAIL_URL = f"{CPANEL_HOST}/execute/Email/add_pop"

# =========================================================
# SESSION
# =========================================================
session = requests.Session()
session.verify = False
session.headers.update({
    "Authorization": f"cpanel {CPANEL_USER}:{API_TOKEN}",
    "Connection": "keep-alive"
})

# =========================================================
# GLOBAL STATE (protected by a lock)
# =========================================================
current_email = {
    "full": None,
    "username": None,
    "password": None
}
email_lock = threading.Lock()

# =========================================================
# HELPER FUNCTIONS
# =========================================================
def random_string(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def generate_random_username(prefix: str = "user") -> str:
    return f"{prefix}_{random_string(USERNAME_LENGTH)}"

def generate_random_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(chars) for _ in range(length))

def cpanel_api_call(url: str, params: Dict = None) -> Dict:
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT)
    except Exception as e:
        raise Exception(f"Connection error: {e}")
    if resp.status_code != 200:
        raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    if data.get("status") != 1:
        error = data.get("errors", ["Unknown"])[0]
        raise Exception(f"API error: {error}")
    return data.get("data", {})

def delete_email_account(email: str) -> bool:
    try:
        cpanel_api_call(DELETE_EMAIL_URL, {"email": email})
        print(f"✔ Deleted: {email}")
        return True
    except Exception as e:
        print(f"✘ Failed to delete {email}: {e}")
        return False

def create_email_account(username: str, domain: str, password: str, quota: int) -> str:
    params = {
        "email": username,
        "domain": domain,
        "password": password,
        "quota": quota
    }
    cpanel_api_call(CREATE_EMAIL_URL, params)
    return f"{username}@{domain}"

def list_all_accounts() -> list:
    result = cpanel_api_call(LIST_EMAILS_URL)
    if "pops" in result:
        return result["pops"]
    elif "accounts" in result:
        return result["accounts"]
    else:
        return []

def find_account_by_username(accounts: list, username: str) -> Optional[str]:
    for acc in accounts:
        email_addr = acc.get("email") or acc.get("address") or ""
        if email_addr.split("@")[0] == username:
            return email_addr
    return None

def check_inbox(email_address: str, password: str) -> Dict:
    host = IMAP_SERVER or email_address.split("@")[1]
    try:
        imap = imaplib.IMAP4_SSL(host, IMAP_PORT)
        imap.login(email_address, password)
        imap.select("INBOX")
        status, msg_ids = imap.search(None, "ALL")
        if status != "OK":
            raise Exception("Search failed")
        ids = msg_ids[0].split()
        total = len(ids)
        result = {"total": total, "latest_preview": None}
        if total > 0:
            latest_id = ids[-1]
            status, data = imap.fetch(latest_id, "(RFC822)")
            if status == "OK":
                raw = data[0][1]
                msg = email.message_from_bytes(raw, policy=default)
                subject = msg.get("Subject", "(no subject)")
                from_addr = msg.get("From", "unknown")
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_content()
                            break
                else:
                    body = msg.get_content()
                preview = body[:300].replace("\n", " ").strip()
                result["latest_preview"] = f"From: {from_addr}\nSubject: {subject}\nPreview: {preview}..."
        imap.close()
        imap.logout()
        return result
    except Exception as e:
        return {"total": 0, "error": str(e), "latest_preview": None}

def create_new_email():
    """Generate random credentials, create email account, update global state."""
    username = generate_random_username()
    password = generate_random_password(PASSWORD_LENGTH)

    print("\n🔐 Creating new random email account...")
    print(f"   Username: {username}")
    print(f"   Password: {password}")

    # Delete any existing account with the same random username (cleanup)
    accounts = list_all_accounts()
    existing = find_account_by_username(accounts, username)
    if existing:
        print(f"⚠ Deleting conflicting account: {existing}")
        delete_email_account(existing)

    full_email = create_email_account(username, EMAIL_DOMAIN, password, QUOTA_MB)
    print(f"✅ Created: {full_email}")

    # Update global state (thread-safe)
    with email_lock:
        current_email["full"] = full_email
        current_email["username"] = username
        current_email["password"] = password

    # Immediately check inbox once to show status
    inbox = check_inbox(full_email, password)
    print("\n📬 Initial inbox check:")
    print(f"   Total messages: {inbox['total']}")
    if inbox.get("latest_preview"):
        print("\n📄 Latest message preview:\n" + inbox["latest_preview"])

def delete_current_and_create_new():
    """Delete current email (if exists) and create a new one."""
    with email_lock:
        old_email = current_email["full"]
    if old_email:
        print(f"\n🗑 Deleting current email: {old_email}")
        delete_email_account(old_email)
    else:
        print("\nℹ No current email to delete – creating first one.")
    create_new_email()

# =========================================================
# PERIODIC CHECKER (every 3 seconds)
# =========================================================
def periodic_checker():
    """Runs every CHECK_INTERVAL seconds, checks inbox of current email."""
    last_total = 0
    while True:
        time.sleep(CHECK_INTERVAL)
        with email_lock:
            email_full = current_email["full"]
            email_pass = current_email["password"]
        if email_full and email_pass:
            inbox = check_inbox(email_full, email_pass)
            if inbox.get("error"):
                # Silently ignore IMAP errors (maybe account not ready)
                continue
            total = inbox["total"]
            if total != last_total:
                # New messages arrived or count changed
                print(f"\n📬 [{email_full}] New inbox status: {total} messages (was {last_total})")
                if inbox.get("latest_preview"):
                    print("📄 Latest message:\n" + inbox["latest_preview"])
                last_total = total
            else:
                # Optional: print a dot to show it's alive – but we keep quiet
                pass

# =========================================================
# HOTKEY LISTENER (Alt+V)
# =========================================================
def hotkey_listener():
    import keyboard
    print("\n🎧 Listening for Alt+V... Press Alt+V to replace current email with a new one.\n")
    keyboard.add_hotkey('alt+v', delete_current_and_create_new)
    keyboard.wait()  # blocks

# =========================================================
# MAIN
# =========================================================
def main():
    # Create the first email account
    create_new_email()

    # Start hotkey listener in background
    hotkey_thread = threading.Thread(target=hotkey_listener, daemon=True)
    hotkey_thread.start()

    # Start periodic checker
    checker_thread = threading.Thread(target=periodic_checker, daemon=True)
    checker_thread.start()

    print("\n💡 Script is running.")
    print("   - Press Alt+V to delete current email and create a new random one.")
    print(f"   - Inbox is checked every {CHECK_INTERVAL} seconds.")
    print("   - Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)  # keep main thread alive
    except KeyboardInterrupt:
        print("\n\n🛑 Exiting... Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()