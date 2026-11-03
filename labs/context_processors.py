from django.conf import settings


def lab_settings(request):
    return {
        "LAB_DOMAIN": settings.LAB_DOMAIN,
        "LAB_MQTT_HOST": settings.LAB_MQTT_HOST,
        "LAB_MQTT_PORT": settings.LAB_MQTT_PORT,
        "LAB_SSH_HOST": settings.LAB_SSH_HOST,
    }
