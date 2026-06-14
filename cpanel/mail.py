import os
import json
import secrets
import string
import requests
import urllib3
import imaplib
import email
import time
import re
import webbrowser
import pyperclip
import keyboard
from email.header import decode_header
from pathlib import Path

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Paths
BASE_DIR = Path(__file__).parent
SERVERS_FILE = BASE_DIR / "servers.txt"
CONFIG_FILE = BASE_DIR / "config.txt"
OUTPUT_ACCOUNTS_FILE = BASE_DIR / "created_accounts.txt"
CURRENT_ACCOUNT_FILE = BASE_DIR / "current_account.txt"   # stores the active random account

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

def generate_random_username(length=8):
    """Generate a random username (lowercase letters and digits)."""
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

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
        if "cyberpanel.e_catchall" in str(error_msg) and "doesn't exist" in str(error_msg):
            return True, "Deleted (ignored table error)"
        return False, error_msg
    except Exception as e:
        return False, str(e)

def imap_connect(server, port, use_ssl, email_address, password):
    """Connect to IMAP server and return the connection object."""
    try:
        if use_ssl:
            imap = imaplib.IMAP4_SSL(server, port, timeout=10)
        else:
            imap = imaplib.IMAP4(server, port, timeout=10)
        imap.login(email_address, password)
        return imap
    except ConnectionRefusedError:
        print(f"  [!] IMAP connection failed: Server refused connection at {server}:{port}")
        print(f"     Check that the IMAP server address is correct in config.txt")
        return None
    except TimeoutError:
        print(f"  [!] IMAP connection timed out: {server}:{port} did not respond within 10 seconds")
        return None
    except Exception as e:
        print(f"  [!] IMAP connection failed: {e}")
        return None

def read_inbox(imap_conn, limit=10, verification_opened=False):
    """Fetch and display recent emails from INBOX."""
    try:
        imap_conn.select("INBOX")
        status, messages = imap_conn.search(None, "ALL")
        if status != "OK":
            print("  [-] Could not search emails.")
            return verification_opened
        msg_ids = messages[0].split()
        if not msg_ids:
            print("  [~] Inbox is empty.")
            return verification_opened
        # show most recent 'limit' emails
        for num in msg_ids[-limit:]:
            status, data = imap_conn.fetch(num, "(RFC822)")
            if status != "OK":
                continue
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            subject, encoding = decode_header(msg.get("Subject", "(no subject)"))[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding or "utf-8", errors="ignore")
            from_ = msg.get("From", "unknown")
            date = msg.get("Date", "unknown")
            print(f"\n  📧 From: {from_}")
            print(f"     Date: {date}")
            print(f"     Subject: {subject}")
            
            # Extract body and links
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
                    elif part.get_content_type() == "text/html":
                        body = part.get_payload(decode=True).decode(errors="ignore")
            else:
                body = msg.get_payload(decode=True).decode(errors="ignore")
            
            # Extract all links
            links = re.findall(r'https?://[^\s\)<>"]+', body)
            
            # Show preview
            print(f"     Preview: {body[:200]}...")
            
            # Open verification link ONLY if not already opened for this account
            if not verification_opened and links:
                for link in links:
                    # Check if it's a verification link
                    if any(keyword in link.lower() for keyword in ['verify', 'confirm', 'activate', 'signnow']):
                        print(f"\n     [🔗] Verification Link:")
                        print(f"        {link}")
                        print(f"        [→] Opening verification link...")
                        webbrowser.open(link)
                        time.sleep(2)
                        verification_opened = True
                        break  # Only open first verification link found
            print()
    except Exception as e:
        print(f"  [!] Error reading inbox: {e}")
    return verification_opened

def delete_previous_account(session, base_url):
    """Delete the account stored in CURRENT_ACCOUNT_FILE (if any)."""
    if not CURRENT_ACCOUNT_FILE.exists():
        return
    with open(CURRENT_ACCOUNT_FILE, "r") as f:
        data = json.load(f)
    email_address = data.get("email")
    if email_address:
        print(f"  [.] Deleting previous account: {email_address}")
        ok, msg = delete_cyberpanel_email(session, base_url, email_address)
        if ok:
            print(f"  [x] Deleted {email_address}")
        else:
            print(f"  [-] Failed to delete {email_address}: {msg}")
    CURRENT_ACCOUNT_FILE.unlink(missing_ok=True)

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
    # Required keys for standard modes
    if 'EMAIL_PREFIX' not in config:
        config['EMAIL_PREFIX'] = "temp"  # fallback, but random mode doesn't use it
    if 'EMAIL_COUNT' not in config:
        config['EMAIL_COUNT'] = "1"
    try:
        config['EMAIL_COUNT'] = int(config['EMAIL_COUNT'])
    except ValueError:
        config['EMAIL_COUNT'] = 1
    # IMAP settings (optional)
    config['IMAP_SERVER'] = config.get('IMAP_SERVER', '')
    config['IMAP_PORT'] = int(config.get('IMAP_PORT', 993))
    config['IMAP_USE_SSL'] = config.get('IMAP_USE_SSL', 'True').lower() == 'true'
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
    """Main logic - Random account cycle only."""
    print("\n=== Random Account Manager ===\n")

    # Load config and servers
    config = read_config()
    if config is None:
        return
    servers = read_servers()
    if servers is None:
        return

    # Use first server
    server = servers[0]
    base_url = server['base_url']
    admin_user = server['username']
    admin_pass = server['password']
    domain = server['domain'] or config.get('EMAIL_DOMAIN')
    if not domain:
        print("ERROR: No domain found in servers.txt or config.txt")
        return

    # Login
    session, ok = login_to_panel(base_url, admin_user, admin_pass)
    if not ok:
        print("[!] Login failed.")
        return

    # Delete previous account
    delete_previous_account(session, base_url)

    # Create new random account
    random_user = generate_random_username(10)
    random_pass = generate_password(14)
    email_full = f"{random_user}@{domain}"
    print(f"[+] Creating: {email_full}")
    success, msg = create_cyberpanel_email(session, base_url, domain, random_user, random_pass)
    if not success:
        print(f"[-] Creation failed: {msg}")
        return

    # Save current account
    with open(CURRENT_ACCOUNT_FILE, "w") as f:
        json.dump({"email": email_full, "password": random_pass, "server": base_url}, f, indent=2)
    with open(OUTPUT_ACCOUNTS_FILE, "a") as f:
        f.write(f"{email_full} | {random_pass} | {base_url}\n")
    print(f"[✓] Created: {email_full}")
    print(f"    Pass: {random_pass}\n")
    
    # Auto-copy account to clipboard
    try:
        pyperclip.copy(email_full)
        print(f"[✓] Account copied to clipboard!")
    except Exception as e:
        print(f"[!] Could not copy to clipboard: {e}")

    # Read emails
    imap_server = config['IMAP_SERVER']
    if not imap_server:
        imap_server = f"mail.{domain}"
    imap_port = config['IMAP_PORT']
    use_ssl = config['IMAP_USE_SSL']
    imap_conn = imap_connect(imap_server, imap_port, use_ssl, email_full, random_pass)
    if imap_conn:
        print("\n--- Waiting for Emails (Press Alt+C for New Account) ---\n")
        verification_opened = False  # Track if verification link opened for this account
        try:
            while True:
                verification_opened = read_inbox(imap_conn, limit=10, verification_opened=verification_opened)
                print("[*] Checking again in 5 seconds... Press Alt+C for new account\n")
                
                # Check for Alt+C press during 5 second wait
                for i in range(50):  # 50 * 0.1 = 5 seconds
                    if keyboard.is_pressed('alt+c'):
                        print("\n[*] Alt+C detected! Creating new account...")
                        if imap_conn:
                            try:
                                imap_conn.close()
                                imap_conn.logout()
                            except:
                                pass
                        # Recursively call to create new account
                        process_bulk_creation()
                        return
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[*] Stopped.")
            if imap_conn:
                try:
                    imap_conn.close()
                    imap_conn.logout()
                except:
                    pass
    else:
        print("[!] IMAP connection failed.")

if __name__ == "__main__":
    process_bulk_creation()