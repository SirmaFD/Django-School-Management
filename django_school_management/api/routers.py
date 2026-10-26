from rest_framework.routers import DefaultRouter


class DefaultRouterWithoutFormatSuffixes(DefaultRouter):
    """Avoid duplicate global converter registration across API routers."""

    include_format_suffixes = False
