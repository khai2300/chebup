import json
import logging
from urllib.parse import urlencode
from io import BytesIO

import qrcode
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .models import Address, CartItem, Order, OrderItem, OrderTraceToken
from .services.notifications import send_order_notification_email
from .services.vnpay import build_vnpay_payment_url, is_vnpay_configured, verify_vnpay_signature
from .views_utils import (
    PAYMENT_METHOD_COD,
    PAYMENT_METHOD_BANK_TRANSFER,
    PAYMENT_METHOD_VNPAY,
    PAYMENT_METHODS,
    PAYMENT_METHOD_VALUES,
    build_bank_transfer_info,
    build_order_trace_url,
    calculate_cart_summary,
    get_or_create_order_trace_token,
)

logger = logging.getLogger(__name__)


@login_required
def checkout(request):
    addresses = Address.objects.filter(user=request.user)
    if not addresses.exists():
        messages.error(request, "Bạn cần thêm địa chỉ trước khi đặt hàng.")
        return redirect("shop:account")

    promo_code = request.POST.get("promo_code", request.GET.get("promo_code", "")).strip().upper()
    summary = calculate_cart_summary(request.user, promo_code=promo_code)
    cart_items = summary["cart_items"]
    selected_payment_method = request.POST.get(
        "payment_method", request.GET.get("payment_method", "")
    ).strip()
    if selected_payment_method not in PAYMENT_METHOD_VALUES:
        selected_payment_method = PAYMENT_METHOD_COD
    if not cart_items:
        messages.warning(request, "Giỏ hàng đang trống.")
        return redirect("shop:home")

    if request.method == "POST":
        address_id = request.POST.get("address_id")
        payment_method = request.POST.get("payment_method", PAYMENT_METHOD_COD)
        bank_transfer_name = request.POST.get("bank_transfer_name", "").strip()
        bank_transfer_phone = request.POST.get("bank_transfer_phone", "").strip()

        address = Address.objects.filter(user=request.user, id=address_id).first()
        if address is None:
            messages.error(request, "Địa chỉ giao hàng không hợp lệ.")
            return redirect("shop:checkout")
        if payment_method not in PAYMENT_METHOD_VALUES:
            messages.error(request, "Phương thức thanh toán không hợp lệ.")
            return redirect("shop:checkout")
        if payment_method == PAYMENT_METHOD_BANK_TRANSFER and (
            not bank_transfer_name or not bank_transfer_phone
        ):
            messages.error(request, "Vui lòng nhập đầy đủ thông tin.")
            query = {"payment_method": payment_method}
            if promo_code:
                query["promo_code"] = promo_code
            return redirect(f"{reverse('shop:checkout')}?{urlencode(query)}")
        if payment_method == PAYMENT_METHOD_VNPAY and not is_vnpay_configured():
            messages.error(request, "VNPAY chua duoc cau hinh. Vui long lien he admin.")
            return redirect("shop:checkout")

        for item in cart_items:
            if item.quantity > item.product.stock:
                messages.error(request, f"Sản phẩm {item.product.name} không đủ tồn kho.")
                return redirect("shop:cart")

        with transaction.atomic():
            order = Order.objects.create(
                user=request.user,
                address=address,
                status=Order.STATUS_PENDING,
                payment_method=payment_method,
                promo_code=summary["promotion"].code if summary["promotion"] else "",
                total_amount=summary["subtotal"],
                discount_amount=summary["discount"],
                final_amount=summary["total"],
            )
            get_or_create_order_trace_token(order)

            for item in cart_items:
                zone = item.product.source_zone
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    unit_price=item.product.price,
                    quantity=item.quantity,
                    subtotal=item.product.price * item.quantity,
                    source_zone_name=zone.name if zone else "",
                    source_zone_code=zone.code if zone else "",
                    source_zone_province=zone.province if zone else "",
                    source_zone_latitude=zone.latitude if zone else None,
                    source_zone_longitude=zone.longitude if zone else None,
                )
                item.product.stock -= item.quantity
                item.product.save(update_fields=["stock"])

            CartItem.objects.filter(user=request.user).delete()

        email_sent = False
        email_reason = "send_failed"
        try:
            order_for_email = (
                Order.objects.select_related("user", "address").prefetch_related("items").get(id=order.id)
            )
            email_sent, email_reason = send_order_notification_email(order_for_email)
        except Exception as exc:
            email_sent = False
            email_reason = "send_failed"
            logger.exception("Failed to send order email for order_id=%s", order.id)
            if getattr(settings, "DEBUG", False):
                messages.warning(
                    request,
                    f"Gui email that bai: {exc}",
                )
        if not email_sent:
            if email_reason == "smtp_not_configured":
                messages.info(
                    request,
                    "Đơn hàng đã tạo. Chưa gửi được email vì thiếu cấu hình Gmail App Password (EMAIL_HOST_PASSWORD).",
                )
            elif email_reason == "no_recipients":
                messages.info(
                    request,
                    "Đơn hàng đã tạo. Chưa gửi email vì chưa có người nhận (ORDER_NOTIFY_TO hoặc email tài khoản).",
                )
            else:
                messages.warning(
                    request,
                    "Đơn hàng đã tạo thành công, nhưng gửi email thất bại. Bạn hãy kiểm tra cấu hình Gmail SMTP.",
                )

        if payment_method == PAYMENT_METHOD_VNPAY:
            vnpay_url = build_vnpay_payment_url(request, order)
            if not vnpay_url:
                messages.error(request, "Khong tao duoc link VNPAY. Vui long thu lai sau.")
                return redirect("shop:checkout")
            messages.info(request, "Dang chuyen den cong VNPAY de thanh toan.")
            return redirect(vnpay_url)

        messages.success(request, f"Đặt hàng thành công. Mã đơn #{order.id}")
        success_url = reverse("shop:checkout_success")
        return redirect(f"{success_url}?order_id={order.id}")

    payment_methods = PAYMENT_METHODS
    if not is_vnpay_configured():
        payment_methods = [
            method for method in PAYMENT_METHODS if method["value"] != PAYMENT_METHOD_VNPAY
        ]
        if selected_payment_method == PAYMENT_METHOD_VNPAY:
            selected_payment_method = PAYMENT_METHOD_COD

    return render(
        request,
        "shop/checkout.html",
        {
            "addresses": addresses,
            "payment_methods": payment_methods,
            "selected_payment_method": selected_payment_method,
            "bank_transfer": build_bank_transfer_info(summary["total"], request.user.username),
            "cart_items": cart_items,
            "summary": summary,
            "promo_code": promo_code,
        },
    )


@login_required
def orders(request):
    user_orders = list(
        Order.objects.filter(user=request.user).select_related("address").prefetch_related("items")
    )
    for order in user_orders:
        get_or_create_order_trace_token(order)
    return render(request, "shop/orders.html", {"orders": user_orders})


@login_required
@require_POST
def cancel_order(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related("items"), id=order_id, user=request.user)
    if order.status != Order.STATUS_PENDING:
        messages.error(request, "Chỉ có thể hủy đơn đang Pending.")
        return redirect("shop:orders")

    with transaction.atomic():
        order.status = Order.STATUS_CANCELLED
        order.save(update_fields=["status"])
        for item in order.items.all():
            if item.product:
                item.product.stock += item.quantity
                item.product.save(update_fields=["stock"])

    messages.success(request, "Đã hủy đơn hàng.")
    return redirect("shop:orders")


def _collect_trace_zones(order):
    zones = []
    seen = set()

    for item in order.items.all():
        zone_name = item.source_zone_name
        zone_code = item.source_zone_code
        zone_province = item.source_zone_province
        zone_lat = item.source_zone_latitude
        zone_lng = item.source_zone_longitude

        if (not zone_name or zone_lat is None or zone_lng is None) and item.product and item.product.source_zone:
            source_zone = item.product.source_zone
            zone_name = source_zone.name
            zone_code = source_zone.code
            zone_province = source_zone.province
            zone_lat = source_zone.latitude
            zone_lng = source_zone.longitude

        if not zone_name or zone_lat is None or zone_lng is None:
            continue

        marker_key = f"{zone_name}-{zone_lat}-{zone_lng}"
        if marker_key in seen:
            continue
        seen.add(marker_key)
        zones.append(
            {
                "name": zone_name,
                "code": zone_code,
                "province": zone_province,
                "latitude": float(zone_lat),
                "longitude": float(zone_lng),
            }
        )
    return zones


@login_required
@require_GET
def order_trace_qr(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if not request.user.is_staff and order.user_id != request.user.id:
        return HttpResponse(status=403)
    download_requested = request.GET.get("download", "").strip().lower() in {"1", "true", "yes"}
    if download_requested and not request.user.is_staff:
        return HttpResponse(status=403)

    trace_url = build_order_trace_url(request, order)
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(trace_url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#1d3b2c", back_color="white")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    if download_requested:
        response["Content-Disposition"] = f'attachment; filename="trace-order-{order.id}.png"'
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


@require_GET
def trace_order(request, token):
    trace = get_object_or_404(
        OrderTraceToken.objects.select_related("order").prefetch_related("order__items__product__source_zone"),
        token=token,
    )
    order = trace.order
    zones = _collect_trace_zones(order)

    if zones:
        center_lat = sum(zone["latitude"] for zone in zones) / len(zones)
        center_lng = sum(zone["longitude"] for zone in zones) / len(zones)
    else:
        center_lat = 21.027763
        center_lng = 105.834160

    context = {
        "order": order,
        "trace": trace,
        "zones": zones,
        "zones_json": json.dumps(zones),
        "center_lat": center_lat,
        "center_lng": center_lng,
    }
    return render(request, "shop/trace_order.html", context)


@login_required
def checkout_success(request):
    order_id = request.GET.get("order_id", "").strip()
    order = None
    if order_id.isdigit():
        order = Order.objects.filter(id=int(order_id), user=request.user).first()
    return render(request, "shop/checkout_success.html", {"order": order})


@login_required
@require_GET
def vnpay_return(request):
    params = request.GET.dict()
    order_id = params.get("vnp_TxnRef", "")
    order = None
    if order_id.isdigit():
        order = Order.objects.filter(id=int(order_id), user=request.user).first()

    if not params or not verify_vnpay_signature(params):
        messages.error(request, "Chu ky VNPAY khong hop le.")
    elif not order:
        messages.error(request, "Khong tim thay don hang can xac nhan.")
    else:
        response_code = params.get("vnp_ResponseCode", "")
        txn_status = params.get("vnp_TransactionStatus", "")
        if response_code == "00" and (txn_status in ("", "00")):
            if order.status == Order.STATUS_PENDING:
                order.status = Order.STATUS_PROCESSING
                order.save(update_fields=["status"])
            messages.success(request, "Thanh toan VNPAY thanh cong.")
        else:
            messages.warning(request, "Thanh toan VNPAY that bai hoac bi huy.")

    success_url = reverse("shop:checkout_success")
    if order_id:
        return redirect(f"{success_url}?order_id={order_id}")
    return redirect(success_url)


@require_GET
def vnpay_ipn(request):
    params = request.GET.dict()
    if not params or not verify_vnpay_signature(params):
        return JsonResponse({"RspCode": "97", "Message": "Invalid signature"})

    order_id = params.get("vnp_TxnRef", "")
    if not order_id.isdigit():
        return JsonResponse({"RspCode": "01", "Message": "Order not found"})

    order = Order.objects.filter(id=int(order_id)).first()
    if not order:
        return JsonResponse({"RspCode": "01", "Message": "Order not found"})

    try:
        received_amount = int(params.get("vnp_Amount", "0"))
    except (TypeError, ValueError):
        return JsonResponse({"RspCode": "04", "Message": "Invalid amount"})

    expected_amount = int(order.final_amount or 0) * 100
    if received_amount != expected_amount:
        return JsonResponse({"RspCode": "04", "Message": "Invalid amount"})

    response_code = params.get("vnp_ResponseCode", "")
    txn_status = params.get("vnp_TransactionStatus", "")
    if response_code == "00" and (txn_status in ("", "00")):
        if order.status == Order.STATUS_PENDING:
            order.status = Order.STATUS_PROCESSING
            order.save(update_fields=["status"])

    return JsonResponse({"RspCode": "00", "Message": "Confirm Success"})
