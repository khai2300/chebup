import socket
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import CartItem, OrderTraceToken, Promotion


PAYMENT_METHOD_COD = "COD"
PAYMENT_METHOD_BANK_TRANSFER = "Bank Transfer"
PAYMENT_METHOD_VNPAY = "VNPAY"
PAYMENT_METHODS = [
    {"value": PAYMENT_METHOD_COD, "label": "Thanh toán khi nhận hàng (COD)"},
    {"value": PAYMENT_METHOD_BANK_TRANSFER, "label": "Thanh toán online (Ngân hàng)"},
    {"value": PAYMENT_METHOD_VNPAY, "label": "Thanh toán qua VNPAY"},
]
PAYMENT_METHOD_VALUES = {method["value"] for method in PAYMENT_METHODS}


def get_or_create_order_trace_token(order):
    token_obj, _ = OrderTraceToken.objects.get_or_create(order=order)
    return token_obj


def build_public_url(request, path):
    host = request.get_host().strip()
    host_name = host.split(":", 1)[0].lower()
    if host_name.endswith(".trycloudflare.com"):
        return f"https://{host_name}/{path.lstrip('/')}"

    base_url = (getattr(settings, "QR_PUBLIC_BASE_URL", "") or "").strip()
    if base_url:
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    scheme = "https" if request.is_secure() else "http"
    if host and not host.startswith(("127.0.0.1", "localhost", "[::1]", "::1")):
        return f"{scheme}://{host}/{path.lstrip('/')}"

    # Fallback when admin is opened via localhost: try LAN IP so phone can access QR URL.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            lan_ip = sock.getsockname()[0]
    except OSError:
        lan_ip = ""

    if lan_ip and not lan_ip.startswith("127."):
        port = request.get_port()
        default_port = "443" if scheme == "https" else "80"
        host_with_port = f"{lan_ip}:{port}" if port and port != default_port else lan_ip
        return f"{scheme}://{host_with_port}/{path.lstrip('/')}"

    return request.build_absolute_uri(path)


def build_order_trace_url(request, order):
    token_obj = get_or_create_order_trace_token(order)
    trace_path = reverse("shop:trace_order", kwargs={"token": token_obj.token})
    return build_public_url(request, trace_path)


def calculate_cart_summary(user, promo_code=""):
    cart_items = list(CartItem.objects.select_related("product").filter(user=user))
    subtotal = sum((item.product.price * item.quantity for item in cart_items), Decimal("0"))
    discount = Decimal("0")
    promotion = None

    normalized_code = (promo_code or "").strip().upper()
    if normalized_code:
        now = timezone.now()
        promotion = Promotion.objects.filter(code=normalized_code, is_active=True).first()
        if promotion:
            valid_start = promotion.start_at is None or promotion.start_at <= now
            valid_end = promotion.end_at is None or promotion.end_at >= now
            if not (valid_start and valid_end):
                promotion = None
        if promotion:
            if promotion.discount_type == Promotion.DISCOUNT_PERCENT:
                discount = subtotal * promotion.value / Decimal("100")
            else:
                discount = promotion.value

    discount = min(discount, subtotal)
    total = subtotal - discount
    return {
        "cart_items": cart_items,
        "subtotal": subtotal,
        "discount": discount,
        "total": total,
        "promotion": promotion,
        "promo_code": normalized_code,
    }


def build_bank_transfer_info(total_amount, username=""):
    bank_name = (getattr(settings, "BANK_TRANSFER_BANK_NAME", "") or "Techcombank").strip()
    bank_code = (getattr(settings, "BANK_TRANSFER_BANK_CODE", "") or "TCB").strip().upper()
    account_name = (getattr(settings, "BANK_TRANSFER_ACCOUNT_NAME", "") or "NGUYEN TRI KHAI").strip()
    account_number = (
        getattr(settings, "BANK_TRANSFER_ACCOUNT_NUMBER", "") or "19037577368017"
    ).strip()
    note_prefix = (getattr(settings, "BANK_TRANSFER_NOTE_PREFIX", "") or "THANH TOAN").strip()
    amount_int = int(total_amount) if total_amount else 0
    transfer_note = f"{note_prefix} {username}".strip()

    qr_base = f"https://img.vietqr.io/image/{bank_code}-{account_number}-compact2.png"
    query = urlencode(
        {
            "amount": amount_int,
            "addInfo": transfer_note,
            "accountName": account_name,
        }
    )
    return {
        "method_value": PAYMENT_METHOD_BANK_TRANSFER,
        "bank_name": bank_name,
        "bank_code": bank_code,
        "account_name": account_name,
        "account_number": account_number,
        "transfer_note": transfer_note,
        "qr_url": f"{qr_base}?{query}",
    }
