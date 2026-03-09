from django.contrib import admin

from .models import (
    Address,
    CartItem,
    Category,
    ChatMessage,
    ChatSession,
    Order,
    OrderTraceToken,
    OrderItem,
    Product,
    ProductionZone,
    Promotion,
    UserProfile,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category", "source_zone", "price", "stock", "created_at")
    list_filter = ("category", "source_zone")
    search_fields = ("name", "description")


@admin.register(ProductionZone)
class ProductionZoneAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "province", "latitude", "longitude")
    search_fields = ("code", "name", "province")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "recipient_name", "phone", "city", "is_default")
    list_filter = ("is_default", "city")
    search_fields = ("recipient_name", "phone", "street", "city")


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "product", "quantity", "created_at")
    search_fields = ("user__username", "product__name")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product_name",
        "unit_price",
        "quantity",
        "subtotal",
        "source_zone_name",
        "source_zone_code",
        "source_zone_province",
        "source_zone_latitude",
        "source_zone_longitude",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "payment_method", "final_amount", "created_at")
    list_filter = ("status", "payment_method")
    search_fields = ("user__username", "promo_code")
    inlines = [OrderItemInline]


@admin.register(OrderTraceToken)
class OrderTraceTokenAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "token", "created_at")
    search_fields = ("order__id", "order__user__username", "token")


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "discount_type", "value", "is_active", "start_at", "end_at")
    list_filter = ("discount_type", "is_active")
    search_fields = ("code",)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "full_name", "phone")
    search_fields = ("user__username", "full_name", "phone")


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("role", "content", "created_at")
    can_delete = False


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("user__username", "title")
    inlines = [ChatMessageInline]
