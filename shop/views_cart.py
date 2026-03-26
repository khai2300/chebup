from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import CartItem, Product
from .views_utils import calculate_cart_summary, get_weight_option


@login_required
@require_POST
def add_to_cart(request, product_id):
    try:
        quantity = int(request.POST.get("quantity", 1))
    except ValueError:
        quantity = 1
    quantity = max(1, quantity)
    weight_option = get_weight_option(request.POST.get("weight_grams"))

    with transaction.atomic():
        product = get_object_or_404(Product.objects.select_for_update(), id=product_id)
        if product.stock <= 0:
            messages.error(request, "Sản phẩm này đã hết hàng, vui lòng chờ cập nhật thêm.")
            return redirect(request.META.get("HTTP_REFERER") or "shop:home")
        if quantity > product.stock:
            messages.error(request, "Số lượng vượt quá tồn kho. Thao tác thêm đơn này đã bị hủy.")
            return redirect(request.META.get("HTTP_REFERER") or "shop:home")

        item, created = CartItem.objects.get_or_create(
            user=request.user,
            product=product,
            weight_grams=weight_option["grams"],
            defaults={
                "quantity": 0,
                "weight_label": weight_option["label"],
                "weight_multiplier": weight_option["multiplier"],
            },
        )
        if not created and (
            item.weight_label != weight_option["label"]
            or item.weight_multiplier != weight_option["multiplier"]
        ):
            item.weight_label = weight_option["label"]
            item.weight_multiplier = weight_option["multiplier"]

        item.quantity += quantity
        item.save(update_fields=["quantity", "weight_label", "weight_multiplier"])

        product.stock -= quantity
        product.save(update_fields=["stock"])

    messages.success(request, f"Đã thêm vào giỏ hàng ({weight_option['label']}).")
    return redirect(request.META.get("HTTP_REFERER") or "shop:cart")


@login_required
def cart(request):
    summary = calculate_cart_summary(request.user)
    return render(
        request,
        "shop/cart.html",
        {
            "cart_items": summary["cart_items"],
            "summary": summary,
        },
    )


@login_required
@require_POST
def update_cart(request, item_id):
    item = get_object_or_404(CartItem.objects.select_related("product"), id=item_id, user=request.user)
    try:
        quantity = int(request.POST.get("quantity", item.quantity))
    except ValueError:
        quantity = item.quantity

    with transaction.atomic():
        product = get_object_or_404(Product.objects.select_for_update(), id=item.product_id)
        item = get_object_or_404(CartItem.objects.select_for_update(), id=item_id, user=request.user)
        delta = quantity - item.quantity

        if quantity <= 0:
            product.stock += item.quantity
            product.save(update_fields=["stock"])
            item.delete()
            messages.info(request, "Đã xóa sản phẩm khỏi giỏ.")
            return redirect("shop:cart")

        if delta > 0 and delta > product.stock:
            messages.error(request, "Số lượng vượt quá tồn kho.")
            return redirect("shop:cart")

        if delta > 0:
            product.stock -= delta
            product.save(update_fields=["stock"])
        elif delta < 0:
            product.stock += abs(delta)
            product.save(update_fields=["stock"])

        item.quantity = quantity
        item.save(update_fields=["quantity"])

    messages.success(request, "Đã cập nhật giỏ hàng.")
    return redirect("shop:cart")


@login_required
@require_POST
def remove_cart(request, item_id):
    with transaction.atomic():
        item = get_object_or_404(CartItem.objects.select_related("product"), id=item_id, user=request.user)
        product = get_object_or_404(Product.objects.select_for_update(), id=item.product_id)
        product.stock += item.quantity
        product.save(update_fields=["stock"])
        item.delete()

    messages.info(request, "Đã xóa sản phẩm.")
    return redirect("shop:cart")
