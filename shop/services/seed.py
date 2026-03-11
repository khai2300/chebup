from decimal import Decimal

from django.contrib.auth import get_user_model

from ..models import Category, Product, Promotion, ProductionZone, UserProfile


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


def ensure_seed_data():
    zones = _ensure_production_zones()
    if Category.objects.exists() and Product.objects.exists():
        _sync_sample_product_zones(zones)
        _assign_default_source_zones(default_zone=zones.get("TN-TN-01"))
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
