"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

# config/urls.py
from django.urls import include, path

from gateway.views import check_microservice, liveness_health, wake_services

urlpatterns = [
    path("health", liveness_health, name="gateway-liveness"),
    path("wake", wake_services, name="gateway-wake"),
    path("check_microservice", check_microservice, name="check-microservice"),
    path("", include("gateway.urls")),
]
