import requests

urls = [
    "https://api.mail.td/email/new",
    "https://api.mail.td/v1/email/new",
    "https://api.mail.td/api/email/new"
]

for url in urls:
    try:
        r = requests.post(url, timeout=10)

        print("\n" + "="*60)
        print("URL:", url)
        print("STATUS:", r.status_code)
        print(r.text[:3000])

    except Exception as e:
        print(url, e)