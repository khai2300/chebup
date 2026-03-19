from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Product, ProductionZone


class AdminProductsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff",
            password="strong-pass-123",
            is_staff=True,
        )
        self.category = Category.objects.create(name="Tra xanh")
        self.other_category = Category.objects.create(name="Tra den")
        self.zone = ProductionZone.objects.create(
            name="Tan Cuong",
            code="TC001",
            province="Thai Nguyen",
            latitude="21.594444",
            longitude="105.848611",
            description="Vung trong che chat luong cao",
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Tra moc",
            description="Mo ta cu",
            short_description="Ngan",
            price="100000.00",
            stock=10,
            source_zone=self.zone,
            image_url="",
            map_link="",
        )
        self.low_stock_product = Product.objects.create(
            category=self.other_category,
            name="Hong tra",
            description="Lo hang sap het",
            short_description="Con it",
            price="80000.00",
            stock=3,
            image_url="",
            map_link="",
        )
        self.out_of_stock_product = Product.objects.create(
            category=self.other_category,
            name="Tra sua kho",
            description="Tam het hang",
            short_description="Het hang",
            price="90000.00",
            stock=0,
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

    def test_admin_products_can_filter_by_keyword_and_zone(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url, {"q": "Tan Cuong", "zone": str(self.zone.id)})

        self.assertEqual(response.status_code, 200)
        products = list(response.context["products"])
        self.assertEqual(products, [self.product])

    def test_admin_products_can_filter_by_stock_state(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url, {"stock": "low_stock"})

        self.assertEqual(response.status_code, 200)
        products = list(response.context["products"])
        self.assertEqual(products, [self.low_stock_product])
