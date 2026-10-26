from django_school_management.academics.constants import AcademicsURLConstants
from django_school_management.accounts.constants import AccountURLConstants
from django_school_management.accounts.services.menu import MenuService
from django_school_management.accounts.utils.menu_config import get_menu_config
from django_school_management.institute.models import (
    InstituteProfile,
    TextWidget,
    ListWidget,
)
from django_school_management.articles.models import Category
from django_school_management.ecde.access import accessible_centres
from django_school_management.ecde.management import can_manage_ecde
from django_school_management.ecde.models import ECDEMembership
from django.urls import reverse


def attach_institute_data_ctx_processor(request):
    institute = None
    if hasattr(request, 'user') and request.user.is_authenticated:
        institute = getattr(request.user, 'institute', None)
    if not institute:
        try:
            institute = InstituteProfile.objects.get(active=True)
        except InstituteProfile.DoesNotExist:
            institute = None
    ctx = {
        "request_institute": institute,
        "department_label": institute.department_label if institute else "Department",
        "semester_label": institute.semester_label if institute else "Semester",
        "department_label_plural": institute.department_label_plural if institute else "Departments",
        "semester_label_plural": institute.semester_label_plural if institute else "Semesters",
    }

    if "articles" in request.resolver_match._func_path.split("."):
        # If request is coming for articles app's views,
        # only then pass registered_navlinks in the context.
        # Registered navlinks are Category objects from the articles app.
        try:
            registered_navlinks = Category.objects.filter(
                display_on_menu=True,
            ).order_by("-created")
        except:
            registered_navlinks = []
        try:
            # Setting up widgets for footer and other places of the
            # website. (TODO: Add location hints to the widget models).
            # first text-widget for the footer (footer-col-number-1)
            first_widget = TextWidget.objects.get(widget_number=0)
            # get rest three widgets
            list_widgets = ListWidget.objects.filter(widget_number__lte=4)
        except (TextWidget.DoesNotExist, Exception):
            first_widget = None
            list_widgets = None

        ctx["registered_navlinks"] = registered_navlinks
        ctx["first_widget"] = first_widget
        ctx["list_widgets"] = list_widgets
    return ctx


def attach_urls_for_common_templates(request):
    return dict(
        account_urls=AccountURLConstants,
        academic_urls=AcademicsURLConstants,
    )


def attach_dashboard_menu_items(request):
    if request.user.is_authenticated:
        menu_cofig = get_menu_config(request.user)
        menu_service = MenuService(menu_cofig)
        student_menu_items = menu_service.get_menu_items(
            "student", request.user
        )
        teacher_menu_items = menu_service.get_menu_items(
            "teacher", request.user
        )
        has_ecde_access = request.user.is_superuser or ECDEMembership.objects.filter(
            user=request.user,
            is_active=True,
        ).exists()
        ecde_menu_items = []
        if has_ecde_access:
            ecde_menu_items.append({
                "title": "ECDE dashboard",
                "url": reverse("ecde:dashboard"),
            })
            if can_manage_ecde(request.user):
                ecde_menu_items.extend([
                    {
                        "title": "Manage administrative areas",
                        "url": reverse("ecde:manage"),
                    },
                    {
                        "title": "Manage counties",
                        "url": reverse("ecde:manage_counties"),
                    },
                    {
                        "title": "Manage sub-counties",
                        "url": reverse("ecde:manage_subcounties"),
                    },
                    {
                        "title": "Manage wards",
                        "url": reverse("ecde:manage_wards"),
                    },
                    {
                        "title": "Manage centres",
                        "url": reverse("ecde:manage_centres"),
                    },
                    {
                        "title": "Add ECDE centre",
                        "url": reverse("ecde:add_centre"),
                    },
                    {
                        "title": "County supply stock & distribution",
                        "url": reverse("ecde:county_supply_stock"),
                    },
                ])
            ecde_menu_items.append({
                "title": "Activity history",
                "url": reverse("ecde:audit_log"),
            })
            for centre in accessible_centres(request.user).order_by("name"):
                ecde_menu_items.extend([
                    {
                        "title": f"{centre.name} / Learners",
                        "url": reverse("ecde:children", args=[centre.pk]),
                    },
                    {
                        "title": f"{centre.name} / Attendance",
                        "url": reverse("ecde:attendance", args=[centre.pk]),
                    },
                    {
                        "title": f"{centre.name} / CBC progress",
                        "url": reverse("ecde:progress", args=[centre.pk]),
                    },
                    {
                        "title": f"{centre.name} / Planning & resources",
                        "url": reverse("ecde:resources", args=[centre.pk]),
                    },
                ])
        return dict(
            student_menu_items=student_menu_items,
            teacher_menu_items=teacher_menu_items,
            has_ecde_access=has_ecde_access,
            can_manage_ecde=can_manage_ecde(request.user),
            ecde_menu_items=ecde_menu_items,
        )
    return dict(
        student_menu_items=[],
        teacher_menu_items=[],
        has_ecde_access=False,
        can_manage_ecde=False,
        ecde_menu_items=[],
    )
