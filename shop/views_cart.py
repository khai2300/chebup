from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import CartItem, Product
from .views_utils import calculate_cart_summary


@login_required
@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except ValueError:
        quantity = 1
    quantity = max(1, quantity)

    item, created = CartItem.objects.get_or_create(user=request.user, product=product, defaults={"quantity": 0})
    next_qty = item.quantity + quantity
    if next_qty > product.stock:
        messages.error(request, "So luong vuot qua ton kho.")
        return redirect(request.META.get("HTTP_REFERER") or "shop:home")

    item.quantity = next_qty
    item.save(update_fields=["quantity"])
    messages.success(request, "Da them vao gio hang.")
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

    if quantity <= 0:
        item.delete()
        messages.info(request, "Da xoa san pham khoi gio.")
        return redirect("shop:cart")

    if quantity > item.product.stock:
        messages.error(request, "So luong vuot qua ton kho.")
        return redirect("shop:cart")

    item.quantity = quantity
    item.save(update_fields=["quantity"])
    messages.success(request, "Da cap nhat gio hang.")
    return redirect("shop:cart")


@login_required
@require_POST
def remove_cart(request, item_id):
    item = get_object_or_404(CartItem, id=item_id, user=request.user)
    item.delete()
    messages.info(request, "Da xoa san pham.")
    return redirect("shop:cart")
