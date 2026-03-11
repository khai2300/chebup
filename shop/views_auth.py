from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import UserProfile

User = get_user_model()


def register_view(request):
    if request.user.is_authenticated:
        return redirect("shop:home")

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        email = request.POST.get("email", "").strip().lower()
        username = request.POST.get("username", "").strip()
        password1 = request.POST.get("password1", "")
        password2 = request.POST.get("password2", "")

        if not all([full_name, phone, email, username, password1, password2]):
            messages.error(request, "Vui long nhap day du thong tin.")
            return redirect("shop:register")
        if password1 != password2:
            messages.error(request, "Mat khau xac nhan khong khop.")
            return redirect("shop:register")
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username da ton tai.")
            return redirect("shop:register")
        if User.objects.filter(email=email).exists():
            messages.error(request, "Email da ton tai.")
            return redirect("shop:register")

        user = User.objects.create_user(username=username, email=email, password=password1)
        UserProfile.objects.create(user=user, full_name=full_name, phone=phone)
        messages.success(request, "Dang ky thanh cong. Ban co the dang nhap ngay.")
        return redirect("shop:login")

    return render(request, "shop/auth/register.html")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("shop:home")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        auth_username = username
        if "@" in username:
            user_obj = User.objects.filter(email__iexact=username).first()
            auth_username = user_obj.username if user_obj else username

        user = authenticate(request, username=auth_username, password=password)
        if user is None:
            messages.error(request, "Thong tin dang nhap khong dung.")
            return redirect("shop:login")
        if not user.is_active:
            messages.error(request, "Tai khoan da bi khoa.")
            return redirect("shop:login")
        login(request, user)
        messages.success(request, "Dang nhap thanh cong.")
        return redirect("shop:home")

    return render(request, "shop/auth/login.html")


@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "Ban da dang xuat.")
    return redirect("shop:login")
