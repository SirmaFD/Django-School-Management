from django.urls import path, include
from django_school_management.api.routers import DefaultRouterWithoutFormatSuffixes
from .views import ArticleViewSet

router = DefaultRouterWithoutFormatSuffixes()
# Main resource at '' so URL is /api/v1/articles/ not /api/v1/articles/articles/
router.register(r'', ArticleViewSet, basename='article')

app_name = 'articles_api'

urlpatterns = [
    path('', include(router.urls)),
]
