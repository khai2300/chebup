import html
import re
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Category, Order, OrderItem, Product, ProductionZone, Promotion
from .views_utils import get_or_create_order_trace_token

User = get_user_model()

IFRAME_SRC_RE = re.compile(r"""src=(["'])(?P<src>.+?)\1""", re.IGNORECASE)
REVENUE_STATUSES = [
    Order.STATUS_PENDING,
    Order.STATUS_PROCESSING,
    Order.STATUS_SHIPPED,
    Order.STATUS_DELIVERED,
]
DASHBOARD_PERIODS = {
    "7d": {"label": "7 ngày gần nhất", "days": 7, "bucket": "day"},
    "30d": {"label": "30 ngày gần nhất", "days": 30, "bucket": "day"},
    "90d": {"label": "90 ngày gần nhất", "days": 90, "bucket": "week"},
    "12m": {"label": "12 tháng gần nhất", "days": 365, "bucket": "month"},
}
PRODUCT_FIELDS = (
    "name",
    "description",
    "short_description",
    "category",
    "source_zone",
    "price",
    "stock",
    "image_url",
    "map_link",
)


def _normalize_map_link(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return ""

    if "<iframe" in value.lower():
        match = IFRAME_SRC_RE.search(value)
        if not match:
            return ""
        value = html.unescape(match.group("src")).strip()

    if not value.lower().startswith(("http://", "https://")):
        return ""

    return value[:2000]


def _collect_numeric_ids(raw_ids):
    cleaned_ids = []
    seen_ids = set()
    for raw_id in raw_ids:
        cleaned = (raw_id or "").strip()
        if not cleaned.isdigit():
            continue
        numeric_id = int(cleaned)
        if numeric_id in seen_ids:
            continue
        seen_ids.add(numeric_id)
        cleaned_ids.append(numeric_id)
    return cleaned_ids


def _parse_product_payload(request, prefix=""):
    name = request.POST.get(f"{prefix}name", "").strip()
    description = request.POST.get(f"{prefix}description", "").strip()
    short_description = request.POST.get(f"{prefix}short_description", "").strip()
    category_id = request.POST.get(f"{prefix}category_id", "").strip()
    source_zone_id = request.POST.get(f"{prefix}source_zone_id", "").strip()
    image_url = request.POST.get(f"{prefix}image_url", "").strip()
    uploaded_image = request.FILES.get(f"{prefix}image")
    clear_uploaded_image = request.POST.get(f"{prefix}clear_image") == "on"
    map_link = _normalize_map_link(request.POST.get(f"{prefix}map_link", ""))

    try:
        price = Decimal(request.POST.get(f"{prefix}price", "0").strip() or "0")
        stock = int(request.POST.get(f"{prefix}stock", "0").strip() or "0")
    except Exception:
        return None, "Giá hoặc tồn kho không hợp lệ."

    category = Category.objects.filter(id=category_id).first()
    zone = ProductionZone.objects.filter(id=source_zone_id).first() if source_zone_id else None
    if not category or not name:
        return None, "Cần nhập tên sản phẩm và danh mục."

    payload = {
        "name": name,
        "description": description or short_description or "Đang cập nhật mô tả.",
        "short_description": short_description,
        "category": category,
        "source_zone": zone,
        "price": max(price, Decimal("0")),
        "stock": max(stock, 0),
        "image_url": image_url,
        "map_link": map_link,
        "uploaded_image": uploaded_image,
        "clear_image": clear_uploaded_image,
    }
    return payload, None


def _apply_product_images(product, payload):
    if payload.get("clear_image") and product.image:
        product.image.delete(save=False)
        product.image = None
    uploaded_image = payload.get("uploaded_image")
    if uploaded_image:
        if product.image:
            product.image.delete(save=False)
        product.image = uploaded_image


def _apply_product_payload(product, payload):
    for field in PRODUCT_FIELDS:
        setattr(product, field, payload[field])
    _apply_product_images(product, payload)


def _normalize_dashboard_period(raw_period):
    period_key = (raw_period or "").strip().lower()
    if period_key not in DASHBOARD_PERIODS:
        period_key = "7d"
    return period_key, DASHBOARD_PERIODS[period_key]


def _normalize_stock_filter(raw_value):
    stock_key = (raw_value or "").strip().lower()
    if stock_key not in {"", "in_stock", "low_stock", "out_of_stock"}:
        stock_key = ""
    return stock_key


def _build_change_info(current_value, previous_value):
    if previous_value == 0:
        if current_value == 0:
            return {
                "direction": "flat",
                "display": "0%",
                "note": "Không đổi so với kỳ trước",
            }
        return {
            "direction": "up",
            "display": "Moi",
            "note": "Kỳ trước chưa có dữ liệu",
        }

    delta = current_value - previous_value
    pct = (delta / previous_value) * Decimal("100")
    if pct > 0:
        direction = "up"
    elif pct < 0:
        direction = "down"
    else:
        direction = "flat"
    return {
        "direction": direction,
        "display": f"{pct:+.1f}%",
        "note": "So với kỳ trước",
    }


def _format_dashboard_bucket_label(bucket_value, bucket_type):
    value = bucket_value.date() if hasattr(bucket_value, "date") else bucket_value
    if bucket_type == "day":
        return value.strftime("%d/%m")
    if bucket_type == "week":
        iso_year, iso_week, _ = value.isocalendar()
        return f"Tuần {iso_week:02d}/{iso_year}"
    return value.strftime("%m/%Y")


def _is_staff_user(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(_is_staff_user, login_url="shop:login")
def admin_dashboard(request):
    period_key, period_config = _normalize_dashboard_period(request.GET.get("period"))
    period_days = period_config["days"]
    bucket_type = period_config["bucket"]
    today = timezone.localdate()
    start_date = today - timedelta(days=period_days - 1)
    previous_start = start_date - timedelta(days=period_days)
    previous_end = start_date - timedelta(days=1)

    revenue_orders = Order.objects.filter(status__in=REVENUE_STATUSES)
    period_orders = revenue_orders.filter(created_at__date__range=(start_date, today))
    previous_orders = revenue_orders.filter(created_at__date__range=(previous_start, previous_end))
    period_order_items = OrderItem.objects.filter(
        order__status__in=REVENUE_STATUSES,
        order__created_at__date__range=(start_date, today),
    )
    previous_order_items = OrderItem.objects.filter(
        order__status__in=REVENUE_STATUSES,
        order__created_at__date__range=(previous_start, previous_end),
    )

    period_revenue = period_orders.aggregate(value=Sum("final_amount")).get("value") or Decimal("0")
    previous_revenue = previous_orders.aggregate(value=Sum("final_amount")).get("value") or Decimal("0")
    period_order_count = period_orders.count()
    previous_order_count = previous_orders.count()
    period_quantity_sold = period_order_items.aggregate(value=Sum("quantity")).get("value") or 0
    previous_quantity_sold = previous_order_items.aggregate(value=Sum("quantity")).get("value") or 0
    average_order_value = period_revenue / period_order_count if period_order_count else Decimal("0")

    if bucket_type == "day":
        bucket_expr = TruncDate("created_at")
        item_bucket_expr = TruncDate("order__created_at")
    elif bucket_type == "week":
        bucket_expr = TruncWeek("created_at")
        item_bucket_expr = TruncWeek("order__created_at")
    else:
        bucket_expr = TruncMonth("created_at")
        item_bucket_expr = TruncMonth("order__created_at")

    trend_rows = list(
        period_orders.annotate(bucket=bucket_expr)
        .values("bucket")
        .annotate(revenue=Sum("final_amount"), order_count=Count("id"))
        .order_by("bucket")
    )
    trend_quantity_rows = list(
        period_order_items.annotate(bucket=item_bucket_expr)
        .values("bucket")
        .annotate(quantity_sold=Sum("quantity"))
        .order_by("bucket")
    )
    quantity_by_bucket = {}
    for row in trend_quantity_rows:
        bucket_key = row["bucket"].date() if hasattr(row["bucket"], "date") else row["bucket"]
        quantity_by_bucket[bucket_key] = row["quantity_sold"] or 0

    max_revenue = max((row["revenue"] or Decimal("0") for row in trend_rows), default=Decimal("0"))
    trend_series = []
    for row in trend_rows:
        bucket_key = row["bucket"].date() if hasattr(row["bucket"], "date") else row["bucket"]
        revenue_value = row["revenue"] or Decimal("0")
        trend_series.append(
            {
                "label": _format_dashboard_bucket_label(row["bucket"], bucket_type),
                "revenue": revenue_value,
                "order_count": row["order_count"] or 0,
                "quantity_sold": quantity_by_bucket.get(bucket_key, 0),
                "revenue_pct": int((revenue_value / max_revenue) * 100) if max_revenue else 0,
            }
        )

    top_products = list(
        period_order_items.values("product_name")
        .annotate(quantity_sold=Sum("quantity"), revenue=Sum("subtotal"))
        .order_by("-quantity_sold", "-revenue")[:5]
    )
    low_products = list(
        period_order_items.values("product_name")
        .annotate(quantity_sold=Sum("quantity"), revenue=Sum("subtotal"))
        .order_by("quantity_sold", "revenue", "product_name")[:5]
    )

    trend_insights = []
    revenue_change = _build_change_info(period_revenue, previous_revenue)
    order_change = _build_change_info(Decimal(period_order_count), Decimal(previous_order_count))
    quantity_change = _build_change_info(Decimal(period_quantity_sold), Decimal(previous_quantity_sold))
    if period_order_count == 0:
        trend_insights.append("Chưa có đơn hàng hợp lệ trong kỳ đã chọn.")
    elif revenue_change["direction"] == "up":
        trend_insights.append(f"Doanh thu đang tăng ({revenue_change['display']}) {revenue_change['note'].lower()}.")
    elif revenue_change["direction"] == "down":
        trend_insights.append(f"Doanh thu đang giảm ({revenue_change['display']}) {revenue_change['note'].lower()}.")
    else:
        trend_insights.append("Doanh thu đang ổn định, chưa thay đổi rõ nét.")

    if top_products:
        lead_product = top_products[0]
        trend_insights.append(
            f"Sản phẩm dẫn đầu: {lead_product['product_name']} ({lead_product['quantity_sold']} sản phẩm)."
        )
    if trend_series:
        peak = max(trend_series, key=lambda row: row["revenue"])
        trend_insights.append(f"Giai đoạn cao điểm: {peak['label']} đạt {peak['revenue']:.0f} VND.")

    if low_products:
        slowest_product = low_products[0]
        trend_insights.append(
            f"Sản phẩm tiêu thụ ít nhất: {slowest_product['product_name']} ({slowest_product['quantity_sold']} sản phẩm)."
        )

    stats = {
        "total_users": User.objects.count(),
        "total_products": Product.objects.count(),
        "total_orders": Order.objects.count(),
        "total_revenue": (
            Order.objects.filter(status__in=REVENUE_STATUSES)
            .aggregate(value=Sum("final_amount"))
            .get("value")
            or Decimal("0")
        ),
    }
    latest_orders = Order.objects.select_related("user").order_by("-created_at")[:10]
    period_options = [{"value": key, "label": option["label"]} for key, option in DASHBOARD_PERIODS.items()]
    can_manage_users = request.user.is_superuser
    return render(
        request,
        "shop/admin_dashboard.html",
        {
            "stats": stats,
            "latest_orders": latest_orders,
            "period_options": period_options,
            "selected_period": period_key,
            "period_label": period_config["label"],
            "period_start": start_date,
            "period_end": today,
            "period_revenue": period_revenue,
            "period_order_count": period_order_count,
            "period_quantity_sold": period_quantity_sold,
            "average_order_value": average_order_value,
            "revenue_change": revenue_change,
            "order_change": order_change,
            "quantity_change": quantity_change,
            "trend_series": trend_series,
            "trend_insights": trend_insights,
            "top_products": top_products,
            "low_products": low_products,
            "can_manage_users": can_manage_users,
            "staff_role_label": "Quản lý admin" if can_manage_users else "Nhân viên",
        },
    )


@user_passes_test(_is_staff_user, login_url="shop:login")
def admin_products(request):
    if request.method == "POST":
        action = request.POST.get("action", "").strip()
        if not action and request.POST.getlist("product_ids"):
            action = "bulk_update"

        if action == "create":
            payload, error = _parse_product_payload(request)
            if error:
                messages.error(request, error)
                return redirect("shop:admin_products")

            product = Product(**{field: payload[field] for field in PRODUCT_FIELDS})
            _apply_product_images(product, payload)
            product.save()
            messages.success(request, f"Đã tạo sản phẩm #{product.id}.")
            return redirect("shop:admin_products")

        if action.startswith("delete:"):
            product_id = action.split(":", 1)[1].strip()
            product = Product.objects.filter(id=product_id).first()
            if not product:
                messages.error(request, "Không tìm thấy sản phẩm.")
                return redirect("shop:admin_products")
            product_name = product.name
            product.delete()
            messages.success(request, f"Đã xóa sản phẩm: {product_name}.")
            return redirect("shop:admin_products")

        if action == "bulk_delete_selected":
            selected_ids = _collect_numeric_ids(request.POST.getlist("selected_product_ids"))
            if not selected_ids:
                messages.warning(request, "Bạn chưa chọn sản phẩm nào để xóa.")
                return redirect("shop:admin_products")

            selected_qs = Product.objects.filter(id__in=selected_ids)
            selected_count = selected_qs.count()
            selected_qs.delete()
            if selected_count:
                messages.success(request, f"Đã xóa {selected_count} sản phẩm đã chọn.")
            else:
                messages.warning(request, "Không có sản phẩm hợp lệ để xóa.")
            return redirect("shop:admin_products")

        if action == "bulk_update":
            product_ids = _collect_numeric_ids(request.POST.getlist("product_ids"))
            if not product_ids:
                messages.error(request, "Không có sản phẩm nào để cập nhật.")
                return redirect("shop:admin_products")

            products = {product.id: product for product in Product.objects.filter(id__in=product_ids)}
            updated_count = 0
            failed_rows = []

            for product_id in product_ids:
                product = products.get(product_id)
                if not product:
                    failed_rows.append(str(product_id))
                    continue

                prefix = f"product_{product_id}_"
                payload, error = _parse_product_payload(request, prefix=prefix)
                if error:
                    failed_rows.append(str(product_id))
                    continue

                _apply_product_payload(product, payload)
                product.save()
                updated_count += 1

            if updated_count:
                messages.success(request, f"Đã cập nhật đồng loạt {updated_count} sản phẩm.")
            if failed_rows:
                preview = ", ".join(f"#{row_id}" for row_id in failed_rows[:8])
                suffix = "..." if len(failed_rows) > 8 else ""
                messages.warning(
                    request,
                    f"Một số dòng không hợp lệ, bỏ qua: {preview}{suffix}.",
                )
            if not updated_count and not failed_rows:
                messages.info(request, "Không có thay đổi nào được áp dụng.")
            return redirect("shop:admin_products")

        if action == "update":
            product_id = request.POST.get("product_id", "").strip()
            product = Product.objects.filter(id=product_id).first()
            if not product:
                messages.error(request, "Không tìm thấy sản phẩm.")
                return redirect("shop:admin_products")

            payload, error = _parse_product_payload(request)
            if error:
                messages.error(request, error)
                return redirect("shop:admin_products")

            _apply_product_payload(product, payload)
            product.save()
            messages.success(request, f"Đã cập nhật sản phẩm #{product.id}.")
            return redirect("shop:admin_products")

        if action == "delete":
            product_id = request.POST.get("product_id", "").strip()
            product = Product.objects.filter(id=product_id).first()
            if not product:
                messages.error(request, "Không tìm thấy sản phẩm.")
                return redirect("shop:admin_products")
            product_name = product.name
            product.delete()
            messages.success(request, f"Đã xóa sản phẩm: {product_name}.")
            return redirect("shop:admin_products")

        messages.error(request, "Hành động không hợp lệ.")
        return redirect("shop:admin_products")

    query = request.GET.get("q", "").strip()
    category_filter = request.GET.get("category", "").strip()
    zone_filter = request.GET.get("zone", "").strip()
    stock_filter = _normalize_stock_filter(request.GET.get("stock"))

    products = Product.objects.select_related("category", "source_zone").all()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(short_description__icontains=query)
            | Q(category__name__icontains=query)
            | Q(source_zone__name__icontains=query)
            | Q(source_zone__province__icontains=query)
        )
    if category_filter.isdigit():
        products = products.filter(category_id=int(category_filter))
    if zone_filter.isdigit():
        products = products.filter(source_zone_id=int(zone_filter))
    if stock_filter == "in_stock":
        products = products.filter(stock__gt=5)
    elif stock_filter == "low_stock":
        products = products.filter(stock__gte=1, stock__lte=5)
    elif stock_filter == "out_of_stock":
        products = products.filter(stock=0)

    categories = Category.objects.all()
    zones = ProductionZone.objects.all()
    return render(
        request,
        "shop/admin_products.html",
        {
            "products": products,
            "categories": categories,
            "zones": zones,
            "filters": {
                "q": query,
                "category": category_filter,
                "zone": zone_filter,
                "stock": stock_filter,
            },
        },
    )


@user_passes_test(_is_staff_user, login_url="shop:login")
def admin_orders(request):
    orders_qs = list(Order.objects.select_related("user").all())
    for order in orders_qs:
        get_or_create_order_trace_token(order)
    return render(request, "shop/admin_orders.html", {"orders": orders_qs})


@user_passes_test(_is_staff_user, login_url="shop:login")
def admin_users(request):
    users_qs = User.objects.all().order_by("-date_joined")
    return render(request, "shop/admin_users.html", {"users": users_qs})


@user_passes_test(_is_staff_user, login_url="shop:login")
def admin_promotions(request):
    promotions = Promotion.objects.all()
    return render(request, "shop/admin_promotions.html", {"promotions": promotions})
