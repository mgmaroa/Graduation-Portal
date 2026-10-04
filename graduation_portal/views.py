from django.conf import settings
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import LookupForm
from .models import Graduand, LookupAttempt
from .security import get_client_ip, is_rate_limited


def _private(response):
    """Keep result pages out of search engines, caches and shared proxies."""
    response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response["Cache-Control"] = "no-store, private"
    return response


@require_http_methods(["GET", "POST"])
@never_cache
def lookup(request):
    form = LookupForm()

    if request.method == "POST":
        ip = get_client_ip(request)

        if is_rate_limited(ip):
            response = render(
                request, "graduation/blocked.html",
                {"minutes": settings.LOOKUP_WINDOW_MINUTES}, status=429,
            )
            response["Retry-After"] = str(settings.LOOKUP_WINDOW_MINUTES * 60)
            return _private(response)

        form = LookupForm(request.POST)
        if form.is_valid():
            admission_no = form.cleaned_data["admission_no"]
            graduand = Graduand.objects.filter(admission_no=admission_no).first()
            LookupAttempt.objects.create(
                ip_address=ip, searched_value=admission_no, found=graduand is not None,
            )
            # Rendered directly (no redirect) so the number never appears in a URL.
            if graduand:
                return _private(render(request, "graduation/eligible.html", {"graduand": graduand}))
            return _private(render(request, "graduation/regret.html"))

    return _private(render(request, "graduation/lookup.html", {"form": form}))


def robots_txt(request):
    from django.http import HttpResponse
    return HttpResponse("User-agent: *\nDisallow: /\n", content_type="text/plain")