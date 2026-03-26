import os

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ChatMessage, ChatSession
from .services.chat_ai import generate_chat_reply, quick_replies, suggest_products_for_chat


DEFAULT_CHAT_TITLE = "Trò chuyện hỗ trợ"


@login_required
def chat_view(request):
    session_obj = _get_or_create_chat_session(request.user)
    history = session_obj.messages.exclude(role=ChatMessage.ROLE_SYSTEM)
    has_llm = bool(
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    chat_mode = "llm" if has_llm else "fallback"
    return render(
        request,
        "shop/chat.html",
        {
            "chat_history": history,
            "quick_replies": quick_replies(),
            "chat_mode": chat_mode,
        },
    )


@login_required
@require_POST
def chat_api(request):
    message = request.POST.get("message", "").strip()
    if not message:
        return JsonResponse({"response": "Bạn hãy nhập nội dung cần hỗ trợ.", "mode": "validation"}, status=400)

    session_obj = _get_or_create_chat_session(request.user)
    conversation = list(session_obj.messages.exclude(role=ChatMessage.ROLE_SYSTEM).values("role", "content"))

    ChatMessage.objects.create(session=session_obj, role=ChatMessage.ROLE_USER, content=message)
    response, mode = generate_chat_reply(request.user, conversation, message)
    ChatMessage.objects.create(session=session_obj, role=ChatMessage.ROLE_ASSISTANT, content=response)

    suggested_products = suggest_products_for_chat(message, limit=None)
    products_payload = []

    for product in suggested_products:
        image_url = ""
        if product.image:
            try:
                image_url = product.image.url
            except Exception:
                image_url = ""
        if not image_url:
            image_url = product.image_url or ""

        products_payload.append(
            {
                "id": product.id,
                "name": product.name,
                "category": product.category.name if product.category else "",
                "stock": product.stock,
                "short_description": product.short_description or "",
                "price_text": f"{product.price:,.0f} VND",
                "product_url": reverse("shop:product_detail", args=[product.id]),
                "add_to_cart_url": reverse("shop:add_to_cart", args=[product.id]),
                "image_url": image_url,
            }
        )

    if session_obj.title == DEFAULT_CHAT_TITLE and message:
        session_obj.title = message[:80]
        session_obj.save(update_fields=["title", "updated_at"])

    return JsonResponse(
        {
            "response": response,
            "mode": mode,
            "timestamp": timezone.localtime().strftime("%H:%M"),
            "products": products_payload,
        }
    )


@login_required
@require_POST
def chat_reset(request):
    ChatSession.objects.filter(user=request.user, is_active=True).update(is_active=False)
    ChatSession.objects.create(user=request.user, title=DEFAULT_CHAT_TITLE, is_active=True)
    return JsonResponse({"ok": True})


def _get_or_create_chat_session(user):
    session_obj = ChatSession.objects.filter(user=user, is_active=True).first()
    if session_obj:
        return session_obj
    return ChatSession.objects.create(user=user, title=DEFAULT_CHAT_TITLE, is_active=True)
