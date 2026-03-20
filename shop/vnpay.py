import hashlib
import hmac
from datetime import datetime, timedelta
from urllib.parse import urlencode

from django.conf import settings


def is_vnpay_configured():
    return bool(
        getattr(settings, "VNPAY_TMN_CODE", "").strip()
        and getattr(settings, "VNPAY_HASH_SECRET", "").strip()
        and getattr(settings, "VNPAY_RETURN_URL", "").strip()
    )


def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    ip = request.META.get("REMOTE_ADDR", "127.0.0.1").strip()
    if ip == "::1":
        return "127.0.0.1"
    return ip or "127.0.0.1"


def build_vnpay_payment_url(request, order):
    if not is_vnpay_configured():
        return None

    vnp_url = settings.VNPAY_URL
    now = datetime.now()
    create_date = now.strftime("%Y%m%d%H%M%S")
    expire_date = (now + timedelta(minutes=15)).strftime("%Y%m%d%H%M%S")

    txn_ref = str(order.id)
    amount = int(order.final_amount) * 100

    vnp_params = {
        "vnp_Version": settings.VNPAY_VERSION,
        "vnp_Command": "pay",
        "vnp_TmnCode": settings.VNPAY_TMN_CODE,
        "vnp_Amount": amount,
        "vnp_CurrCode": settings.VNPAY_CURRENCY_CODE,
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": f"Thanh toan don hang {txn_ref}",
        "vnp_OrderType": "other",
        "vnp_Locale": settings.VNPAY_LOCALE,
        "vnp_ReturnUrl": settings.VNPAY_RETURN_URL,
        "vnp_IpAddr": _get_client_ip(request),
        "vnp_CreateDate": create_date,
        "vnp_ExpireDate": expire_date,
    }

    sorted_params = dict(sorted(vnp_params.items()))
    sign_data = urlencode(sorted_params)

    secure_hash = hmac.new(
        settings.VNPAY_HASH_SECRET.encode("utf-8"),
        sign_data.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()

    payment_url = f"{vnp_url}?{sign_data}&vnp_SecureHash={secure_hash}"

    print("NOW:", now)
    print("CREATE_DATE:", create_date)
    print("EXPIRE_DATE:", expire_date)
    print("TXN_REF:", txn_ref)
    print("AMOUNT:", amount)
    print("PAYMENT_URL:", payment_url)

    return payment_url


def verify_vnpay_signature(params):
    input_data = params.copy()
    vnp_secure_hash = input_data.pop("vnp_SecureHash", None)
    input_data.pop("vnp_SecureHashType", None)

    if not vnp_secure_hash:
        return False

    sorted_params = dict(sorted(input_data.items()))
    sign_data = urlencode(sorted_params)

    secure_hash = hmac.new(
        settings.VNPAY_HASH_SECRET.encode("utf-8"),
        sign_data.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(secure_hash, vnp_secure_hash)