from decimal import Decimal

from django.contrib.auth import get_user_model

from ..models import Category, ProcessingStep, Product, Promotion, ProductionZone, UserProfile


DEFAULT_CATEGORIES = ["Che xanh", "Che o long", "Che thao moc", "Che dac san"]

ZONE_SEED = [
    {
        "code": "TN-TN-01",
        "name": "Vung che Tan Cuong",
        "province": "Thai Nguyen",
        "latitude": Decimal("21.594700"),
        "longitude": Decimal("105.773300"),
        "description": "Vung trong che bup truyen thong, do cao trung binh, dat feralit.",
    },
    {
        "code": "HG-ST-02",
        "name": "Vung che Shan Tuyet Tay Con Linh",
        "province": "Ha Giang",
        "latitude": Decimal("22.788300"),
        "longitude": Decimal("104.978900"),
        "description": "Cay che co thu vung cao, thu hoach thu cong.",
    },
    {
        "code": "BL-OL-03",
        "name": "Vung O Long Bao Loc",
        "province": "Lam Dong",
        "latitude": Decimal("11.547700"),
        "longitude": Decimal("107.807800"),
        "description": "Vung o long chuyen canh theo mo hinh huu co.",
    },
]

PRODUCT_SEED = [
    {
        "name": "Che Bup Thai Nguyen",
        "category": "Che xanh",
        "price": Decimal("120000"),
        "stock": 80,
        "short_description": "Tra xanh dam vi, huong com non.",
        "description": "Che bup Tan Cuong, sao kho theo phuong phap truyen thong, vi dam va hau ngot.",
        "image_url": "",
        "source_zone_code": "TN-TN-01",
    },
    {
        "name": "Tra Hoa Cuc Mat Ong",
        "category": "Che thao moc",
        "price": Decimal("95000"),
        "stock": 60,
        "short_description": "Thao moc diu nhe, de ngu.",
        "description": "Tra hoa cuc ket hop mat ong, thich hop uong am hoac uong lanh.",
        "image_url": "",
        "source_zone_code": "TN-TN-01",
    },
    {
        "name": "Bach Tra Shan Tuyet",
        "category": "Che dac san",
        "price": Decimal("220000"),
        "stock": 35,
        "short_description": "Che co thu vung cao, vi thanh mat.",
        "description": "Bach tra Shan Tuyet thu hoach tu cay che co thu tren 1000m, huong thom nhe.",
        "image_url": "",
        "source_zone_code": "HG-ST-02",
    },
    {
        "name": "O Long Bup Xoan",
        "category": "Che o long",
        "price": Decimal("180000"),
        "stock": 50,
        "short_description": "O long len men, huong sua.",
        "description": "O long Bup Xoan Bao Loc, len men vua, vi ngot, huong sua nhe.",
        "image_url": "",
        "source_zone_code": "BL-OL-03",
    },
    {
        "name": "Tra Sen Tay Ho",
        "category": "Che dac san",
        "price": Decimal("260000"),
        "stock": 20,
        "short_description": "Huong sen thanh lich, hau vi ngot.",
        "description": "Tra sen uop bong sen Tay Ho, mui huong thanh nhat, thich hop lam qua.",
        "image_url": "",
    },
    {
        "name": "Tra Gung Suoi Am",
        "category": "Che thao moc",
        "price": Decimal("110000"),
        "stock": 40,
        "short_description": "Am bung, de uong mua lanh.",
        "description": "Tra gung ket hop cam thao, giup am co, thich hop uong hang ngay.",
        "image_url": "",
    },
]

SEED_ZONE_BY_PRODUCT_NAME = {
    "Che Bup Thai Nguyen": "TN-TN-01",
    "Tra Hoa Cuc Mat Ong": "TN-TN-01",
    "Bach Tra Shan Tuyet": "HG-ST-02",
    "O Long Bup Xoan": "BL-OL-03",
}

GREEN_TEA_STEPS = [
    ("Thu h?i v? l?a ch?n nguy?n li?u", "Thu h?i b?p tr? t??i, ch?n l?c k? ?? ??m b?o ch?t l??ng."),
    ("L?m h?o l? tr?", "L?m h?o trong ?i?u ki?n th?ng tho?ng, ??o ??u ?? tr? h?o ??ng nh?t."),
    ("?p tr? v? di?t men", "??a l? tr? v?o t?n quay ?? ?p tr? v? di?t men ??n khi ??t y?u c?u."),
    ("V? tr?", "V? b?ng tay ho?c m?y, y?u c?u c?nh tr? cong v? g?n."),
    ("Sao tr?", "?i?u ch?nh nhi?t ?? sao ph? h?p ?? gi? m?u s?c v? h??ng v?."),
    ("L?n h??ng tr?", "Lo?i b? c?m, l? gi? sau ?? quay ti?p ?? t?o h??ng th?m ??c tr?ng."),
    ("??ng g?i v? b?o qu?n", "??ng g?i k?n, h?t ch?n kh?ng v? b?o qu?n kh? r?o."),
]

BLACK_TEA_STEPS = [
    ("Chu?n b? nguy?n li?u", "Ch?n b?p tr? ??t chu?n cho ch? ?en."),
    ("L?m h?o", "Gi?m l??ng n??c trong l? ?? t?o ?? d?o dai cho c?ng ?o?n v?."),
    ("V? l? tr?", "V? ?? l?m d?p t? b?o v? t?o ?i?u ki?n h?a tan khi pha."),
    ("L?n men", "Ki?m so?t nhi?t ?? v? ?? ?m ?? t?o m?u v? h??ng v? ??c tr?ng."),
    ("S?y", "S?y ? nhi?t ?? ph? h?p ?? c? ??nh m?u v? h??ng, c?n ?? ?m th?p."),
    ("S?ng v? ph?n lo?i", "S?ng tr?, ph?n c?p v? ki?m tra ch?t l??ng."),
    ("??ng g?i v? b?o qu?n", "??ng g?i c?n th?n v? b?o qu?n ??ng ?i?u ki?n."),
]

OOLONG_TEA_STEPS = [
    ("Thu ho?ch v? ph?i kh? r?o", "Thu b?p tr? 2-3 l? non v? 1 t?m, gi? l? tr? nguy?n v?n."),
    ("L?m h?o l? tr?", "K?t h?p h?o n?ng v? h?o m?t ?? t?o h??ng v? h?u v?."),
    ("L?n men", "T?ng oxy h?a c? ki?m so?t ?? t?o ??c tr?ng cho ? long."),
    ("Sao tr?", "Di?t men nhanh ?? gi? m?u xanh v? gi?m ?? ?m."),
    ("V? chu?ng v? s?y d?o", "V? t?o ?? m?m c?nh tr?, s?y ?? ?n ??nh ??c t?nh."),
    ("T?o h?nh", "?p, s?y n?ng v? ??nh t?i ?? t?o vi?n tr? tr?n."),
    ("S?y ??nh h??ng", "S?y ? nhi?t ?? ph? h?p ?? gi? h??ng l?u."),
    ("Th?nh ph?m", "Ki?m tra, ph?n lo?i v? chuy?n ??ng g?i."),
]

TEA_BAG_STEPS = [
    ("Chu?n b? nguy?n li?u", "Thu h?i v? ch?n b?p tr? ph? h?p cho tr? t?i l?c."),
    ("L?m h?o", "L?m h?o ?? t?o ?i?u ki?n cho c?c c?ng ?o?n ti?p theo."),
    ("C?t - v? - nghi?n", "L?m d?p t? b?o, ??ng b? nguy?n li?u ?? l?n men."),
    ("L?n men ??ng ??u", "Ki?m so?t qu? tr?nh l?n men ?? t?o m?u v? m?i v?."),
    ("L?m kh?", "S?y nhi?u giai ?o?n ?? ?n ??nh ch?t l??ng v? tr?nh v?n c?c."),
    ("??p h??ng", "Ph?i h??ng t? nhi?n theo t? l? ph? h?p."),
    ("??ng g?i", "??ng t?i l?c b?ng gi?y l?c ??t ti?u chu?n an to?n."),
]


def ensure_seed_data():
    zones = _ensure_production_zones()
    if Category.objects.exists() and Product.objects.exists():
        _sync_sample_product_zones(zones)
        _assign_default_source_zones(default_zone=zones.get("TN-TN-01"))
        _sync_processing_steps_from_document()
        return

    category_map = {}
    for name in DEFAULT_CATEGORIES:
        category, _ = Category.objects.get_or_create(name=name)
        category_map[name] = category

    for row in PRODUCT_SEED:
        zone_code = row.get("source_zone_code") or SEED_ZONE_BY_PRODUCT_NAME.get(row["name"])
        source_zone = zones.get(zone_code) if zone_code else zones.get("TN-TN-01")
        Product.objects.get_or_create(
            name=row["name"],
            defaults={
                "category": category_map[row["category"]],
                "price": row["price"],
                "stock": row["stock"],
                "source_zone": source_zone,
                "short_description": row["short_description"],
                "description": row["description"],
                "image_url": row.get("image_url", ""),
            },
        )

    Promotion.objects.get_or_create(
        code="TET2026",
        defaults={
            "discount_type": Promotion.DISCOUNT_PERCENT,
            "value": Decimal("10"),
            "is_active": True,
        },
    )

    User = get_user_model()
    if not User.objects.filter(username="admin").exists():
        admin = User.objects.create_user(
            username="admin",
            email="admin@tea.local",
            password="admin123",
            is_staff=True,
            is_superuser=True,
        )
        UserProfile.objects.get_or_create(user=admin, defaults={"full_name": "Admin", "phone": "0900000000"})
    _assign_default_source_zones(default_zone=zones.get("TN-TN-01"))
    _sync_sample_product_zones(zones)
    _sync_processing_steps_from_document()


def _ensure_production_zones():
    zones = {}
    for row in ZONE_SEED:
        zone, _ = ProductionZone.objects.get_or_create(code=row["code"], defaults=row)
        zones[zone.code] = zone
    return zones


def _assign_default_source_zones(default_zone=None):
    if default_zone is None:
        default_zone = ProductionZone.objects.order_by("id").first()
    if not default_zone:
        return
    Product.objects.filter(source_zone__isnull=True).update(source_zone=default_zone)


def _sync_sample_product_zones(zones):
    for product_name, zone_code in SEED_ZONE_BY_PRODUCT_NAME.items():
        zone = zones.get(zone_code)
        if not zone:
            continue
        Product.objects.filter(name=product_name).update(source_zone=zone)


def _sync_processing_steps_from_document():
    for product in Product.objects.select_related("category").all():
        category_name = (product.category.name or "").strip().lower()
        product_name = (product.name or "").strip().lower()

        if "o long" in category_name or "o long" in product_name:
            steps = OOLONG_TEA_STEPS
        elif "thao moc" in category_name:
            steps = TEA_BAG_STEPS
        elif "den" in category_name or "den" in product_name:
            steps = BLACK_TEA_STEPS
        else:
            steps = GREEN_TEA_STEPS

        ProcessingStep.objects.filter(product=product).delete()
        ProcessingStep.objects.bulk_create(
            [
                ProcessingStep(
                    product=product,
                    step_order=index,
                    title=title,
                    description=description,
                )
                for index, (title, description) in enumerate(steps, start=1)
            ]
        )
