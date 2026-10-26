from django.urls import path, include
from django_school_management.api.routers import DefaultRouterWithoutFormatSuffixes
from .views import StudentViewSet, AdmissionStudentViewSet

router = DefaultRouterWithoutFormatSuffixes()
router.register(r'applications', AdmissionStudentViewSet, basename='admission')
router.register(r'', StudentViewSet, basename='student')

app_name = 'students_api'

urlpatterns = [
    path('', include(router.urls)),
]
