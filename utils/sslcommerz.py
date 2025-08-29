import requests
import hashlib
import logging
from django.conf import settings
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SSLCommerzGateway:
    """
    SSLCommerz payment gateway integration.
    """

    def __init__(self):
        self.store_id = settings.SSLCOMMERZ_STORE_ID
        self.store_password = settings.SSLCOMMERZ_STORE_PASSWORD
        self.is_sandbox = settings.SSLCOMMERZ_IS_SANDBOX

        if self.is_sandbox:
            self.base_url = "https://sandbox.sslcommerz.com"
        else:
            self.base_url = "https://securepay.sslcommerz.com"

    def create_payment_session(self, payment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a payment session with SSLCommerz.
        """
        url = f"{self.base_url}/gwprocess/v4/api.php"

        # Required fields
        data = {
            "store_id": self.store_id,
            "store_passwd": self.store_password,
            "total_amount": payment_data["amount"],
            "currency": "BDT",
            "tran_id": payment_data["transaction_id"],
            "success_url": payment_data["success_url"],
            "fail_url": payment_data["fail_url"],
            "cancel_url": payment_data["cancel_url"],
            "ipn_url": payment_data.get("ipn_url", ""),
            # Customer information
            "cus_name": payment_data["customer_name"],
            "cus_email": payment_data["customer_email"],
            "cus_add1": payment_data.get("customer_address", "N/A"),
            "cus_city": payment_data.get("customer_city", "Dhaka"),
            "cus_country": payment_data.get("customer_country", "Bangladesh"),
            "cus_phone": payment_data["customer_phone"],
            # Product information
            "product_name": payment_data["product_name"],
            "product_category": payment_data.get("product_category", "Subscription"),
            "product_profile": payment_data.get("product_profile", "general"),
            # Shipping information (required by SSLCommerz)
            "shipping_method": "NO",
            "num_of_item": 1,
        }

        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()

            result = response.json()

            if result.get("status") == "SUCCESS":
                logger.info(
                    f"Payment session created: {payment_data['transaction_id']}"
                )
                return {
                    "success": True,
                    "gateway_url": result["GatewayPageURL"],
                    "session_key": result.get("sessionkey", ""),
                    "data": result,
                }
            else:
                logger.error(
                    f"Payment session failed: {result.get('failedreason', 'Unknown error')}"
                )
                return {
                    "success": False,
                    "error": result.get(
                        "failedreason", "Payment session creation failed"
                    ),
                }

        except requests.exceptions.RequestException as e:
            logger.error(f"SSLCommerz API error: {str(e)}")
            return {"success": False, "error": "Payment gateway connection failed"}
        except Exception as e:
            logger.error(f"Unexpected payment error: {str(e)}")
            return {"success": False, "error": "Payment processing failed"}

    def validate_payment(self, transaction_id: str, amount: float) -> Dict[str, Any]:
        """
        Validate payment with SSLCommerz.
        """
        url = f"{self.base_url}/validator/api/validationserverAPI.php"

        data = {
            "store_id": self.store_id,
            "store_passwd": self.store_password,
            "val_id": transaction_id,
        }

        try:
            response = requests.get(url, params=data, timeout=30)
            response.raise_for_status()

            result = response.json()

            if result.get("status") == "VALID":
                # Verify amount matches
                if float(result.get("amount", 0)) == float(amount):
                    logger.info(f"Payment validated: {transaction_id}")
                    return {"success": True, "data": result}
                else:
                    logger.warning(f"Payment amount mismatch: {transaction_id}")
                    return {"success": False, "error": "Payment amount mismatch"}
            else:
                logger.warning(f"Payment validation failed: {transaction_id}")
                return {"success": False, "error": "Payment validation failed"}

        except requests.exceptions.RequestException as e:
            logger.error(f"Payment validation API error: {str(e)}")
            return {"success": False, "error": "Payment validation failed"}
        except Exception as e:
            logger.error(f"Unexpected validation error: {str(e)}")
            return {"success": False, "error": "Payment validation failed"}

    def verify_webhook_hash(self, post_data: Dict[str, str]) -> bool:
        """
        Verify webhook hash from SSLCommerz.
        """
        try:
            received_hash = post_data.get("verify_sign", "")
            if not received_hash:
                return False

            # Create hash string
            hash_string = f"{self.store_password}"
            for key in sorted(post_data.keys()):
                if key != "verify_sign":
                    hash_string += f"{key}={post_data[key]}&"

            hash_string = hash_string.rstrip("&")
            calculated_hash = hashlib.md5(hash_string.encode()).hexdigest()

            return calculated_hash.upper() == received_hash.upper()

        except Exception as e:
            logger.error(f"Hash verification error: {str(e)}")
            return False
