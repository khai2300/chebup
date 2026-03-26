# Django UI - Web Ban Che Bup

Bo giao dien nay dung `Django Template` + `Bootstrap 5` + `JavaScript`.

## Cau truc

- `templates/shop/base.html`
- `templates/shop/home.html`
- `templates/shop/product_detail.html`
- `templates/shop/cart.html`
- `templates/shop/checkout.html`
- `templates/shop/account.html`
- `templates/shop/orders.html`
- `templates/shop/chat.html`
- `templates/shop/admin_dashboard.html`
- `templates/shop/auth/login.html`
- `templates/shop/auth/register.html`
- `static/shop/css/theme.css`
- `static/shop/js/chat.js`

## URL name duoc dung trong template

```python
shop:home
shop:product_detail
shop:add_to_cart
shop:cart
shop:update_cart
shop:remove_cart
shop:checkout
shop:orders
shop:order_detail
shop:cancel_order
shop:account
shop:add_address
shop:set_default_address
shop:chat
shop:chat_api
shop:chat_reset
shop:login
shop:logout
shop:register
shop:search_suggest
shop:admin_dashboard
shop:admin_products
shop:admin_orders
shop:admin_users
shop:admin_promotions
```

## Context toi thieu cho cac trang

- `home`: `products`, `categories`, `q`, `selected_category`
- `product_detail`: `product`, `related_products`
- `cart`: `cart_items`, `summary{subtotal,discount,total}`
- `checkout`: `addresses`, `payment_methods`, `cart_items`, `promo_code`, `summary`
- `account`: `addresses`
- `orders`: `orders`
- `chat`: `chat_history`
- `admin_dashboard`: `stats`, `latest_orders`

## Cai dat static trong Django

Trong `settings.py`:

```python
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "django_ui" / "static"]
TEMPLATES[0]["DIRS"] = [BASE_DIR / "django_ui" / "templates"]
```
