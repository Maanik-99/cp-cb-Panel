#!/usr/bin/env python3
"""
CPanel Manager – Create/Delete email accounts, Delete forwarders (live progress), Check messages (IMAP) – instant file write
"""

import requests
import urllib3
import time
import os
import sys
import secrets
import string
import imaplib
import email
from email.policy import default
from typing import List, Tuple, Dict

urllib3.disable_warnings()

# =========================================================
# FIXED SETTINGS – EDIT THESE ONCE
# =========================================================
CREATE_COUNT = 100                     # How many accounts per base name (1..N)
QUOTA = "250"                          # Mailbox quota (MB)
SAVE_PASSWORDS = True                  # Always save passwords to passwords.txt
DELETE_EXISTING_BEFORE_CREATE = False  # False = skip existing accounts (don't delete)

# Choose name mode:
USE_NUMBERED_NAMES = False       # Single base name for all panels (ignored if basename file used)
USE_BASENAME_FILE = True         # Use per-panel base names from names.txt
BASENAME_FILE = "names.txt"      # One base name per line, for each panel in order

# Only used if USE_NUMBERED_NAMES = True
BASE_NAME = "adam"

# Only used if both USE_NUMBERED_NAMES and USE_BASENAME_FILE are False
NAMES_FILE = "names.txt"

TIMEOUT = 15
CPANEL_FILE = "cpanel.txt"

# IMAP settings for message checking
IMAP_PORT = 993
IMAP_SERVER = None               # None = use mail.{domain}
PASSWORDS_FILE = "passwords.txt"
REPORT_FILE = "reportmsgsubject.txt"

# =========================================================
# HELPER FUNCTIONS
# =========================================================
def clear_console():
    os.system("cls" if os.name == "nt" else "clear")

def wait_for_user():
    input("\nPress Enter to return to menu...")

def random_password(length=16):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def load_cpanel_configs() -> List[Tuple[str, str, str, str]]:
    configs = []
    try:
        with open(CPANEL_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 4:
                    host, user, domain, token = parts[0], parts[1], parts[2], parts[3]
                    configs.append((host, user, domain, token))
    except FileNotFoundError:
        print(f"[!] File {CPANEL_FILE} not found.")
    return configs

def load_basenames() -> List[str]:
    basenames = []
    try:
        with open(BASENAME_FILE, "r") as f:
            for line in f:
                name = line.strip().lower()
                if name:
                    basenames.append(name)
    except FileNotFoundError:
        print(f"[!] File {BASENAME_FILE} not found.")
    return basenames

def get_name_list_for_panel(panel_index: int, total_panels: int) -> List[str]:
    """Return list of local parts (usernames) for a given panel."""
    if USE_NUMBERED_NAMES:
        return [f"{BASE_NAME}{i}" for i in range(1, CREATE_COUNT + 1)]
    elif USE_BASENAME_FILE:
        basenames = load_basenames()
        if not basenames:
            return []
        if panel_index >= len(basenames):
            print(f"  ⚠ Not enough base names for panel {panel_index+1}. Needed {panel_index+1}, have {len(basenames)}.")
            return []
        base = basenames[panel_index]
        return [f"{base}{i}" for i in range(1, CREATE_COUNT + 1)]
    else:
        # Original names.txt mode (full local parts)
        try:
            with open(NAMES_FILE, "r") as f:
                names = [line.strip().lower() for line in f if line.strip()]
            return names[:CREATE_COUNT]
        except FileNotFoundError:
            print(f"[!] File {NAMES_FILE} not found.")
            return []

def email_exists(session: requests.Session, host: str, domain: str, local: str) -> bool:
    url = f"{host}/execute/Email/list_pops"
    try:
        resp = session.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != 1:
            return False
        accounts = data.get("data", {}).get("pops") or data.get("data", {}).get("accounts") or []
        for acc in accounts:
            email_addr = acc.get("email") or acc.get("address") or ""
            if email_addr == f"{local}@{domain}":
                return True
    except:
        pass
    return False

def delete_email_account(session: requests.Session, host: str, domain: str, email: str) -> bool:
    url = f"{host}/execute/Email/delete_pop"
    params = {"email": email, "domain": domain}
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT)
        data = resp.json()
        return data.get("status") == 1
    except:
        return False

def create_email_account(session: requests.Session, host: str, domain: str, local: str, password: str, quota: int) -> bool:
    url = f"{host}/execute/Email/add_pop"
    params = {
        "email": local,
        "domain": domain,
        "password": password,
        "quota": str(quota)
    }
    try:
        resp = session.get(url, params=params, timeout=TIMEOUT)
        data = resp.json()
        return data.get("status") == 1
    except:
        return False

def session_for_panel(host: str, user: str, token: str) -> requests.Session:
    sess = requests.Session()
    sess.verify = False
    sess.headers.update({
        "Authorization": f"cpanel {user}:{token}",
        "Connection": "keep-alive"
    })
    return sess

def fetch_subjects(email_address: str, password: str, domain: str) -> List[str]:
    """Return list of subjects (or error string)."""
    host = IMAP_SERVER or f"mail.{domain}"
    subjects = []
    try:
        imap = imaplib.IMAP4_SSL(host, IMAP_PORT, timeout=TIMEOUT)
        imap.login(email_address, password)
        imap.select("INBOX")
        status, msg_ids = imap.search(None, "ALL")
        if status != "OK":
            raise Exception("IMAP search failed")
        ids = msg_ids[0].split()
        for msg_id in ids:
            status, data = imap.fetch(msg_id, "(RFC822)")
            if status == "OK":
                raw = data[0][1]
                msg = email.message_from_bytes(raw, policy=default)
                subject = msg.get("Subject", "(no subject)")
                subjects.append(subject)
        imap.close()
        imap.logout()
    except Exception as e:
        subjects.append(f"IMAP ERROR: {str(e)}")
    return subjects

# =========================================================
# OPTION 1: BULK CREATE
# =========================================================
def bulk_create_all_panels():
    clear_console()
    print("=" * 70)
    print("        BULK CREATE – ALL PANELS (skip existing)")
    print("=" * 70)

    configs = load_cpanel_configs()
    if not configs:
        wait_for_user()
        return

    # Get name list for each panel (pre‑compute because we need panel index)
    panel_names = []
    for idx in range(len(configs)):
        names = get_name_list_for_panel(idx, len(configs))
        if not names:
            print(f"[!] No names for panel {idx+1}. Aborting.")
            wait_for_user()
            return
        panel_names.append(names)

    total_created = 0
    total_existed = 0
    total_failed = 0
    all_passwords = []  # list of (email_lower, password)

    for pidx, (host, user, domain, token) in enumerate(configs):
        names = panel_names[pidx]
        print(f"\n--- PANEL {pidx+1}/{len(configs)} : {user} @ {domain} ---")
        print(f"  Target accounts: {len(names)} ({names[0]} .. {names[-1]})")
        sess = session_for_panel(host, user, token)

        created = 0
        existed = 0
        failed = 0

        for local in names:
            email = f"{local}@{domain}"
            email_lower = email.lower()
            if email_exists(sess, host, domain, local):
                print(f"  ⚠ Already exists: {email}")
                existed += 1
                continue

            password = random_password()
            if create_email_account(sess, host, domain, local, password, QUOTA):
                created += 1
                all_passwords.append((email_lower, password))
                print(f"  ✅ Created: {email} (pass: {password})")
            else:
                failed += 1
                print(f"  ❌ Failed: {email}")

        total_created += created
        total_existed += existed
        total_failed += failed
        print(f"  -> Panel done: {created} created, {existed} existed, {failed} failed.")

    print("\n" + "=" * 70)
    print(f"TOTAL: Created {total_created}, Existed {total_existed}, Failed {total_failed}")
    print("=" * 70)

    if SAVE_PASSWORDS and all_passwords:
        with open(PASSWORDS_FILE, "w", encoding="utf-8") as f:
            for email, pwd in all_passwords:
                f.write(f"{email}\t{pwd}\n")
        print(f"[*] Passwords saved to {PASSWORDS_FILE} (tab‑separated, lowercase emails).")
    wait_for_user()

# =========================================================
# OPTION 2: BULK DELETE
# =========================================================
def bulk_delete_all_panels():
    clear_console()
    print("=" * 70)
    print("        BULK DELETE – ALL PANELS")
    print("=" * 70)

    configs = load_cpanel_configs()
    if not configs:
        wait_for_user()
        return

    panel_names = []
    for idx in range(len(configs)):
        names = get_name_list_for_panel(idx, len(configs))
        if not names:
            print(f"[!] No names for panel {idx+1}. Aborting.")
            wait_for_user()
            return
        panel_names.append(names)

    total_deleted = 0
    total_failed = 0

    for pidx, (host, user, domain, token) in enumerate(configs):
        names = panel_names[pidx]
        print(f"\n--- PANEL {pidx+1}/{len(configs)} : {user} @ {domain} ---")
        sess = session_for_panel(host, user, token)

        deleted = 0
        failed = 0
        for local in names:
            email = f"{local}@{domain}"
            if delete_email_account(sess, host, domain, email):
                deleted += 1
                print(f"  ✅ Deleted: {email}")
            else:
                failed += 1
                print(f"  ❌ Failed: {email}")

        total_deleted += deleted
        total_failed += failed
        print(f"  -> Panel done: {deleted} deleted, {failed} failed.")

    print("\n" + "=" * 70)
    print(f"TOTAL: Deleted {total_deleted}, Failed {total_failed}")
    print("=" * 70)
    wait_for_user()

# =========================================================
# OPTION 3: DELETE ALL FORWARDERS (all panels) – with LIVE PROGRESS
# =========================================================
def delete_forwarders_all_panels():
    clear_console()
    print("=" * 70)
    print("        DELETE ALL FORWARDERS – ALL PANELS (live progress)")
    print("=" * 70)

    configs = load_cpanel_configs()
    if not configs:
        wait_for_user()
        return

    total_deleted = 0
    total_failed = 0
    total_skipped = 0

    for idx, (host, user, domain, token) in enumerate(configs):
        print(f"\n--- PANEL {idx+1}/{len(configs)} : {user} @ {host} ---")
        sess = session_for_panel(host, user, token)

        # Fetch forwarders
        try:
            resp = sess.get(f"{host}/execute/Email/list_forwarders", timeout=TIMEOUT)
            data = resp.json()
        except Exception as e:
            print(f"  [!] Error fetching forwarders: {e}")
            continue

        if data.get("status") != 1:
            print(f"  [!] API error: {data.get('errors', ['Unknown'])}")
            continue

        forwarders = data.get("data", [])
        total = len(forwarders)
        if total == 0:
            print("  [*] No forwarders found.")
            continue

        print(f"  [*] Found {total} forwarders. Deleting...")

        deleted = 0
        failed = 0
        skipped = 0

        # Process each forwarder with live progress (inline updating)
        for i, item in enumerate(forwarders, 1):
            source = (item.get("dest") or item.get("address") or item.get("email") or item.get("source"))
            dest = (item.get("forward") or item.get("fwdopt") or item.get("destination"))
            if not source or not dest or "@" not in source:
                skipped += 1
            else:
                try:
                    payload = {"address": source.strip().lower(), "forwarder": dest.strip().lower()}
                    resp_del = sess.get(f"{host}/execute/Email/delete_forwarder", params=payload, timeout=TIMEOUT)
                    if resp_del.status_code == 200:
                        deleted += 1
                    else:
                        failed += 1
                except Exception:
                    failed += 1

            # Live progress update (overwrites same line)
            percent = (i / total) * 100
            sys.stdout.write(f"\r     Progress: {i}/{total} ({percent:.1f}%) | Deleted: {deleted} | Failed: {failed} | Skipped: {skipped}")
            sys.stdout.flush()

        # New line after progress completes
        print()
        print(f"  -> Panel done: {deleted} deleted, {failed} failed, {skipped} skipped.")

        total_deleted += deleted
        total_failed += failed
        total_skipped += skipped

    print("\n" + "=" * 70)
    print(f"ALL PANELS COMPLETE: Deleted {total_deleted}, Failed {total_failed}, Skipped {total_skipped}")
    print("=" * 70)
    wait_for_user()

# =========================================================
# OPTION 4: CHECK MESSAGES (IMAP) – INSTANT FILE SAVE
# =========================================================
def check_messages_all_panels():
    clear_console()
    print("=" * 70)
    print("        CHECK MESSAGES (IMAP) – ALL PANELS (instant save)")
    print("=" * 70)

    configs = load_cpanel_configs()
    if not configs:
        wait_for_user()
        return

    # Load passwords
    try:
        with open(PASSWORDS_FILE, "r", encoding="utf-8") as f:
            passwords = {}
            for line in f:
                line = line.strip()
                if not line or "\t" not in line:
                    continue
                email, pwd = line.split("\t", 1)
                passwords[email.lower()] = pwd
    except FileNotFoundError:
        print(f"[!] {PASSWORDS_FILE} not found. Run bulk create first.")
        wait_for_user()
        return

    if not passwords:
        print("[!] No passwords loaded.")
        wait_for_user()
        return

    # Build list of expected emails per panel
    panel_emails = []
    for idx in range(len(configs)):
        names = get_name_list_for_panel(idx, len(configs))
        if not names:
            print(f"[!] No names for panel {idx+1}. Skipping panel.")
            continue
        domain = configs[idx][2]  # domain from panel
        emails = [f"{name}@{domain}".lower() for name in names]
        panel_emails.append(emails)

    # Open report file in write mode (overwrite previous)
    with open(REPORT_FILE, "w", encoding="utf-8") as report_file:
        total_checked = 0
        total_with_messages = 0

        for pidx, (host, user, domain, _) in enumerate(configs):
            if pidx >= len(panel_emails):
                continue
            emails = panel_emails[pidx]
            report_file.write(f"\n--- PANEL {pidx+1}/{len(configs)} : {user} @ {domain} ---\n")
            report_file.flush()   # ensure written immediately
            print(f"\n--- PANEL {pidx+1}/{len(configs)} : {user} @ {domain} ---")

            for email_addr in emails:
                password = passwords.get(email_addr)
                if not password:
                    msg = f"  ⚠ No password for {email_addr}\n"
                    report_file.write(msg)
                    report_file.flush()
                    print(msg.rstrip())
                    continue

                print(f"  📬 Checking {email_addr} ...")
                subjects = fetch_subjects(email_addr, password, domain)
                total_checked += 1
                report_file.write(f"\n=== {email_addr} ===\n")
                if subjects and not subjects[0].startswith("IMAP ERROR"):
                    total_with_messages += 1
                    for subj_idx, subj in enumerate(subjects, 1):
                        report_file.write(f"{subj_idx}. {subj}\n")
                    report_file.write(f"  → Total messages: {len(subjects)}\n")
                    print(f"      → {len(subjects)} subject(s) saved instantly")
                else:
                    error_msg = subjects[0] if subjects else "Unknown error"
                    report_file.write(f"ERROR: {error_msg}\n")
                    print(f"      → {error_msg}")
                report_file.flush()   # force write to disk after each account

    # Final summary (not part of report file, just console)
    print(f"\n✅ Report saved to {REPORT_FILE} (updated instantly during check)")
    print(f"   Total accounts checked: {total_checked}")
    print(f"   Accounts with messages: {total_with_messages}")
    wait_for_user()

# =========================================================
# MAIN MENU
# =========================================================
def main():
    while True:
        clear_console()
        print("=" * 70)
        print("        CPANEL MANAGER (Create/Delete/Forwarders/Check Messages)")
        print("=" * 70)
        print("\n1. Bulk CREATE email accounts (skip existing)")
        print("2. Bulk DELETE email accounts")
        print("3. Delete ALL forwarders (all panels) – live progress")
        print("4. Check messages (IMAP) using passwords.txt – instant save")
        print("5. Exit")
        print("-" * 70)

        choice = input("Select option (1-5): ").strip()
        if choice == "1":
            bulk_create_all_panels()
        elif choice == "2":
            bulk_delete_all_panels()
        elif choice == "3":
            delete_forwarders_all_panels()
        elif choice == "4":
            check_messages_all_panels()
        elif choice == "5":
            print("\n[*] Goodbye!")
            break
        else:
            print("[!] Invalid choice.")
            time.sleep(1)

if __name__ == "__main__":
    main()
