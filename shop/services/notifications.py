from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives


def _format_currency(amount):
    if amount is None:
        return "0"
    if isinstance(amount, Decimal):
        amount = int(amount)
    return f"{amount:,}".replace(",", ".")


def _collect_recipients(order):
    recipients = []
    user_email = (getattr(order.user, "email", "") or "").strip()
    if user_email:
        recipients.append(user_email)
    extra_recipients = getattr(settings, "ORDER_NOTIFY_TO", []) or []
    for email in extra_recipients:
        cleaned = (email or "").strip()
        if cleaned:
            recipients.append(cleaned)
    # Deduplicate while preserving order.
    return list(dict.fromkeys(recipients))


def send_order_notification_email(order):
    recipients = _collect_recipients(order)
    if not recipients:
        return False, "no_recipients"
    backend = (getattr(settings, "EMAIL_BACKEND", "") or "").lower()
    host_user = (getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    host_password = (getattr(settings, "EMAIL_HOST_PASSWORD", "") or "").strip()
    if "smtp" in backend and (not host_user or not host_password):
        return False, "smtp_not_configured"

    order_items = list(order.items.all())
    item_lines = []
    for item in order_items:
        item_lines.append(
            f"- {item.product_name}: {item.quantity} x {_format_currency(item.unit_price)} VND = {_format_currency(item.subtotal)} VND"
        )
    items_block = "\n".join(item_lines) if item_lines else "- (kh?ng c? s?n ph?m)"

    address = order.address
    shipping_address = (
        f"{address.street}, {address.ward}, {address.district}, {address.city}"
        if address
        else "N/A"
    )
    recipient_name = (getattr(address, "recipient_name", "") or "").strip() if address else ""
    recipient_phone = (getattr(address, "phone", "") or "").strip() if address else ""

    subject = f"[Ch? B?p] X?c nh?n ??n h?ng #{order.id}"
    text_body = (
        "??n h?ng c?a b?n ?? ???c ghi nh?n.\n\n"
        f"M? ??n: #{order.id}\n"
        f"Tr?ng th?i: {order.status}\n"
        f"Ph??ng th?c thanh to?n: {order.payment_method}\n"
        f"T?ng thanh to?n: {_format_currency(order.final_amount)} VND\n"
        f"??a ch? giao h?ng: {shipping_address}\n"
        f"T?n ng??i nh?n: {recipient_name or 'N/A'}\n"
        f"S? ?i?n tho?i: {recipient_phone or 'N/A'}\n\n"
        f"Danh s?ch s?n ph?m:\n{items_block}\n\n"
        "C?m ?n b?n ?? ??t h?ng t?i Ch? B?p Th?i Nguy?n."
    )
    html_body = (
        "<h3>X?c nh?n ??n h?ng</h3>"
        f"<p><strong>M? ??n:</strong> #{order.id}</p>"
        f"<p><strong>Tr?ng th?i:</strong> {order.status}</p>"
        f"<p><strong>Ph??ng th?c thanh to?n:</strong> {order.payment_method}</p>"
        f"<p><strong>T?ng thanh to?n:</strong> {_format_currency(order.final_amount)} VND</p>"
        f"<p><strong>??a ch? giao h?ng:</strong> {shipping_address}</p>"
        f"<p><strong>T?n ng??i nh?n:</strong> {recipient_name or 'N/A'}</p>"
        f"<p><strong>S? ?i?n tho?i:</strong> {recipient_phone or 'N/A'}</p>"
        "<p><strong>Danh s?ch s?n ph?m:</strong></p>"
        f"<pre>{items_block}</pre>"
        "<p>C?m ?n b?n ?? ??t h?ng t?i Ch? B?p Th?i Nguy?n.</p>"
    )

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=recipients,
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=False)
    return True, "sent"
