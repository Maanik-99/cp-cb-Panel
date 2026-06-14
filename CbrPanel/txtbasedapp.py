import os
import json
import secrets
import string
import requests
import urllib3
from pathlib import Path

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Paths relative to this script
BASE_DIR = Path(__file__).parent
SERVERS_FILE = BASE_DIR / "servers.txt"
CONFIG_FILE = BASE_DIR / "config.txt"
OUTPUT_ACCOUNTS_FILE = BASE_DIR / "created_accounts.txt"

def generate_password(length=12):
    """Generates a secure random password."""
    characters = string.ascii_letters + string.digits + "!@#^*-_="
    pwd = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#^*-_=")
    ]
    pwd += [secrets.choice(characters) for _ in range(length - 4)]
    import random
    random.shuffle(pwd)
    return ''.join(pwd)

def login_to_panel(base_url, username, password):
    """Creates a session by logging into CyberPanel."""
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
    """Creates a single email account."""
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
    """Deletes a single email account."""
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
        # Ignore missing e_catchall table error
        if "cyberpanel.e_catchall" in str(error_msg) and "doesn't exist" in str(error_msg):
            return True, "Deleted (ignored table error)"
        return False, error_msg
    except Exception as e:
        return False, str(e)

def setup_email_forwarding(session, base_url, source_email, destinations):
    """Sets up email forwarding for a source account."""
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
    """Fetches all existing forwarding destinations for a source email."""
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
    """Deletes a specific email forwarding rule."""
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

def read_config():
    """Read config.txt and return a dictionary."""
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
    """Read servers.txt (tab-separated: base_url, username, password, domain)"""
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

def process_bulk_creation():
    """Main logic using text files instead of Excel."""
    print("\n--- CyberPanel Email Manager (Text File Mode) ---")
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

    # Load config and servers
    config = read_config()
    if config is None:
        return
    servers = read_servers()
    if servers is None:
        return

    # For forwarding modes, load destinations from emails.txt
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

    total_created = 0
    for server in servers:
        base_url = server['base_url']
        username = server['username']
        password = server['password']
        domain = server['domain']
        if not domain and 'EMAIL_DOMAIN' in config:
            domain = config['EMAIL_DOMAIN']
        if not domain:
            print(f"  [!] Skipping {base_url}: No domain provided (missing in servers.txt and EMAIL_DOMAIN in config.txt)")
            continue

        prefix = config['EMAIL_PREFIX']
        count = config['EMAIL_COUNT']
        batch_size = config['FORWARD_BATCH_SIZE']

        print(f"\n=== Processing {base_url} (domain: {domain}) ===")
        session, login_ok = login_to_panel(base_url, username, password)
        if not login_ok:
            print(f"  [!] Login failed for {username} @ {base_url}")
            continue

        success_count = 0
        fail_count = 0

        # For FORWARD modes, we need to work on a copy of dest_list per server
        # because each server consumes destinations independently.
        if mode in ["FORWARD", "DELETE_FORWARD", "CREATE_AND_FORWARD"]:
            # Copy the global list (but modifications will affect subsequent servers)
            # To avoid inter-server conflict, we'll work on a local copy but also
            # write back to the file after each server. Simpler: keep as global list
            # and update the file after each consumed batch.
            pass  # We will use the global dest_list variable (updated in place)

        for i in range(1, count + 1):
            local_username = f"{prefix}{i}"
            email_address = f"{local_username}@{domain}"

            if mode == "CREATE":
                pwd = generate_password()
                ok, msg = create_cyberpanel_email(session, base_url, domain, local_username, pwd)
                if ok:
                    success_count += 1
                    total_created += 1
                    with open(OUTPUT_ACCOUNTS_FILE, "a") as f:
                        f.write(f"{email_address} | {pwd} | {base_url}\n")
                    print(f"  [+] Created {email_address}")
                elif "already exists" in msg.lower():
                    print(f"  [~] Skipped {email_address} (Already exists)")
                else:
                    fail_count += 1
                    print(f"  [-] Failed {email_address}: {msg}")

            elif mode == "DELETE":
                ok, msg = delete_cyberpanel_email(session, base_url, email_address)
                if ok:
                    success_count += 1
                    print(f"  [x] Deleted {email_address}")
                else:
                    fail_count += 1
                    print(f"  [-] Failed to delete {email_address}: {msg}")

            elif mode == "CREATE_AND_FORWARD":
                pwd = generate_password()
                ok, msg = create_cyberpanel_email(session, base_url, domain, local_username, pwd)
                if ok:
                    success_count += 1
                    total_created += 1
                    with open(OUTPUT_ACCOUNTS_FILE, "a") as f:
                        f.write(f"{email_address} | {pwd} | {base_url}\n")
                    print(f"  [+] Created {email_address}")
                elif "already exists" in msg.lower():
                    print(f"  [~] Skipped {email_address} (Already exists), attempting forwarding")
                else:
                    fail_count += 1
                    print(f"  [-] Failed {email_address}: {msg}")
                    continue

                # Forward immediately
                existing = get_existing_forwards(session, base_url, email_address)
                if existing:
                    print(f"  [~] Already forwarded to {len(existing)} targets, skipping forwarding")
                    continue
                if len(dest_list) < batch_size:
                    print(f"  [!] Not enough destinations left (need {batch_size}, have {len(dest_list)})")
                    break
                batch = dest_list[:batch_size]
                dest_list = dest_list[batch_size:]
                dest_str = ", ".join(batch)
                fwd_ok, fwd_msg = setup_email_forwarding(session, base_url, email_address, dest_str)
                if fwd_ok:
                    print(f"  [>] Forwarded {email_address} -> {len(batch)} targets")
                    with open(USED_TXT, "a") as f:
                        for d in batch:
                            f.write(f"{d}\n")
                    with open(EMAILS_TXT, "w") as f:
                        for d in dest_list:
                            f.write(f"{d}\n")
                else:
                    fail_count += 1
                    print(f"  [-] Failed forward for {email_address}: {fwd_msg}")
                    dest_list = batch + dest_list  # put back

            elif mode == "DELETE_FORWARD_AND_DELETE":
                existing = get_existing_forwards(session, base_url, email_address)
                if existing:
                    print(f"  [.] Found {len(existing)} forwards for {email_address}, deleting...")
                    for dest in existing:
                        d_ok, d_msg = delete_email_forwarding(session, base_url, email_address, dest)
                        if d_ok:
                            print(f"    [x] Deleted: {dest}")
                        else:
                            print(f"    [-] Failed to delete {dest}: {d_msg}")
                else:
                    print(f"  [~] No forwards found for {email_address}")
                del_ok, del_msg = delete_cyberpanel_email(session, base_url, email_address)
                if del_ok:
                    success_count += 1
                    print(f"  [x] Deleted {email_address}")
                else:
                    fail_count += 1
                    print(f"  [-] Failed to delete {email_address}: {del_msg}")

            elif mode == "FORWARD":
                existing = get_existing_forwards(session, base_url, email_address)
                if existing:
                    print(f"  [~] Skipping {email_address} (Already forwarded to {len(existing)} targets)")
                    success_count += 1
                    continue
                if len(dest_list) < batch_size:
                    print(f"  [!] Not enough destinations left (need {batch_size}, have {len(dest_list)})")
                    break
                batch = dest_list[:batch_size]
                dest_list = dest_list[batch_size:]
                dest_str = ", ".join(batch)
                fwd_ok, fwd_msg = setup_email_forwarding(session, base_url, email_address, dest_str)
                if fwd_ok:
                    success_count += 1
                    print(f"  [>] Forwarded {email_address} -> {len(batch)} targets")
                    with open(USED_TXT, "a") as f:
                        for d in batch:
                            f.write(f"{d}\n")
                    with open(EMAILS_TXT, "w") as f:
                        for d in dest_list:
                            f.write(f"{d}\n")
                else:
                    fail_count += 1
                    print(f"  [-] Failed forward for {email_address}: {fwd_msg}")
                    dest_list = batch + dest_list

            elif mode == "DELETE_FORWARD":
                existing = get_existing_forwards(session, base_url, email_address)
                if not existing:
                    print(f"  [~] No forwards found for {email_address}")
                    success_count += 1
                    continue
                print(f"  [.] Found {len(existing)} forwards for {email_address}, deleting...")
                for dest in existing:
                    d_ok, d_msg = delete_email_forwarding(session, base_url, email_address, dest)
                    if d_ok:
                        print(f"    [x] Deleted: {dest}")
                    else:
                        print(f"    [-] Failed to delete {dest}: {d_msg}")
                success_count += 1

        print(f"  Summary for {base_url}: Success: {success_count}, Fail: {fail_count}")

    print(f"\nFinished! Total accounts created across all servers: {total_created}")
    if total_created > 0:
        print(f"Credentials saved to: {OUTPUT_ACCOUNTS_FILE.name}")

if __name__ == "__main__":
    process_bulk_creation()