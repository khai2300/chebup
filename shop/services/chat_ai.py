import json
import os
import re
import urllib.error
import urllib.request
from decimal import Decimal

from django.utils import timezone

from shop.models import Address, Order, Product, Promotion


SYSTEM_PROMPT = (
    "Ban la tro ly ban che bup trong he thong ecommerce. "
    "Tra loi bang tieng Viet khong dau, than thien, ngan gon, khong may moc. "
    "Neu thong tin lien quan den don hang cua user da co trong context thi uu tien su dung dung du lieu do. "
    "Khong tu tao chinh sach khong co trong context. "
    "Neu user hoi ve san pham/tra, uu tien de xuat san pham tu he thong neu co."
)

PROMO_LIMIT = 5
MAX_HISTORY_MESSAGES = 12
PRODUCT_SUGGESTION_LIMIT = 3
DEFAULT_CHAT_PRODUCTS_LIMIT = 20
DEFAULT_CATALOG_CONTEXT_LIMIT = 200

GREETING_KEYWORDS = ["xin chao", "chao", "hello", "hi"]
PROMO_KEYWORDS = ["khuyen mai", "voucher", "ma giam", "giam gia"]
ORDER_KEYWORDS = ["don hang", "trang thai", "kiem tra don", "order", "ma don"]
CANCEL_KEYWORDS = ["huy don", "huy"]
SHIPPING_KEYWORDS = ["giao hang", "ship", "van chuyen"]
PAYMENT_KEYWORDS = ["thanh toan", "payment", "cod", "bank", "vi"]
ADDRESS_KEYWORDS = ["dia chi", "address"]
PRODUCT_KEYWORDS = ["goi y", "de xuat", "san pham", "che", "tra", "nen mua", "mua gi", "tat ca"]
THANKS_KEYWORDS = ["cam on", "thanks", "thank"]


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


def _contains_any(message, keywords):
    text = (message or "").lower()
    return any(word in text for word in keywords)


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
    match = re.search(r"(?:#|don\\s*|order\\s*)(\\d{1,8})", text.lower())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _order_status_text(status):
    mapping = {
        Order.STATUS_PENDING: "dang cho xac nhan",
        Order.STATUS_PROCESSING: "dang xu ly",
        Order.STATUS_SHIPPED: "dang giao",
        Order.STATUS_DELIVERED: "da giao",
        Order.STATUS_CANCELLED: "da huy",
    }
    return mapping.get(status, status)


def _looks_like_product_query(message):
    return _contains_any(message, PRODUCT_KEYWORDS)


def _product_search_tokens(text):
    return [token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 2]


def _score_product(product, tokens):
    haystack = (
        f"{product.name} {product.short_description} {product.description} {product.category.name}"
    ).lower()
    score = sum(1 for token in set(tokens) if token in haystack)
    return score, product.stock, -float(product.price)


def _rank_products(user_message):
    products = list(Product.objects.select_related("category").all())
    if not products:
        return []

    tokens = _product_search_tokens(user_message)
    if not tokens:
        return sorted(products, key=lambda p: (-p.stock, float(p.price), p.category.name, p.name))

    scored = []
    for product in products:
        score, stock, price_key = _score_product(product, tokens)
        scored.append((score, stock, price_key, product.category.name, product.name, product))

    scored.sort(reverse=True, key=lambda item: (item[0], item[1], item[2]))
    ranked = [item[5] for item in scored]

    # Neu co ket qua match, uu tien nhung item co score > 0 truoc, sau do bo sung phan con lai.
    matched = [item[5] for item in scored if item[0] > 0]
    unmatched = [item for item in ranked if item not in matched]
    return matched + unmatched


def _format_product_line(product):
    desc = (product.short_description or "").strip()
    desc_text = f" - {desc}" if desc else ""
    stock_text = f"Ton: {product.stock}"
    return (
        f"- {product.name} ({_format_money(product.price)}) | Danh muc: {product.category.name} | "
        f"{stock_text}{desc_text} | /product/{product.id}/"
    )


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

    limit = max(1, _env_int("CHAT_CATALOG_CONTEXT_LIMIT", DEFAULT_CATALOG_CONTEXT_LIMIT))
    catalog = ranked[:limit]

    category_counts = {}
    for product in catalog:
        category_counts[product.category.name] = category_counts.get(product.category.name, 0) + 1

    category_summary = "; ".join(
        f"{category}: {count}" for category, count in sorted(category_counts.items(), key=lambda item: item[0].lower())
    )
    lines = _format_product_lines(catalog)

    context = [
        f"Tong so san pham trong catalog dua vao prompt: {len(catalog)}",
        "So luong theo danh muc: " + category_summary,
        "Danh sach chi tiet:",
        *lines,
    ]
    return "\n".join(context), catalog


def suggest_products_for_chat(user_message, limit=None):
    if not _looks_like_product_query(user_message):
        return []

    ranked = _rank_products(user_message)
    if limit is None:
        limit = _env_int("CHAT_PRODUCTS_LIMIT", DEFAULT_CHAT_PRODUCTS_LIMIT)

    if limit <= 0:
        return ranked
    return ranked[:limit]


def _build_user_context(user):
    latest_orders = Order.objects.filter(user=user).select_related("address").order_by("-created_at")[:3]
    default_address = Address.objects.filter(user=user, is_default=True).first()
    if default_address is None:
        default_address = Address.objects.filter(user=user).first()
    promotions = _active_promotions()

    lines = [f"Ten user: {user.username}"]
    if default_address:
        lines.append(f"Dia chi mac dinh: {default_address.full_address}")
    else:
        lines.append("Dia chi mac dinh: chua co")

    if latest_orders:
        for order in latest_orders:
            lines.append(f"Don #{order.id}: {_order_status_text(order.status)}, tong {_format_money(order.final_amount)}")
    else:
        lines.append("Don hang: chua co don nao")

    if promotions:
        lines.append("Khuyen mai dang hoat dong: " + ", ".join(promotions))
    else:
        lines.append("Khuyen mai dang hoat dong: chua co")

    return "\n".join(lines)


def _rule_based_reply(user, user_message):
    message = (user_message or "").strip().lower()
    if not message:
        return "Ban cu nhan cau hoi, minh se ho tro ngay."

    if _contains_any(message, GREETING_KEYWORDS):
        latest = Order.objects.filter(user=user).order_by("-created_at").first()
        if latest:
            return f"Chao {user.username}. Don gan nhat cua ban la #{latest.id}, hien {_order_status_text(latest.status)}."
        return f"Chao {user.username}. Ban can minh goi y che, kiem tra don hay ma giam gia?"

    if _contains_any(message, PROMO_KEYWORDS):
        promos = _active_promotions()
        if promos:
            return "Hien shop dang co: " + ", ".join(promos) + ". Ban nhap ma o buoc checkout."
        return "Hien tai chua co ma giam gia dang hoat dong."

    if _contains_any(message, ORDER_KEYWORDS):
        target_id = _extract_order_id(message)
        order_qs = Order.objects.filter(user=user)
        order = order_qs.filter(id=target_id).first() if target_id else order_qs.order_by("-created_at").first()
        if order:
            return f"Don #{order.id} hien {_order_status_text(order.status)}. Tong thanh toan {_format_money(order.final_amount)}."
        return "Minh chua tim thay don phu hop. Ban thu gui ma don dang #123."

    if _contains_any(message, CANCEL_KEYWORDS):
        pending = Order.objects.filter(user=user, status=Order.STATUS_PENDING).order_by("-created_at")
        if pending.exists():
            ids = ", ".join(f"#{order.id}" for order in pending[:3])
            return f"Ban dang co {pending.count()} don co the huy ({ids}). Vao trang Don hang va bam Huy don."
        return "Hien tai ban khong co don Pending de huy."

    if _contains_any(message, SHIPPING_KEYWORDS):
        shipping_order = (
            Order.objects.filter(user=user, status__in=[Order.STATUS_PROCESSING, Order.STATUS_SHIPPED])
            .order_by("-created_at")
            .first()
        )
        if shipping_order:
            return f"Don #{shipping_order.id} dang {_order_status_text(shipping_order.status)}. Thuong mat 1-3 ngay lam viec tuy khu vuc."
        return "Thoi gian giao thuong 1-3 ngay lam viec tuy khu vuc."

    if _contains_any(message, PAYMENT_KEYWORDS):
        return "Shop ho tro 2 cach thanh toan: COD va online bang ngan hang (co ma QR)."

    if _contains_any(message, ADDRESS_KEYWORDS):
        count = Address.objects.filter(user=user).count()
        if count == 0:
            return "Ban chua co dia chi. Vao Tai khoan de them dia chi truoc khi checkout."
        return f"Ban dang co {count} dia chi giao hang. Ban co the dat 1 dia chi mac dinh."

    if _contains_any(message, PRODUCT_KEYWORDS):
        products = suggest_products_for_chat(message, limit=10)
        if products:
            lines = _format_product_lines(products)
            return (
                f"Minh tim thay {len(products)} san pham phu hop trong he thong:\n"
                + "\n".join(lines)
                + "\nBan co the noi muc gia hoac huong vi de minh loc tiep."
            )
        return "Kho san pham dang cap nhat, ban thu lai sau it phut."

    if _contains_any(message, THANKS_KEYWORDS):
        return "Rat vui duoc ho tro ban. Can gi ban cu nhan minh ngay."

    return (
        "Minh da hieu y ban. Ban co the hoi tu nhien, vi du: "
        "'kiem tra don #12', 'goi y che thanh mat', 'co ma giam gia khong?'."
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
        system_parts.append("Goi y san pham nhanh:\n" + "\n".join(suggest_lines))
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
        if _looks_like_product_query(user_message):
            check_products = catalog_products or suggest_products
            if check_products:
                reply_lower = llm_reply.lower()
                if not any(product.name.lower() in reply_lower for product in check_products[:8]):
                    extra_lines = _format_product_lines(check_products[:8])
                    llm_reply += "\n\nGoi y san pham tu he thong:\n" + "\n".join(extra_lines)
        return llm_reply, mode

    fallback = _rule_based_reply(user, user_message)
    return fallback, f"fallback_{mode}"


def quick_replies():
    return [
        "Kiem tra don hang gan nhat",
        "Co ma giam gia nao dang dung?",
        "Goi y tat ca loai che hien co",
        "Huong dan thanh toan bang COD",
    ]
