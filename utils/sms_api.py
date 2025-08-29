import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


def send_sms(phone_number: str, message: str) -> dict:
    """
    Send SMS using MIM SMS API.
    """
    api_url = settings.SMS_API_URL
    api_key = settings.SMS_API_KEY
    username = settings.SMS_USERNAME
    sender_id = settings.SMS_SENDER_ID

    payload = {
        "UserName": username,
        "Apikey": api_key,
        "MobileNumber": phone_number,
        "CampaignId": "null",
        "SenderName": sender_id,
        "TransactionType": "T",
        "Message": message,
    }

    try:
        response = requests.post(api_url, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        logger.info(f"SMS sent successfully to {phone_number}")
        return {"success": True, "data": result}

    except requests.exceptions.RequestException as e:
        logger.error(f"SMS API error: {str(e)}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected SMS error: {str(e)}")
        return {"success": False, "error": "Failed to send SMS"}
