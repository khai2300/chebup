import os

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ChatMessage, ChatSession
from .services.chat_ai import generate_chat_reply, quick_replies


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
        return JsonResponse({"response": "Ban hay nhap noi dung can ho tro.", "mode": "validation"}, status=400)

    session_obj = _get_or_create_chat_session(request.user)
    conversation = list(
        session_obj.messages.exclude(role=ChatMessage.ROLE_SYSTEM).values("role", "content")
    )

    ChatMessage.objects.create(session=session_obj, role=ChatMessage.ROLE_USER, content=message)
    response, mode = generate_chat_reply(request.user, conversation, message)
    ChatMessage.objects.create(session=session_obj, role=ChatMessage.ROLE_ASSISTANT, content=response)

    if session_obj.title == "Tro chuyen ho tro" and message:
        session_obj.title = message[:80]
        session_obj.save(update_fields=["title", "updated_at"])

    return JsonResponse(
        {
            "response": response,
            "mode": mode,
            "timestamp": timezone.localtime().strftime("%H:%M"),
        }
    )


@login_required
@require_POST
def chat_reset(request):
    ChatSession.objects.filter(user=request.user, is_active=True).update(is_active=False)
    ChatSession.objects.create(user=request.user, title="Tro chuyen ho tro", is_active=True)
    return JsonResponse({"ok": True})


def _get_or_create_chat_session(user):
    session_obj = ChatSession.objects.filter(user=user, is_active=True).first()
    if session_obj:
        return session_obj
    return ChatSession.objects.create(user=user, title="Tro chuyen ho tro", is_active=True)
