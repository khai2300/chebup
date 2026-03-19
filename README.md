# Tea Shop Django

Ung dung web ban che bup su dung Django + Bootstrap + JavaScript.

## Chay nhanh

```powershell
cd c:\Users\admin\Documents\GitHub\bt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Mo trinh duyet: `http://127.0.0.1:8000`

## QR public ngoai mang (mien phi voi Cloudflare Tunnel)

1. Chay Django:

```powershell
python manage.py runserver 0.0.0.0:8000
```

2. Mo terminal khac va chay tunnel:

```cmd
cd /d %USERPROFILE%\Downloads
cloudflared.exe tunnel --url http://127.0.0.1:8000
```

3. Mo trang admin bang link `https://xxxxx.trycloudflare.com`.
   Khi mo tu domain tunnel, QR se tu dong tao link public theo tunnel (khong bi dính localhost/LAN).

Luu y: link `trycloudflare.com` la tam thoi, moi lan chay lai tunnel se doi link.

## Tai khoan admin mac dinh

- Username: `admin`
- Password: `admin123`

Neu chua co du lieu mau, trang chu se tu dong seed san pham khi truy cap lan dau.

## Luu y GitHub

- `.env`, `db.sqlite3`, `media/`, `staticfiles/`, `.venv/`, `__pycache__/` da duoc gitignore.
- Mau bien moi truong nam trong `.env.example`.
- Du lieu mau seeding nam trong `shop/services/seed.py`.

## Thu muc giao dien

- `django_ui/templates/shop`
- `django_ui/static/shop`

## URL chinh

- `/` danh sach san pham
- `/robots.txt`
- `/sitemap.xml`
- `/register/`, `/login/`, `/logout/`
- `/cart/`, `/checkout/`
- `/account/`, `/orders/`
- `/trace/product/<product_id>/` truy xuat nguon tung san pham
- `/product/<product_id>/trace-qr.png` QR truy xuat san pham
- `/chat/`
- `/dashboard/admin/`

## Chat AI hoan chinh (LLM + fallback)

Chat se tu dong chay theo 2 che do:

- Co API key: goi LLM that (Gemini hoac Groq/OpenAI compatible), co nho ngu canh hoi thoai.
- Khong co API key: fllback thong minh dua tren du lieu don hang/san pham.

### Cau hinh Gemini (PowerShell)

```powershell
$env:GEMINI_API_KEY="YOUR_GEMINI_KEY"
$env:GEMINI_MODEL="gemini-2.5-flash"
python manage.py runserver
```
### Cau hinh Groq (PowerShell)

```powershell
$env:OPENAI_API_KEY="YOUR_GROQ_KEY"
$env:OPENAI_CHAT_ENDPOINT="https://api.groq.com/openai/v1/chat/completions"
$env:OPENAI_CHAT_MODEL="llama-3.3-70b-versatile"
python manage.py runserver
```

### Bien moi truong ho tro

- `GEMINI_API_KEY` (hoac `GOOGLE_API_KEY`)
- `GEMINI_MODEL` (optional, mac dinh `gemini-2.5-flash`)
- `GEMINI_ENDPOINT` (optional)
- `GEMINI_TIMEOUT` (optional, mac dinh `25`)
- `GEMINI_TEMPERATURE` (optional, mac dinh `0.6`)
- `GEMINI_MAX_TOKENS` (optional)
- `OPENAI_API_KEY`
- `OPENAI_CHAT_ENDPOINT` (optional)
- `OPENAI_CHAT_MODEL` (optional)
- `OPENAI_CHAT_TIMEOUT` (optional, mac dinh `25`)
- `OPENAI_CHAT_TEMPERATURE` (optional, mac dinh `0.6`)
- `ORDER_NOTIFY_TO` (email nhan thong bao don hang, co the nhieu email cach nhau boi dau phay)
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`
- `SITE_URL` (nen dat domain that, vi du `https://yourdomain.com`)
- `DEFAULT_META_DESCRIPTION` (optional)

### Gmail SMTP cho thong bao don hang

Vi du nhanh trong `.env`:

```env
ORDER_NOTIFY_TO=nhoc15527@gmail.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=nhoc15527@gmail.com
EMAIL_HOST_PASSWORD=your_gmail_app_password
DEFAULT_FROM_EMAIL=nhoc15527@gmail.com
```

Luu y: `EMAIL_HOST_PASSWORD` la **App Password** cua Gmail, khong phai mat khau dang nhap thuong.


## SEO + Google

- He thong da co `robots.txt` va `sitemap.xml` de Google crawl/index.
- Dat `SITE_URL` trong `.env` dung domain that cua ban.
- Sau khi deploy, vao Google Search Console:
  - Verify domain.
  - Submit `https://yourdomain.com/sitemap.xml`.
  - Request indexing trang chu va trang san pham.

## Upload anh tu thu muc may tinh

- Vao: `/dashboard/admin/products/`
- O form "Them san pham moi", chon file trong o `Anh` de upload tu may tinh.
- Co the cap nhat anh nhanh tung san pham ngay trong bang danh sach.
