from django.conf import settings


def portal(request):
    return {"INSTITUTION_NAME": settings.INSTITUTION_NAME}
