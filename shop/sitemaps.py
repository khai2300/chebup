from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Product


class StaticViewSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return ["shop:home", "shop:news_list"]

    def location(self, item):
        return reverse(item)


class ProductSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return Product.objects.select_related("category").all()

    def lastmod(self, obj):
        return obj.created_at

    def location(self, obj):
        return reverse("shop:product_detail", args=[obj.id])
