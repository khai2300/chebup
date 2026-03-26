import json
import os
import re
import urllib.error
import urllib.request
import unicodedata
from decimal import Decimal

from django.utils import timezone

from shop.models import Address, Order, Product, Promotion


SYSTEM_PROMPT = (
    "Bạn là trợ lý bán chè búp trong hệ thống ecommerce. "
    "Trả lời bằng tiếng Việt có dấu, thân thiện, ngắn gọn, không máy móc. "
    "Nếu thông tin liên quan đến đơn hàng của user đã có trong context thì ưu tiên dùng đúng dữ liệu đó. "
    "Không tự tạo chính sách không có trong context. "
    "Nếu user hỏi về sản phẩm/trà, ưu tiên đề xuất sản phẩm từ hệ thống nếu có."
)

PROMO_LIMIT = 5
MAX_HISTORY_MESSAGES = 12
PRODUCT_SUGGESTION_LIMIT = 3
DEFAULT_CHAT_PRODUCTS_LIMIT = 20
DEFAULT_CATALOG_CONTEXT_LIMIT = 200

GREETING_KEYWORDS = ["xin chào", "chào", "hello", "hi"]
PROMO_KEYWORDS = ["khuyến mãi", "voucher", "mã giảm", "giảm giá", "khuyen mai", "ma giam"]
ORDER_KEYWORDS = ["đơn hàng", "trạng thái", "kiểm tra đơn", "order", "mã đơn", "don hang", "ma don"]
CANCEL_KEYWORDS = ["hủy đơn", "hủy", "huy don", "huy"]
SHIPPING_KEYWORDS = ["giao hàng", "ship", "vận chuyển", "giao hang", "van chuyen"]
PAYMENT_KEYWORDS = ["thanh toán", "payment", "cod", "bank", "ví", "thanh toan"]
ADDRESS_KEYWORDS = ["địa chỉ", "address", "dia chi"]
PRODUCT_KEYWORDS = [
    "gợi ý", "đề xuất", "sản phẩm", "chè", "trà", "nên mua", "mua gì", "tất cả",
    "goi y", "de xuat", "san pham", "che", "tra",
]
THANKS_KEYWORDS = ["cảm ơn", "cam on", "thanks", "thank"]
VIETNAMESE_DIACRITICS = set("ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
PRICE_CHEAP_KEYWORDS = ["rẻ", "giá rẻ", "bình dân", "rẻ nhất", "thấp", "tiết kiệm", "re", "gia re"]
PRICE_EXPENSIVE_KEYWORDS = ["đắt", "cao cấp", "đắt tiền", "đắt nhất", "xịn", "premium", "mac", "dat"]
PRICE_HINT_TOKENS = {
    "re", "gia", "thap", "binh", "dan", "tiet", "kiem", "nhat",
    "dat", "cao", "cap", "mac", "xin", "premium", "tien",
}


def _env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _format_money(value):
    amount = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    return f"{amount:,.0f} VND"


def _normalize_text(text):
    normalized = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return stripped.lower()


def _contains_any(message, keywords):
    text = _normalize_text(message)
    return any(_normalize_text(word) in text for word in keywords)


def _has_vietnamese_diacritics(text):
    return any(char in VIETNAMESE_DIACRITICS for char in (text or "").lower())


def _active_promotions():
    now = timezone.now()
    promos = []
    for promo in Promotion.objects.filter(is_active=True):
        valid_start = promo.start_at is None or promo.start_at <= now
        valid_end = promo.end_at is None or promo.end_at >= now
        if not (valid_start and valid_end):
            continue
        if promo.discount_type == Promotion.DISCOUNT_PERCENT:
            value = f"{promo.value:.0f}%"
        else:
            value = _format_money(promo.value)
        promos.append(f"{promo.code} ({value})")
    return promos[:PROMO_LIMIT]


def _extract_order_id(text):
    if not text:
        return None
    normalized = _normalize_text(text)
    match = re.search(r"(?:#|don\s*|order\s*)(\d{1,8})", normalized)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _order_status_text(status):
    mapping = {
        Order.STATUS_PENDING: "đang chờ xác nhận",
        Order.STATUS_PROCESSING: "đang xử lý",
        Order.STATUS_SHIPPED: "đang giao",
        Order.STATUS_DELIVERED: "đã giao",
        Order.STATUS_CANCELLED: "đã hủy",
        Order.STATUS_PAYMENT_FAILED: "thất bại thanh toán",
    }
    return mapping.get(status, status)


def _looks_like_product_query(message):
    return _contains_any(message, PRODUCT_KEYWORDS)


def _get_price_intent(message):
    if _contains_any(message, PRICE_CHEAP_KEYWORDS):
        return "cheap"
    if _contains_any(message, PRICE_EXPENSIVE_KEYWORDS):
        return "expensive"
    return None


def _product_search_tokens(text):
    return [token for token in re.findall(r"[a-z0-9]+", _normalize_text(text)) if len(token) > 2]


def _score_product(product, tokens):
    haystack = _normalize_text(
        f"{product.name} {product.short_description} {product.description} {product.category.name}"
    )
    score = sum(1 for token in set(tokens) if token in haystack)
    return score, product.stock, -float(product.price)


def _rank_products(user_message):
    products = list(Product.objects.select_related("category").all())
    if not products:
        return []

    tokens = _product_search_tokens(user_message)
    price_intent = _get_price_intent(user_message)
    searchable_tokens = [token for token in tokens if token not in PRICE_HINT_TOKENS]

    if price_intent:
        sorted_prices = sorted(float(product.price) for product in products)
        median_price = sorted_prices[len(sorted_prices) // 2]
        if price_intent == "cheap":
            filtered = [product for product in products if float(product.price) <= median_price]
            filtered.sort(key=lambda p: (float(p.price), -p.stock, p.name))
        else:
            filtered = [product for product in products if float(product.price) >= median_price]
            filtered.sort(key=lambda p: (-float(p.price), -p.stock, p.name))

        if searchable_tokens:
            matched = []
            for product in filtered:
                haystack = _normalize_text(
                    f"{product.name} {product.short_description} {product.description} {product.category.name}"
                )
                if any(token in haystack for token in searchable_tokens):
                    matched.append(product)
            if matched:
                return matched
        return filtered

    if not searchable_tokens:
        return sorted(products, key=lambda p: (-p.stock, float(p.price), p.category.name, p.name))

    scored = []
    for product in products:
        score, stock, price_key = _score_product(product, searchable_tokens)
        scored.append((score, stock, price_key, product.category.name, product.name, product))

    scored.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
    ranked = [item[5] for item in scored]
    matched = [item[5] for item in scored if item[0] > 0]
    unmatched = [item for item in ranked if item not in matched]
    return matched + unmatched


def _format_product_line(product):
    return f"- {product.name}: {_format_money(product.price)}"


def _format_product_lines(products):
    return [_format_product_line(product) for product in products]


def _build_product_suggestions(message, limit=PRODUCT_SUGGESTION_LIMIT):
    if not _looks_like_product_query(message):
        return [], []
    products = _rank_products(message)[: max(1, limit)]
    return products, _format_product_lines(products)


def _build_catalog_context(message):
    if not _looks_like_product_query(message):
        return "", []

    ranked = _rank_products(message)
    if not ranked:
        return "", []

    price_intent = _get_price_intent(message)
    default_limit = 40 if price_intent else DEFAULT_CATALOG_CONTEXT_LIMIT
    limit = max(1, _env_int("CHAT_CATALOG_CONTEXT_LIMIT", default_limit))
    catalog = ranked[:limit]

    category_counts = {}
    for product in catalog:
        category_counts[product.category.name] = category_counts.get(product.category.name, 0) + 1

    category_summary = "; ".join(
        f"{category}: {count}" for category, count in sorted(category_counts.items(), key=lambda item: item[0].lower())
    )

    context = [
        f"Tổng số sản phẩm trong catalog đưa vào prompt: {len(catalog)}",
        "Số lượng theo danh mục: " + category_summary,
        "Danh sách chi tiết:",
        *_format_product_lines(catalog),
    ]
    return "\n".join(context), catalog


def suggest_products_for_chat(user_message, limit=None):
    if not _looks_like_product_query(user_message):
        return []

    ranked = _rank_products(user_message)
    if limit is None:
        if _get_price_intent(user_message):
            limit = min(8, _env_int("CHAT_PRODUCTS_LIMIT", DEFAULT_CHAT_PRODUCTS_LIMIT))
        else:
            limit = _env_int("CHAT_PRODUCTS_LIMIT", DEFAULT_CHAT_PRODUCTS_LIMIT)
    return ranked if limit <= 0 else ranked[:limit]


def _build_user_context(user):
    latest_orders = Order.objects.filter(user=user).select_related("address").order_by("-created_at")[:3]
    default_address = Address.objects.filter(user=user, is_default=True).first() or Address.objects.filter(user=user).first()
    promotions = _active_promotions()

    lines = [f"Tên user: {user.username}"]
    if default_address:
        lines.append(f"Địa chỉ mặc định: {default_address.full_address}")
    else:
        lines.append("Địa chỉ mặc định: chưa có")

    if latest_orders:
        for order in latest_orders:
            lines.append(f"Đơn #{order.id}: {_order_status_text(order.status)}, tổng {_format_money(order.final_amount)}")
    else:
        lines.append("Đơn hàng: chưa có đơn nào")

    if promotions:
        lines.append("Khuyến mãi đang hoạt động: " + ", ".join(promotions))
    else:
        lines.append("Khuyến mãi đang hoạt động: chưa có")

    return "\n".join(lines)


def _rule_based_reply(user, user_message):
    message = (user_message or "").strip().lower()
    if not message:
        return "Bạn cứ nhắn câu hỏi, mình sẽ hỗ trợ ngay."

    if _contains_any(message, GREETING_KEYWORDS):
        latest = Order.objects.filter(user=user).order_by("-created_at").first()
        if latest:
            return f"Chào {user.username}. Đơn gần nhất của bạn là #{latest.id}, hiện {_order_status_text(latest.status)}."
        return f"Chào {user.username}. Bạn cần mình gợi ý chè, kiểm tra đơn hay mã giảm giá?"

    if _contains_any(message, PROMO_KEYWORDS):
        promos = _active_promotions()
        if promos:
            return "Hiện shop đang có: " + ", ".join(promos) + ". Bạn nhập mã ở bước checkout."
        return "Hiện tại chưa có mã giảm giá đang hoạt động."

    if _contains_any(message, ORDER_KEYWORDS):
        target_id = _extract_order_id(message)
        order_qs = Order.objects.filter(user=user)
        order = order_qs.filter(id=target_id).first() if target_id else order_qs.order_by("-created_at").first()
        if order:
            return f"Đơn #{order.id} hiện {_order_status_text(order.status)}. Tổng thanh toán {_format_money(order.final_amount)}."
        return "Mình chưa tìm thấy đơn phù hợp. Bạn thử gửi mã đơn dạng #123."

    if _contains_any(message, CANCEL_KEYWORDS):
        pending = Order.objects.filter(user=user, status=Order.STATUS_PENDING).order_by("-created_at")
        if pending.exists():
            ids = ", ".join(f"#{order.id}" for order in pending[:3])
            return f"Bạn đang có {pending.count()} đơn có thể hủy ({ids}). Vào trang Đơn hàng và bấm Hủy đơn."
        return "Hiện tại bạn không có đơn Pending để hủy."

    if _contains_any(message, SHIPPING_KEYWORDS):
        shipping_order = (
            Order.objects.filter(user=user, status__in=[Order.STATUS_PROCESSING, Order.STATUS_SHIPPED])
            .order_by("-created_at")
            .first()
        )
        if shipping_order:
            return f"Đơn #{shipping_order.id} đang {_order_status_text(shipping_order.status)}. Thường mất 1-3 ngày làm việc tùy khu vực."
        return "Thời gian giao thường 1-3 ngày làm việc tùy khu vực."

    if _contains_any(message, PAYMENT_KEYWORDS):
        return "Shop hỗ trợ 2 cách thanh toán: COD và online bằng ngân hàng (có mã QR)."

    if _contains_any(message, ADDRESS_KEYWORDS):
        count = Address.objects.filter(user=user).count()
        if count == 0:
            return "Bạn chưa có địa chỉ. Vào Tài khoản để thêm địa chỉ trước khi checkout."
        return f"Bạn đang có {count} địa chỉ giao hàng. Bạn có thể đặt 1 địa chỉ mặc định."

    if _contains_any(message, PRODUCT_KEYWORDS):
        price_intent = _get_price_intent(message)
        products = suggest_products_for_chat(message, limit=6 if price_intent else 10)
        if products:
            lines = _format_product_lines(products)
            if price_intent == "cheap":
                header = f"Mình tìm thấy {len(products)} sản phẩm giá rẻ phù hợp:"
            elif price_intent == "expensive":
                header = f"Mình tìm thấy {len(products)} sản phẩm cao cấp/phân khúc giá cao:"
            else:
                header = f"Mình tìm thấy {len(products)} sản phẩm phù hợp trong hệ thống:"
            return (
                header + "\n"
                + "\n".join(lines)
                + "\nBạn có thể nói mức giá hoặc hương vị để mình lọc tiếp."
            )
        return "Kho sản phẩm đang cập nhật, bạn thử lại sau ít phút."

    if _contains_any(message, THANKS_KEYWORDS):
        return "Rất vui được hỗ trợ bạn. Cần gì bạn cứ nhắn mình ngay."

    return (
        "Mình đã hiểu ý bạn. Bạn có thể hỏi tự nhiên, ví dụ: "
        "'kiểm tra đơn #12', 'gợi ý chè thanh mát', 'có mã giảm giá không?'."
    )


def _call_openai(messages):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "missing_api_key"

    is_groq_key = api_key.startswith("gsk_")
    default_endpoint = "https://api.groq.com/openai/v1/chat/completions" if is_groq_key else "https://api.openai.com/v1/chat/completions"
    default_model = "llama-3.3-70b-versatile" if is_groq_key else "gpt-4o-mini"

    endpoint = os.environ.get("OPENAI_CHAT_ENDPOINT", default_endpoint).strip()
    model = os.environ.get("OPENAI_CHAT_MODEL", default_model).strip()
    timeout = _env_int("OPENAI_CHAT_TIMEOUT", 25)
    temperature = _env_float("OPENAI_CHAT_TEMPERATURE", 0.6)

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 500,
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except urllib.error.URLError:
        return None, "network_error"
    except TimeoutError:
        return None, "timeout"
    except Exception:
        return None, "unknown_error"

    try:
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
        if not content:
            return None, "empty_response"
        provider = "groq" if "groq.com" in endpoint else "openai"
        return content.strip(), f"llm_{provider}"
    except Exception:
        return None, "parse_error"


def _call_gemini(system_text, conversation_messages, user_message):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        return None, "missing_api_key"

    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    endpoint = os.environ.get(
        "GEMINI_ENDPOINT",
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
    ).strip()
    timeout = _env_int("GEMINI_TIMEOUT", 25)
    temperature = _env_float("GEMINI_TEMPERATURE", 0.6)
    max_tokens = _env_int("GEMINI_MAX_TOKENS", 700)

    contents = [{"role": "user", "parts": [{"text": system_text}]}]
    for item in conversation_messages[-MAX_HISTORY_MESSAGES:]:
        role = "user" if item["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": item["content"]}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except urllib.error.URLError:
        return None, "network_error"
    except TimeoutError:
        return None, "timeout"
    except Exception:
        return None, "unknown_error"

    try:
        parsed = json.loads(raw)
        candidates = parsed.get("candidates", [])
        if not candidates:
            return None, "empty_response"
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        if not text:
            return None, "empty_response"
        return text.strip(), "llm_gemini"
    except Exception:
        return None, "parse_error"


def generate_chat_reply(user, conversation_messages, user_message):
    context_text = _build_user_context(user)
    suggest_products, suggest_lines = _build_product_suggestions(user_message, limit=PRODUCT_SUGGESTION_LIMIT)
    catalog_text, catalog_products = _build_catalog_context(user_message)

    system_parts = [SYSTEM_PROMPT, f"Context user:\n{context_text}"]
    if catalog_text:
        system_parts.append("Context catalog:\n" + catalog_text)
    elif suggest_lines:
        system_parts.append("Gợi ý sản phẩm nhanh:\n" + "\n".join(suggest_lines))
    system_text = "\n\n".join(system_parts)

    has_gemini = bool(os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip())
    has_openai = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    llm_reply = None
    mode = "missing_api_key"

    if has_gemini:
        llm_reply, mode = _call_gemini(system_text, conversation_messages, user_message)

    if not llm_reply and has_openai:
        llm_messages = [{"role": "system", "content": system_text}]
        for item in conversation_messages[-MAX_HISTORY_MESSAGES:]:
            llm_messages.append({"role": item["role"], "content": item["content"]})
        llm_messages.append({"role": "user", "content": user_message})
        llm_reply, mode = _call_openai(llm_messages)

    if llm_reply:
        # Hard guard: if provider output is non-accented Vietnamese, force local Vietnamese response.
        if not _has_vietnamese_diacritics(llm_reply):
            fallback = _rule_based_reply(user, user_message)
            return fallback, "fallback_force_vi"
        if _looks_like_product_query(user_message):
            check_products = catalog_products or suggest_products
            if check_products:
                reply_lower = llm_reply.lower()
                if not any(product.name.lower() in reply_lower for product in check_products[:8]):
                    extra_lines = _format_product_lines(check_products[:8])
                    llm_reply += "\n\nGợi ý sản phẩm từ hệ thống:\n" + "\n".join(extra_lines)
        return llm_reply, mode

    fallback = _rule_based_reply(user, user_message)
    return fallback, f"fallback_{mode}"


def quick_replies():
    return [
        "Kiểm tra đơn hàng gần nhất",
        "Có mã giảm giá nào đang dùng?",
        "Gợi ý tất cả loại chè hiện có",
        "Hướng dẫn thanh toán bằng COD",
    ]
