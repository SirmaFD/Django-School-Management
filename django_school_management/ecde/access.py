from django.db.models import Q

from .models import ECDEAuditEvent, ECDECentre, ECDEMembership


def accessible_centres(user):
    """Return centres within the active ECDE memberships assigned to a user."""
    if not user.is_authenticated:
        return ECDECentre.objects.none()
    if user.is_superuser:
        return ECDECentre.objects.filter(is_active=True)

    memberships = ECDEMembership.objects.filter(user=user, is_active=True)
    membership_list = list(memberships.select_related(
        'county', 'subcounty', 'ward', 'centre',
    ))
    if not membership_list:
        return ECDECentre.objects.none()

    scope = Q()
    for membership in membership_list:
        if membership.role == ECDEMembership.ROLE_COUNTY_ADMIN:
            scope |= Q(ward__subcounty__county_id=membership.county_id)
        elif membership.role == ECDEMembership.ROLE_SUBCOUNTY_OFFICER:
            scope |= Q(ward__subcounty_id=membership.subcounty_id)
        elif membership.role == ECDEMembership.ROLE_WARD_COORDINATOR:
            scope |= Q(ward_id=membership.ward_id)
        elif membership.centre_id:
            scope |= Q(pk=membership.centre_id)
    return ECDECentre.objects.filter(scope, is_active=True).distinct()


def can_record_at_centre(user, centre):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return ECDEMembership.objects.filter(
        user=user,
        is_active=True,
        role__in=[
            ECDEMembership.ROLE_CENTRE_MANAGER,
            ECDEMembership.ROLE_ECDE_TEACHER,
        ],
        centre=centre,
    ).exists()


def accessible_ecde_teachers(user):
    return ECDEMembership.objects.filter(
        user__is_active=True,
        is_active=True,
        role=ECDEMembership.ROLE_ECDE_TEACHER,
        centre__in=accessible_centres(user),
    ).select_related(
        'user', 'centre__ward__subcounty__county', 'teacher_profile',
    )


def accessible_audit_events(user):
    if not user.is_authenticated:
        return ECDEAuditEvent.objects.none()
    if user.is_superuser:
        return ECDEAuditEvent.objects.all()

    memberships = ECDEMembership.objects.filter(user=user, is_active=True)
    scope = Q()
    for membership in memberships.select_related(
        'county', 'subcounty', 'ward', 'centre',
    ):
        if membership.role == ECDEMembership.ROLE_COUNTY_ADMIN:
            scope |= (
                Q(county_id=membership.county_id)
                | Q(related_centre__ward__subcounty__county_id=membership.county_id)
            )
        elif membership.role == ECDEMembership.ROLE_SUBCOUNTY_OFFICER:
            scope |= (
                Q(subcounty_id=membership.subcounty_id)
                | Q(related_centre__ward__subcounty_id=membership.subcounty_id)
            )
        elif membership.role == ECDEMembership.ROLE_WARD_COORDINATOR:
            scope |= (
                Q(ward_id=membership.ward_id)
                | Q(related_centre__ward_id=membership.ward_id)
            )
        elif membership.centre_id:
            scope |= (
                Q(centre_id=membership.centre_id)
                | Q(related_centre_id=membership.centre_id)
            )
    if not scope.children:
        return ECDEAuditEvent.objects.none()
    return ECDEAuditEvent.objects.filter(scope).select_related(
        'actor', 'county', 'subcounty', 'ward', 'centre', 'related_centre',
    )
