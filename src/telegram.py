import requests

def send_message(token: str, chat_id: str, text: str) -> None:
    api = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        api,
        data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=30,
    )
    r.raise_for_status()
