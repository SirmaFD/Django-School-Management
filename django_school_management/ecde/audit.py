from .models import ECDEAuditEvent


def record_audit_event(
    *,
    actor,
    action,
    summary,
    centre=None,
    county=None,
    subcounty=None,
    ward=None,
    details=None,
    related_centre=None,
):
    if centre is not None:
        ward = centre.ward
    if ward is not None:
        subcounty = ward.subcounty
    if subcounty is not None:
        county = subcounty.county

    return ECDEAuditEvent.objects.create(
        actor=actor if actor.is_authenticated else None,
        action=action,
        summary=summary,
        details=details or {},
        county=county,
        subcounty=subcounty,
        ward=ward,
        centre=centre,
        related_centre=related_centre,
    )
