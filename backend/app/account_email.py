from dataclasses import dataclass

import httpx

from app.config import Settings


class EmailDeliveryError(Exception):
    pass


@dataclass(frozen=True)
class AccountEmail:
    subject: str
    text: str


def send_email(settings: Settings, recipient: str, message: AccountEmail) -> None:
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {settings.resend_api_key.get_secret_value().strip()}"
            },
            json={
                "from": settings.resend_from_email.strip(),
                "to": [recipient],
                "subject": message.subject,
                "text": message.text,
            },
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise EmailDeliveryError from exc
