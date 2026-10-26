from django.urls import path, include
from django_school_management.api.routers import DefaultRouterWithoutFormatSuffixes

# Create router and register viewsets here
router = DefaultRouterWithoutFormatSuffixes()
# router.register(r'departments', DepartmentViewSet, basename='department')
# router.register(r'batches', BatchViewSet, basename='batch')
# router.register(r'subjects', SubjectViewSet, basename='subject')

app_name = 'academics_api'

urlpatterns = [
    path('', include(router.urls)),
]
