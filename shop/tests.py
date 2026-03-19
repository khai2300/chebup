from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


class AdminProductsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff",
            password="strong-pass-123",
            is_staff=True,
        )
        self.category = Category.objects.create(name="Tra xanh")
        self.product = Product.objects.create(
            category=self.category,
            name="Tra moc",
            description="Mo ta cu",
            short_description="Ngan",
            price="100000.00",
            stock=10,
            image_url="",
            map_link="",
        )
        self.url = reverse("shop:admin_products")

    def _bulk_update_payload(self, name):
        prefix = f"product_{self.product.id}_"
        return {
            "product_ids": [str(self.product.id)],
            f"{prefix}name": name,
            f"{prefix}description": "Mo ta moi",
            f"{prefix}short_description": "Ngan moi",
            f"{prefix}category_id": str(self.category.id),
            f"{prefix}source_zone_id": "",
            f"{prefix}price": "120000",
            f"{prefix}stock": "8",
            f"{prefix}image_url": "",
            f"{prefix}map_link": "",
        }

    def test_bulk_update_without_action_still_saves(self):
        self.client.force_login(self.user)
        payload = self._bulk_update_payload("Tra da sua")

        response = self.client.post(self.url, payload)

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Tra da sua")
        self.assertEqual(str(self.product.price), "120000.00")
        self.assertEqual(self.product.stock, 8)

    def test_bulk_update_with_action_saves(self):
        self.client.force_login(self.user)
        payload = self._bulk_update_payload("Tra o long")
        payload["action"] = "bulk_update"

        response = self.client.post(self.url, payload)

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "Tra o long")
