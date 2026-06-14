import requests
import time
import random
import pyperclip
import os
import sys
from datetime import datetime

# ------------------------------------------------------------------
# Mail.td API client – corrected endpoints
# ------------------------------------------------------------------
API_BASE = "https://api.mail.td"

# Nice random names
FIRST_NAMES = [
    "john", "jane", "alex", "sam", "chris", "pat", "jordan", "casey", "riley", "avery",
    "morgan", "taylor", "jamie", "blake", "drew", "emerson", "finley", "quinn", "sawyer",
    "oliver", "amelia", "liam", "mia", "noah", "isabella", "elijah", "sophia", "lucas"
]
LAST_NAMES = [
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller", "davis",
    "rodriguez", "martinez", "wilson", "anderson", "thomas", "taylor", "moore", "jackson"
]

def generate_username():
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    num = random.randint(10, 999)
    return f"{first}.{last}{num}"

def get_domains():
    """Fetch available domains from API."""
    try:
        resp = requests.get(f"{API_BASE}/v1/domains")
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return [d['domain'] for d in data if 'domain' in d]
            elif isinstance(data, dict) and 'domains' in data:
                return [d['domain'] for d in data['domains']] if data['domains'] else ['mail.td']
        return ['mail.td']
    except:
        return ['mail.td']

def create_email():
    """Create a new temporary email using the mail.td API (correct endpoint)."""
    print("📧 Creating new email...")
    try:
        # Try with custom username (optional)
        username = generate_username()
        resp = requests.post(f"{API_BASE}/v1/email/new", json={"username": username})
        if resp.status_code != 200:
            # Try without username
            resp = requests.post(f"{API_BASE}/v1/email/new")
        resp.raise_for_status()
        data = resp.json()
        email = data.get("email")
        if email and '@' in email:
            print(f"✅ Email created: {email}")
            return email
        raise Exception("Invalid email in response")
    except Exception as e:
        print(f"⚠️ API error: {e}")
        # Fallback: manually build email using a real domain from the API
        domains = get_domains()
        domain = domains[0] if domains else 'mail.td'
        username = generate_username()
        email = f"{username}@{domain}"
        print(f"⚠️ Using fallback email: {email}")
        return email

def fetch_messages(email):
    """Retrieve list of messages for the given email (correct endpoint)."""
    encoded = requests.utils.quote(email)
    url = f"{API_BASE}/v1/email/{encoded}/messages"
    try:
        resp = requests.get(url)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("messages", [])
    except Exception as e:
        print(f"⚠️ Error fetching messages: {e}")
        return []

def fetch_message_content(msg_id):
    """Get full content of a message by its ID (correct endpoint)."""
    url = f"{API_BASE}/v1/message/{msg_id}/content"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return data.get("body") or data.get("text") or data.get("content") or "(No content)"
    except Exception as e:
        return f"⚠️ Could not load content: {e}"

def display_messages(messages):
    """Show a numbered list of messages."""
    if not messages:
        print("📭 Inbox is empty.")
        return
    print("\n📬 INBOX:")
    for i, msg in enumerate(messages, 1):
        subject = msg.get("subject", "(no subject)")
        from_addr = msg.get("from", "unknown")
        date = msg.get("createdAt") or msg.get("date")
        if date:
            try:
                dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
                date_str = dt.strftime("%H:%M:%S")
            except:
                date_str = "recent"
        else:
            date_str = "just now"
        print(f"{i}. {subject[:50]} | from: {from_addr} | {date_str}")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    print("=" * 50)
    print("📧 TempMail.td Python Client (Fixed API)")
    print("=" * 50)
    
    email = create_email()
    pyperclip.copy(email)
    print(f"📋 Email copied to clipboard: {email}")
    
    print("\n⏳ Waiting for messages... (auto-refresh every 5 seconds)")
    print("Commands: [r]efresh, [m] <number>, [c]opy, [n]ew, [q]uit\n")
    
    messages = []
    last_count = 0
    
    try:
        while True:
            time.sleep(5)
            
            new_msgs = fetch_messages(email)
            if len(new_msgs) != last_count:
                messages = new_msgs
                last_count = len(messages)
                clear_screen()
                print(f"📧 Current email: {email}")
                display_messages(messages)
                print("\nCommands: [r]efresh, [m] <num>, [c]opy, [n]ew, [q]uit")
                if messages:
                    print("👉 Type 'm <number>' to read a message.")
            else:
                # heartbeat dot
                print(".", end="", flush=True)
            
            # Non-blocking input check (Windows: msvcrt, Unix: select)
            if os.name == 'nt':
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch().decode('utf-8').lower()
                    if key == 'r':
                        messages = fetch_messages(email)
                        last_count = len(messages)
                        clear_screen()
                        print(f"📧 Current email: {email}")
                        display_messages(messages)
                    elif key == 'c':
                        pyperclip.copy(email)
                        print("\n📋 Email re-copied to clipboard.")
                    elif key == 'n':
                        email = create_email()
                        pyperclip.copy(email)
                        messages = []
                        last_count = 0
                        clear_screen()
                        print(f"📧 New email: {email}")
                        display_messages(messages)
                    elif key == 'q':
                        print("\n👋 Goodbye!")
                        return
                    elif key == 'm':
                        print("\nEnter message number: ", end="")
                        num_input = input().strip()
                        if num_input.isdigit():
                            idx = int(num_input) - 1
                            if 0 <= idx < len(messages):
                                msg = messages[idx]
                                content = fetch_message_content(msg['id'])
                                print(f"\n--- Message from {msg.get('from')} ---")
                                print(f"Subject: {msg.get('subject')}\n")
                                print(content)
                                print("\n--- End of message ---")
                                input("Press Enter to continue...")
                                clear_screen()
                                print(f"📧 Current email: {email}")
                                display_messages(messages)
            else:
                # Unix-like
                import select
                if select.select([sys.stdin], [], [], 0)[0]:
                    cmd = sys.stdin.readline().strip().lower()
                    if cmd == 'r':
                        messages = fetch_messages(email)
                        last_count = len(messages)
                        clear_screen()
                        print(f"📧 Current email: {email}")
                        display_messages(messages)
                    elif cmd == 'c':
                        pyperclip.copy(email)
                        print("\n📋 Email re-copied to clipboard.")
                    elif cmd == 'n':
                        email = create_email()
                        pyperclip.copy(email)
                        messages = []
                        last_count = 0
                        clear_screen()
                        print(f"📧 New email: {email}")
                        display_messages(messages)
                    elif cmd == 'q':
                        print("\n👋 Goodbye!")
                        return
                    elif cmd.startswith('m '):
                        parts = cmd.split()
                        if len(parts) == 2 and parts[1].isdigit():
                            idx = int(parts[1]) - 1
                            if 0 <= idx < len(messages):
                                msg = messages[idx]
                                content = fetch_message_content(msg['id'])
                                print(f"\n--- Message from {msg.get('from')} ---")
                                print(f"Subject: {msg.get('subject')}\n")
                                print(content)
                                print("\n--- End of message ---")
                                input("Press Enter to continue...")
                                clear_screen()
                                print(f"📧 Current email: {email}")
                                display_messages(messages)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()