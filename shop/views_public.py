import difflib
from io import BytesIO

import qrcode
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import Category, Product
from .services.seed import ensure_seed_data
from .views_utils import build_public_url


@require_GET
def home(request):
    ensure_seed_data()
    q = request.GET.get("q", "").strip()
    selected_category = request.GET.get("category", "").strip()

    products = Product.objects.select_related("category").all()
    categories = Category.objects.all()

    if selected_category.isdigit():
        products = products.filter(category_id=int(selected_category))
    if q:
        products = products.filter(
            Q(name__icontains=q) | Q(description__icontains=q) | Q(category__name__icontains=q)
        )

    return render(
        request,
        "shop/home.html",
        {
            "products": products,
            "categories": categories,
            "q": q,
            "selected_category": selected_category,
        },
    )


@require_GET
def search_suggest(request):
    q = request.GET.get("q", "").strip()
    if not q:
        return JsonResponse([], safe=False)

    names = list(Product.objects.values_list("name", flat=True))
    contains = [name for name in names if q.lower() in name.lower()]
    fuzzy = difflib.get_close_matches(q, names, n=8, cutoff=0.3)
    merged = []
    for item in contains + fuzzy:
        if item not in merged:
            merged.append(item)
    return JsonResponse(merged[:8], safe=False)


@require_GET
def product_detail(request, product_id):
    product = get_object_or_404(Product.objects.select_related("category", "source_zone"), id=product_id)
    related_products = Product.objects.filter(category=product.category).exclude(id=product.id)[:3]
    return render(
        request,
        "shop/product_detail.html",
        {
            "product": product,
            "related_products": related_products,
        },
    )


@require_GET
def product_trace_qr(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    trace_path = reverse("shop:trace_product", kwargs={"product_id": product.id})
    trace_url = build_public_url(request, trace_path)
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(trace_url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#1d3b2c", back_color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    if request.GET.get("download", "").strip().lower() in {"1", "true", "yes"}:
        response["Content-Disposition"] = f'attachment; filename="trace-product-{product.id}.png"'
    return response


@require_GET
def trace_product(request, product_id):
    product = get_object_or_404(Product.objects.select_related("source_zone", "category"), id=product_id)
    zone = product.source_zone
    if zone:
        zone_data = {
            "name": zone.name,
            "code": zone.code,
            "province": zone.province,
            "description": zone.description,
            "latitude": float(zone.latitude),
            "longitude": float(zone.longitude),
        }
    else:
        zone_data = None

    return render(
        request,
        "shop/trace_product.html",
        {
            "product": product,
            "zone": zone_data,
        },
    )
