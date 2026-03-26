import hashlib
import hmac
import urllib.parse
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from shop.views_utils import build_public_url


def is_vnpay_configured():
    return bool(
        (getattr(settings, "VNPAY_TMN_CODE", "") or "").strip()
        and (getattr(settings, "VNPAY_HASH_SECRET", "") or "").strip()
        and (getattr(settings, "VNPAY_URL", "") or "").strip()
    )


def _get_client_ip(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.META.get("REMOTE_ADDR") or "").strip()


def _sign_params(params, secret):
    items = [(key, value) for key, value in params.items() if value not in (None, "")]
    items.sort(key=lambda item: item[0])
    query = urllib.parse.urlencode(items)
    digest = hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha512).hexdigest()
    return digest


def build_vnpay_payment_url(request, order):
    if not is_vnpay_configured():
        return None

    tmn_code = (getattr(settings, "VNPAY_TMN_CODE", "") or "").strip()
    secret = (getattr(settings, "VNPAY_HASH_SECRET", "") or "").strip()
    base_url = (getattr(settings, "VNPAY_URL", "") or "").strip()
    return_url = (getattr(settings, "VNPAY_RETURN_URL", "") or "").strip()
    if not return_url:
        return_url = build_public_url(request, reverse("shop:vnpay_return"))
    else:
        # Ensure trailing slash matches Django URL pattern to avoid 404 from VNPAY callback
        if not return_url.endswith("/"):
            return_url = return_url + "/"

    amount = int(order.final_amount or 0) * 100
    now = timezone.localtime(timezone.now())
    expire = now + timedelta(minutes=15)

    params = {
        "vnp_Version": getattr(settings, "VNPAY_VERSION", "2.1.0"),
        "vnp_Command": "pay",
        "vnp_TmnCode": tmn_code,
        "vnp_Amount": str(amount),
        "vnp_CurrCode": "VND",
        "vnp_TxnRef": str(order.id),
        "vnp_OrderInfo": f"Thanh toán đơn hàng #{order.id}",
        "vnp_OrderType": "other",
        "vnp_Locale": getattr(settings, "VNPAY_LOCALE", "vn"),
        "vnp_ReturnUrl": return_url,
        "vnp_IpAddr": _get_client_ip(request),
        "vnp_CreateDate": now.strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate": expire.strftime("%Y%m%d%H%M%S"),
    }

    secure_hash = _sign_params(params, secret)
    params["vnp_SecureHash"] = secure_hash

    query = urllib.parse.urlencode(sorted(params.items(), key=lambda item: item[0]))
    return f"{base_url}?{query}"


def verify_vnpay_signature(params):
    secret = (getattr(settings, "VNPAY_HASH_SECRET", "") or "").strip()
    if not secret:
        return False

    secure_hash = (params.get("vnp_SecureHash") or "").strip()
    if not secure_hash:
        return False

    data = {key: value for key, value in params.items() if key not in {"vnp_SecureHash", "vnp_SecureHashType"}}
    calculated = _sign_params(data, secret)
    return hmac.compare_digest(calculated.lower(), secure_hash.lower())

