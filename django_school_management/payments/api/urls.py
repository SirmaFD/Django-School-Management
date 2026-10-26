from django.urls import path, include
from django_school_management.api.routers import DefaultRouterWithoutFormatSuffixes

# Create router and register viewsets here
router = DefaultRouterWithoutFormatSuffixes()
# router.register(r'payments', PaymentViewSet, basename='payment')

app_name = 'payments_api'

urlpatterns = [
    path('', include(router.urls)),
]
