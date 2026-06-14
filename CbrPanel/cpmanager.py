import os
import json
import secrets
import string
import random
import re
import requests
import urllib3
from pathlib import Path

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_DIR = Path(__file__).parent
SERVERS_FILE = BASE_DIR / "servers.txt"
CONFIG_FILE = BASE_DIR / "config.txt"
OUTPUT_ACCOUNTS_FILE = BASE_DIR / "created_accounts.txt"
REPORT_FILE = BASE_DIR / "report.txt"

# -------------------------------------------------------------------
# Helper functions (login, create, delete, forward)
# -------------------------------------------------------------------

def generate_password(length=12):
    characters = string.ascii_letters + string.digits + "!@#^*-_="
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#^*-_=")
    ]
    pwd += [secrets.choice(characters) for _ in range(length - 4)]
    random.shuffle(pwd)
    return ''.join(pwd)

def login_to_panel(base_url, username, password):
    session = requests.Session()
    session.verify = False
    try:
        if base_url.endswith('/'):
            base_url = base_url[:-1]
        login_page = f"{base_url}/login"
        session.get(login_page, timeout=20)
        csrf = session.cookies.get("csrftoken", "")
        headers = {
            "X-CSRFToken": csrf,
            "Referer": login_page,
            "Origin": base_url,
            "User-Agent": "Mozilla/5.0",
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/json"
        }
        payload = {
            "username": username,
            "password": password,
            "languageSelection": "english"
        }
        response = session.post(
            f"{base_url}/verifyLogin",
            headers=headers,
            json=payload,
            timeout=20
        )
        text = response.text.lower()
        if '"loginstatus": 1' in text or '"loginstatus":1' in text:
            return session, True
        return None, False
    except Exception as e:
        print(f"  [!] Login Error: {str(e)}")
        return None, False

def create_cyberpanel_email(session, base_url, domain, username, password):
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    create_email_url = f"{base_url}/email/submitEmailCreation"
    cookies_dict = session.cookies.get_dict()
    csrf_token = cookies_dict.get('csrftoken', '')
    headers = {
        'X-CSRFToken': csrf_token,
        'Referer': f"{base_url}/email/createEmailAccount/",
        'Origin': base_url,
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest'
    }
    payload = {
        'domain': domain,
        'username': username,
        'passwordByPass': password,
        'quota': '0',
        'controller': 'submitEmailCreation'
    }
    try:
        response = session.post(create_email_url, headers=headers, json=payload, timeout=15)
        if "login" in response.url.lower() or response.status_code == 403:
            return False, "Session expired or invalid."
        result = response.json()
        if result.get('status') == 1:
            return True, "Success"
        return False, result.get('error_message', 'Unknown error')
    except Exception as e:
        return False, f"Request Error: {str(e)}"

def delete_cyberpanel_email(session, base_url, email_address):
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    delete_url = f"{base_url}/email/submitEmailDeletion"
    cookies_dict = session.cookies.get_dict()
    csrf_token = cookies_dict.get('csrftoken', '')
    headers = {
        'X-CSRFToken': csrf_token,
        'Referer': f"{base_url}/email/createEmailAccount/",
        'Origin': base_url,
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest'
    }
    payload = {
        'email': email_address,
        'controller': 'submitEmailDeletion'
    }
    try:
        response = session.post(delete_url, headers=headers, json=payload, timeout=15)
        result = response.json()
        if result.get('status') == 1:
            return True, "Deleted"
        error_msg = result.get('error_message', 'Unknown error')
        if "cyberpanel.e_catchall" in str(error_msg) and "doesn't exist" in str(error_msg):
            return True, "Deleted (ignored table error)"
        return False, error_msg
    except Exception as e:
        return False, str(e)

def setup_email_forwarding(session, base_url, source_email, destinations):
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    forward_url = f"{base_url}/email/submitEmailForwardingCreation"
    cookies_dict = session.cookies.get_dict()
    csrf_token = cookies_dict.get('csrftoken', '')
    headers = {
        'X-CSRFToken': csrf_token,
        'Referer': f"{base_url}/email/createEmailAccount/",
        'Origin': base_url,
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest'
    }
    payload = {
        'source': source_email,
        'destination': destinations,
        'forwardingOption': 'Forward to email',
        'controller': 'submitEmailForwardingCreation'
    }
    try:
        response = session.post(forward_url, headers=headers, json=payload, timeout=15)
        result = response.json()
        if result.get('status') == 1:
            return True, "Forwarded"
        return False, result.get('error_message', 'Unknown error')
    except Exception as e:
        return False, str(e)

def get_existing_forwards(session, base_url, source_email):
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    fetch_url = f"{base_url}/email/fetchCurrentForwardings"
    cookies_dict = session.cookies.get_dict()
    csrf_token = cookies_dict.get('csrftoken', '')
    headers = {
        'X-CSRFToken': csrf_token,
        'Referer': f"{base_url}/email/createEmailAccount/",
        'Origin': base_url,
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest'
    }
    payload = {
        'emailAddress': source_email,
        'forwardingOption': 'Forward to email',
        'controller': 'fetchCurrentForwardings'
    }
    try:
        response = session.post(fetch_url, headers=headers, json=payload, timeout=10)
        result = response.json()
        if result.get('status') == 1:
            raw_data = result.get('data', '[]')
            if isinstance(raw_data, str):
                parsed_list = json.loads(raw_data) if raw_data else []
            else:
                parsed_list = raw_data
            return [item.get('destination') for item in parsed_list if isinstance(item, dict) and 'destination' in item]
        return []
    except Exception:
        return []

def delete_email_forwarding(session, base_url, source_email, destination):
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    delete_url = f"{base_url}/email/submitForwardDeletion"
    cookies_dict = session.cookies.get_dict()
    csrf_token = cookies_dict.get('csrftoken', '')
    headers = {
        'X-CSRFToken': csrf_token,
        'Referer': f"{base_url}/email/createEmailAccount/",
        'Origin': base_url,
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/json; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest'
    }
    payload = {
        'source': source_email,
        'destination': destination,
        'forwardingOption': 'Forward to email',
        'controller': 'submitForwardDeletion'
    }
    try:
        response = session.post(delete_url, headers=headers, json=payload, timeout=15)
        result = response.json()
        if result.get('status') == 1:
            return True, "Deleted"
        return False, result.get('error_message', 'Unknown error')
    except Exception as e:
        return False, str(e)

# -------------------------------------------------------------------
# Config & servers
# -------------------------------------------------------------------

def read_config():
    config = {}
    if not CONFIG_FILE.exists():
        print(f"ERROR: {CONFIG_FILE.name} not found.")
        return None
    with open(CONFIG_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    required = ['EMAIL_PREFIX', 'EMAIL_COUNT']
    for req in required:
        if req not in config:
            print(f"ERROR: Missing '{req}' in {CONFIG_FILE.name}")
            return None
    try:
        config['EMAIL_COUNT'] = int(config['EMAIL_COUNT'])
    except ValueError:
        print("ERROR: EMAIL_COUNT must be an integer.")
        return None
    if 'FORWARD_BATCH_SIZE' in config:
        try:
            config['FORWARD_BATCH_SIZE'] = int(config['FORWARD_BATCH_SIZE'])
        except ValueError:
            print("WARNING: FORWARD_BATCH_SIZE invalid, using default 4.")
            config['FORWARD_BATCH_SIZE'] = 4
    else:
        config['FORWARD_BATCH_SIZE'] = 4
    return config

def read_servers():
    servers = []
    if not SERVERS_FILE.exists():
        print(f"ERROR: {SERVERS_FILE.name} not found.")
        return None
    with open(SERVERS_FILE, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                print(f"WARNING: Line {line_num} in {SERVERS_FILE.name} has <3 columns, skipping.")
                continue
            base_url = parts[0].strip()
            username = parts[1].strip()
            password = parts[2].strip()
            domain = parts[3].strip() if len(parts) >= 4 else None
            servers.append({
                'base_url': base_url,
                'username': username,
                'password': password,
                'domain': domain
            })
    if not servers:
        print(f"ERROR: No valid server entries found in {SERVERS_FILE.name}")
        return None
    return servers

# -------------------------------------------------------------------
# Report handling (robust parse & update)
# -------------------------------------------------------------------

def load_report_stats():
    """Return dict: {domain: {'create':int, 'forward':int, 'delete_acc':int, 'delete_forward':int}}"""
    stats = {}
    if not REPORT_FILE.exists():
        return stats
    with open(REPORT_FILE, 'r') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Expected: domain Create-40 forward-40 delete acc-40 delete forward-40
            # Use regex to extract numbers
            match = re.match(r'^(\S+)\s+Create-(\d+)\s+forward-(\d+)\s+delete\s+acc-(\d+)\s+delete\s+forward-(\d+)$', line)
            if match:
                domain = match.group(1)
                stats[domain] = {
                    'create': int(match.group(2)),
                    'forward': int(match.group(3)),
                    'delete_acc': int(match.group(4)),
                    'delete_forward': int(match.group(5))
                }
            else:
                # fallback: simple split
                parts = line.split()
                if len(parts) >= 8:
                    domain = parts[0]
                    try:
                        create_val = int(parts[1].split('-')[1])
                        forward_val = int(parts[2].split('-')[1])
                        delete_acc_val = int(parts[4].split('-')[1])  # "acc-40"
                        delete_forward_val = int(parts[6].split('-')[1])  # "forward-40"
                        stats[domain] = {
                            'create': create_val,
                            'forward': forward_val,
                            'delete_acc': delete_acc_val,
                            'delete_forward': delete_forward_val
                        }
                    except (IndexError, ValueError):
                        continue
    return stats

def update_report(domain, operation, new_count):
    """
    Update the report file for a specific domain and operation.
    operation: 'create', 'forward', 'delete_acc', 'delete_forward'
    """
    stats = load_report_stats()
    if domain not in stats:
        stats[domain] = {'create': 0, 'forward': 0, 'delete_acc': 0, 'delete_forward': 0}
    stats[domain][operation] = new_count

    # Write back
    with open(REPORT_FILE, 'w') as f:
        for dom, cnt in stats.items():
            line = (f"{dom} Create-{cnt['create']} forward-{cnt['forward']} "
                    f"delete acc-{cnt['delete_acc']} delete forward-{cnt['delete_forward']}")
            f.write(line + "\n")

# -------------------------------------------------------------------
# Main processing (modes 1-6, each reads report to resume)
# -------------------------------------------------------------------

def process_bulk_creation():
    print("\n--- CyberPanel Email Manager (Resume from report.txt) ---")
    print("1. Create accounts")
    print("2. Delete accounts")
    print("3. Setup Forwarding")
    print("4. Delete Forwarding (All)")
    print("5. Create + Forward (same run)")
    print("6. Delete forwarding + delete account")
    choice = input("Select an option (1-6): ").strip()
    if choice not in ['1', '2', '3', '4', '5', '6']:
        print("Invalid choice. Exiting.")
        return

    mode_map = {
        '1': "CREATE",
        '2': "DELETE",
        '3': "FORWARD",
        '4': "DELETE_FORWARD",
        '5': "CREATE_AND_FORWARD",
        '6': "DELETE_FORWARD_AND_DELETE",
    }
    mode = mode_map[choice]
    print(f"\nMode: {mode}")

    config = read_config()
    if not config:
        return
    servers = read_servers()
    if not config or not servers:
        return

    # For forwarding modes, load destinations
    if mode in ["FORWARD", "DELETE_FORWARD", "CREATE_AND_FORWARD"]:
        EMAILS_TXT = BASE_DIR / "emails.txt"
        USED_TXT = BASE_DIR / "used.txt"
        if not EMAILS_TXT.exists():
            print(f"ERROR: {EMAILS_TXT.name} not found.")
            return
        with open(EMAILS_TXT, "r") as f:
            dest_list = [line.strip() for line in f if line.strip()]
        if not dest_list:
            print("ERROR: emails.txt is empty.")
            return
    else:
        dest_list = []

    total_created_global = 0
    # Load initial report stats (will be refreshed per domain if needed, but we use update_report function)
    # We'll maintain local counters per domain to avoid stale reads.

    for server in servers:
        base_url = server['base_url']
        username = server['username']
        password = server['password']
        domain = server['domain']
        if not domain and 'EMAIL_DOMAIN' in config:
            domain = config['EMAIL_DOMAIN']
        if not domain:
            print(f"  [!] Skipping {base_url}: No domain provided.")
            continue

        prefix = config['EMAIL_PREFIX']
        total_required = config['EMAIL_COUNT']
        batch_size = config['FORWARD_BATCH_SIZE']

        # Load current report stats for this domain
        report_stats = load_report_stats()
        domain_stats = report_stats.get(domain, {'create':0, 'forward':0, 'delete_acc':0, 'delete_forward':0})

        if mode == "CREATE":
            already_done = domain_stats['create']
        elif mode == "DELETE":
            already_done = domain_stats['delete_acc']
        elif mode == "FORWARD":
            already_done = domain_stats['forward']
        elif mode == "DELETE_FORWARD":
            already_done = domain_stats['delete_forward']
        elif mode == "CREATE_AND_FORWARD":
            already_done = domain_stats['create']   # use create count to resume
        elif mode == "DELETE_FORWARD_AND_DELETE":
            already_done = domain_stats['delete_acc']   # resume from where account deletion left off
        else:
            already_done = 0

        if already_done >= total_required:
            print(f"\n=== {domain} already fully processed for mode {mode} ({already_done}/{total_required}) ===")
            continue

        print(f"\n=== Processing {domain} (already done: {already_done}, target: {total_required}) ===")
        session, login_ok = login_to_panel(base_url, username, password)
        if not login_ok:
            print(f"  Login failed for {base_url}")
            continue

        # Local counters for this domain (start from already_done)
        create_count = domain_stats['create']
        forward_count = domain_stats['forward']
        delete_acc_count = domain_stats['delete_acc']
        delete_forward_count = domain_stats['delete_forward']

        success_in_this_run = 0
        fail_in_this_run = 0

        # Loop from already_done+1 to total_required
        for i in range(already_done + 1, total_required + 1):
            local_username = f"{prefix}{i}"
            email_address = f"{local_username}@{domain}"

            # ------------------------------------------------------------
            # MODE 1: CREATE
            # ------------------------------------------------------------
            if mode == "CREATE":
                pwd = generate_password()
                ok, msg = create_cyberpanel_email(session, base_url, domain, local_username, pwd)
                if ok:
                    create_count += 1
                    success_in_this_run += 1
                    total_created_global += 1
                    with open(OUTPUT_ACCOUNTS_FILE, "a") as f:
                        f.write(f"{email_address} | {pwd} | {base_url}\n")
                    print(f"  [+] Created {email_address} ({create_count}/{total_required})")
                    update_report(domain, 'create', create_count)
                elif "already exists" in msg.lower():
                    create_count += 1
                    success_in_this_run += 1
                    print(f"  [~] {email_address} already exists, counted.")
                    update_report(domain, 'create', create_count)
                else:
                    fail_in_this_run += 1
                    print(f"  [-] Failed {email_address}: {msg}")
                    continue

            # ------------------------------------------------------------
            # MODE 2: DELETE
            # ------------------------------------------------------------
            elif mode == "DELETE":
                ok, msg = delete_cyberpanel_email(session, base_url, email_address)
                if ok:
                    delete_acc_count += 1
                    success_in_this_run += 1
                    print(f"  [x] Deleted {email_address} ({delete_acc_count}/{total_required})")
                    update_report(domain, 'delete_acc', delete_acc_count)
                else:
                    fail_in_this_run += 1
                    print(f"  [-] Failed to delete {email_address}: {msg}")

            # ------------------------------------------------------------
            # MODE 3: FORWARD (only)
            # ------------------------------------------------------------
            elif mode == "FORWARD":
                existing = get_existing_forwards(session, base_url, email_address)
                if existing:
                    print(f"  [~] {email_address} already forwarded to {len(existing)} targets, counting.")
                    forward_count += 1
                    success_in_this_run += 1
                    update_report(domain, 'forward', forward_count)
                    continue
                if len(dest_list) < batch_size:
                    print(f"  [!] Not enough destinations left (need {batch_size}, have {len(dest_list)}). Stopping for this server.")
                    break
                batch = dest_list[:batch_size]
                dest_list = dest_list[batch_size:]
                dest_str = ", ".join(batch)
                fwd_ok, fwd_msg = setup_email_forwarding(session, base_url, email_address, dest_str)
                if fwd_ok:
                    forward_count += 1
                    success_in_this_run += 1
                    print(f"  [>] Forwarded {email_address} -> {len(batch)} targets ({forward_count}/{total_required})")
                    update_report(domain, 'forward', forward_count)
                    with open(USED_TXT, "a") as f:
                        for d in batch:
                            f.write(f"{d}\n")
                    with open(EMAILS_TXT, "w") as f:
                        for d in dest_list:
                            f.write(f"{d}\n")
                else:
                    fail_in_this_run += 1
                    print(f"  [-] Failed forward for {email_address}: {fwd_msg}")
                    dest_list = batch + dest_list

            # ------------------------------------------------------------
            # MODE 4: DELETE FORWARD (only)
            # ------------------------------------------------------------
            elif mode == "DELETE_FORWARD":
                existing = get_existing_forwards(session, base_url, email_address)
                if not existing:
                    print(f"  [~] No forwards found for {email_address}, counting as done.")
                    delete_forward_count += 1
                    success_in_this_run += 1
                    update_report(domain, 'delete_forward', delete_forward_count)
                    continue
                all_ok = True
                for dest in existing:
                    d_ok, d_msg = delete_email_forwarding(session, base_url, email_address, dest)
                    if d_ok:
                        print(f"    [x] Deleted forward: {dest}")
                    else:
                        print(f"    [-] Failed to delete {dest}: {d_msg}")
                        all_ok = False
                if all_ok:
                    delete_forward_count += 1
                    success_in_this_run += 1
                    update_report(domain, 'delete_forward', delete_forward_count)
                else:
                    fail_in_this_run += 1

            # ------------------------------------------------------------
            # MODE 5: CREATE + FORWARD
            # ------------------------------------------------------------
            elif mode == "CREATE_AND_FORWARD":
                # Create
                pwd = generate_password()
                ok, msg = create_cyberpanel_email(session, base_url, domain, local_username, pwd)
                if ok:
                    create_count += 1
                    success_in_this_run += 1
                    total_created_global += 1
                    with open(OUTPUT_ACCOUNTS_FILE, "a") as f:
                        f.write(f"{email_address} | {pwd} | {base_url}\n")
                    print(f"  [+] Created {email_address} ({create_count}/{total_required})")
                    update_report(domain, 'create', create_count)
                elif "already exists" in msg.lower():
                    create_count += 1
                    success_in_this_run += 1
                    print(f"  [~] {email_address} already exists, counted.")
                    update_report(domain, 'create', create_count)
                else:
                    fail_in_this_run += 1
                    print(f"  [-] Failed {email_address}: {msg}")
                    continue

                # Forward
                existing = get_existing_forwards(session, base_url, email_address)
                if existing:
                    print(f"  [~] Already forwarded, counting.")
                    forward_count += 1
                    update_report(domain, 'forward', forward_count)
                else:
                    if len(dest_list) < batch_size:
                        print(f"  [!] Not enough destinations left. Stopping forward for this server.")
                        break
                    batch = dest_list[:batch_size]
                    dest_list = dest_list[batch_size:]
                    dest_str = ", ".join(batch)
                    fwd_ok, fwd_msg = setup_email_forwarding(session, base_url, email_address, dest_str)
                    if fwd_ok:
                        forward_count += 1
                        print(f"  [>] Forwarded {email_address} -> {len(batch)} targets")
                        update_report(domain, 'forward', forward_count)
                        with open(USED_TXT, "a") as f:
                            for d in batch:
                                f.write(f"{d}\n")
                        with open(EMAILS_TXT, "w") as f:
                            for d in dest_list:
                                f.write(f"{d}\n")
                    else:
                        fail_in_this_run += 1
                        print(f"  [-] Failed forward for {email_address}: {fwd_msg}")
                        dest_list = batch + dest_list

            # ------------------------------------------------------------
            # MODE 6: DELETE FORWARD + DELETE ACCOUNT
            # ------------------------------------------------------------
            elif mode == "DELETE_FORWARD_AND_DELETE":
                # ---- Step A: Delete all forwards ----
                existing = get_existing_forwards(session, base_url, email_address)
                if not existing:
                    print(f"  [~] No forwards to delete for {email_address}")
                    # Still count as success for forward deletion
                    delete_forward_count += 1
                    update_report(domain, 'delete_forward', delete_forward_count)
                else:
                    all_ok = True
                    for dest in existing:
                        d_ok, d_msg = delete_email_forwarding(session, base_url, email_address, dest)
                        if d_ok:
                            print(f"    [x] Deleted forward: {dest}")
                        else:
                            print(f"    [-] Failed to delete {dest}: {d_msg}")
                            all_ok = False
                    if all_ok:
                        delete_forward_count += 1
                        update_report(domain, 'delete_forward', delete_forward_count)
                    else:
                        # If forward deletion fails, do not proceed to account deletion for this account
                        fail_in_this_run += 1
                        print(f"  [!] Forward deletion incomplete for {email_address}, skipping account deletion.")
                        continue

                # ---- Step B: Delete the account ----
                del_ok, del_msg = delete_cyberpanel_email(session, base_url, email_address)
                if del_ok:
                    delete_acc_count += 1
                    success_in_this_run += 1
                    print(f"  [x] Deleted account {email_address} ({delete_acc_count}/{total_required})")
                    update_report(domain, 'delete_acc', delete_acc_count)
                else:
                    fail_in_this_run += 1
                    print(f"  [-] Failed to delete account {email_address}: {del_msg}")

        # End of for loop for this domain
        print(f"  Summary for {domain}: New successes: {success_in_this_run}, Failures: {fail_in_this_run}")

    # After all servers
    if mode in ["CREATE", "CREATE_AND_FORWARD"]:
        print(f"\nFinished! Total accounts created across all servers: {total_created_global}")
        if total_created_global > 0:
            print(f"Credentials saved to: {OUTPUT_ACCOUNTS_FILE.name}")
    else:
        print("\nOperation completed.")

if __name__ == "__main__":
    process_bulk_creation()
