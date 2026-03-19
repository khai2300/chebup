from django.conf import settings


def seo_defaults(request):
    site_url = (getattr(settings, "SITE_URL", "") or "").strip().rstrip("/")
    if not site_url:
        scheme = "https" if request.is_secure() else "http"
        site_url = f"{scheme}://{request.get_host()}".rstrip("/")

    path = request.path or "/"
    canonical_url = f"{site_url}{path}"
    return {
        "site_url": site_url,
        "canonical_url": canonical_url,
        "default_meta_description": getattr(
            settings,
            "DEFAULT_META_DESCRIPTION",
            "Che Bup Market - cua hang che sach Thai Nguyen, tra xanh, tra den, giao hang toan quoc.",
        ),
    }
