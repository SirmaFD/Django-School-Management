from django.db.models import Q

from ..management_forms import manageable_counties
from ..models import ECDEMembership


def can_manage_ecde(user):
    return user.is_authenticated and (
        user.is_superuser
        or ECDEMembership.objects.filter(
            user=user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            is_active=True,
        ).exists()
    )


def manageable_memberships(user):
    if user.is_superuser:
        return ECDEMembership.objects.all()
    counties = manageable_counties(user)
    return ECDEMembership.objects.filter(
        Q(county__in=counties)
        | Q(subcounty__county__in=counties)
        | Q(ward__subcounty__county__in=counties)
        | Q(centre__ward__subcounty__county__in=counties)
    ).distinct()