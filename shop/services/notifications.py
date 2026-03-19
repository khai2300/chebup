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
    items_block = "\n".join(item_lines) if item_lines else "- (khong co san pham)"

    address = order.address
    shipping_address = (
        f"{address.street}, {address.ward}, {address.district}, {address.city}"
        if address
        else "N/A"
    )
    recipient_name = (getattr(address, "recipient_name", "") or "").strip() if address else ""
    recipient_phone = (getattr(address, "phone", "") or "").strip() if address else ""

    subject = f"[Che Bup] Xac nhan don hang #{order.id}"
    text_body = (
        "Don hang cua ban da duoc ghi nhan.\n\n"
        f"Ma don: #{order.id}\n"
        f"Trang thai: {order.status}\n"
        f"Phuong thuc thanh toan: {order.payment_method}\n"
        f"Tong thanh toan: {_format_currency(order.final_amount)} VND\n"
        f"Dia chi giao hang: {shipping_address}\n"
        f"Ten nguoi nhan: {recipient_name or 'N/A'}\n"
        f"So dien thoai: {recipient_phone or 'N/A'}\n\n"
        f"Danh sach san pham:\n{items_block}\n\n"
        "Cam on ban da dat hang tai Che Bup Thai Nguyen."
    )
    html_body = (
        "<h3>Xac nhan don hang</h3>"
        f"<p><strong>Ma don:</strong> #{order.id}</p>"
        f"<p><strong>Trang thai:</strong> {order.status}</p>"
        f"<p><strong>Phuong thuc thanh toan:</strong> {order.payment_method}</p>"
        f"<p><strong>Tong thanh toan:</strong> {_format_currency(order.final_amount)} VND</p>"
        f"<p><strong>Dia chi giao hang:</strong> {shipping_address}</p>"
        f"<p><strong>Ten nguoi nhan:</strong> {recipient_name or 'N/A'}</p>"
        f"<p><strong>So dien thoai:</strong> {recipient_phone or 'N/A'}</p>"
        "<p><strong>Danh sach san pham:</strong></p>"
        f"<pre>{items_block}</pre>"
        "<p>Cam on ban da dat hang tai Che Bup Thai Nguyen.</p>"
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
