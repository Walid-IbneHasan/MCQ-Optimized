import requests
import logging
from decouple import config
from django.conf import settings

logger = logging.getLogger(__name__)

def send_sms(phone_number: str, message: str) -> dict:
    """
    Send SMS using MIM SMS API.
    """
    api_url = config("SMS_API_URL")
    api_key = config("SMS_API_KEY")
    username = config("SMS_USERNAME")
    sender_id = config("SMS_SENDER_ID")

    # Validate credentials
    if not all([api_key, username, sender_id]):
        error_msg = f"Missing SMS credentials: API_KEY={api_key}, USERNAME={username}, SENDER_ID={sender_id}"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

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
        logger.debug(f"Mim SMS API response for {phone_number}: {result}")
        if isinstance(result, dict) and result.get("status") == "failed":
            logger.error(f"SMS API failed for {phone_number}: {result.get('responseResult', 'Unknown error')}")
            return {"success": False, "error": result.get("responseResult", "Unknown error")}
        logger.info(f"SMS sent successfully to {phone_number}: {result}")
        return {"success": True, "data": result}

    except requests.exceptions.HTTPError as e:
        logger.error(f"SMS API HTTP error for {phone_number}: {str(e)} - Response: {e.response.text}")
        return {"success": False, "error": f"{str(e)} - Response: {e.response.text}"}
    except requests.exceptions.RequestException as e:
        logger.error(f"SMS API error for {phone_number}: {str(e)}")
        return {"success": False, "error": str(e)}
    except Exception as e:
        logger.error(f"Unexpected SMS error for {phone_number}: {str(e)}")
        return {"success": False, "error": "Failed to send SMS"}
