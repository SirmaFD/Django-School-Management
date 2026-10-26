from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .access import (
    accessible_audit_events, accessible_centres, can_record_at_centre,
)
from .audit import record_audit_event
from .forms import (
    AttendanceRecordForm, CBCProgressRecordForm, ECDEChildForm,
    ECDEChildLifecycleForm, ECDEChildProfileForm, ECDEChildTransferForm,
)
from .management import can_manage_ecde, manageable_memberships
from .management_forms import (
    CountyForm, ECDECentreForm, ECDEMembershipForm, ECDETeacherProfileForm,
    SubCountyForm, WardForm, manageable_counties,
)
from .models import (
    AttendanceRecord, CBCProgressRecord, County, ECDECentre, ECDEChild,
    ECDEMembership, ECDETeacherProfile, SubCounty, Ward,
)


def _centre_for_user(user, centre_id):
    return get_object_or_404(accessible_centres(user), pk=centre_id)


@login_required
def dashboard(request):
    today = timezone.localdate()
    centre_scope = accessible_centres(request.user)
    summary = centre_scope.aggregate(
        centre_count=Count('pk', distinct=True),
        active_children=Count(
            'children', filter=Q(children__is_active=True), distinct=True,
        ),
        attendance_today=Count(
            'attendance_records',
            filter=Q(attendance_records__date=today),
            distinct=True,
        ),
        progress_today=Count(
            'progress_records',
            filter=Q(progress_records__evidence_date=today),
            distinct=True,
        ),
    )
    centres = centre_scope.select_related(
        'ward__subcounty__county',
    ).annotate(active_children_count=Count(
        'children', filter=Q(children__is_active=True), distinct=True,
    ))
    return render(request, 'ecde/dashboard.html', {
        'centres': centres,
        'summary': summary,
        'can_manage_ecde': can_manage_ecde(request.user),
    })


@login_required
def manage(request):
    if not can_manage_ecde(request.user):
        raise PermissionDenied

    # Keep existing form submissions working while the hierarchy has dedicated pages.
    legacy_create_forms = {
        'create_county': (CountyForm, County),
        'create_subcounty': (SubCountyForm, SubCounty),
        'create_ward': (WardForm, Ward),
    }
    action = request.POST.get('action') if request.method == 'POST' else None
    if action in legacy_create_forms:
        form_class, model = legacy_create_forms[action]
        if model is County and not request.user.is_superuser:
            raise PermissionDenied
        form_kwargs = {'data': request.POST}
        if form_class is not CountyForm:
            form_kwargs['user'] = request.user
        form = form_class(**form_kwargs)
        if form.is_valid():
            try:
                with transaction.atomic():
                    instance = form.save()
                    record_audit_event(
                        actor=request.user,
                        action='create',
                        summary=f'{instance._meta.verbose_name.title()} '
                        f'{instance.name} was created.',
                        **_hierarchy_audit_fields(instance),
                    )
            except IntegrityError:
                form.add_error(
                    None,
                    'A record with that name or code already exists in this area.',
                )
            else:
                messages.success(request, f'{instance} was created.')
                return redirect('ecde:manage')

    counties = manageable_counties(request.user)
    return render(request, 'ecde/manage.html', {
        'county_count': counties.count(),
        'subcounty_count': SubCounty.objects.filter(county__in=counties).count(),
        'ward_count': Ward.objects.filter(subcounty__county__in=counties).count(),
        'can_create_county': request.user.is_superuser,
        'legacy_form_errors': form if action in legacy_create_forms else None,
    })


def _hierarchy_audit_fields(instance):
    if isinstance(instance, County):
        return {'county': instance}
    if isinstance(instance, SubCounty):
        return {'county': instance.county, 'subcounty': instance}
    return {
        'county': instance.subcounty.county,
        'subcounty': instance.subcounty,
        'ward': instance,
    }


def _hierarchy_has_dependents(instance):
    if isinstance(instance, County):
        return instance.subcounties.exists() or instance.memberships.exists()
    if isinstance(instance, SubCounty):
        return instance.wards.exists() or instance.memberships.exists()
    return instance.centres.exists() or instance.memberships.exists()


def _manage_hierarchy_page(
    request, *, form_class, queryset, route_name, template_name,
    label, allow_create=True,
):
    action = request.POST.get('action') if request.method == 'POST' else None
    object_id = request.POST.get('object_id') if request.method == 'POST' else None
    submitted_form = None

    if action in {'create', 'update'}:
        if action == 'create' and not allow_create:
            raise PermissionDenied
        instance = None
        if action == 'update':
            instance = get_object_or_404(queryset, pk=object_id)
        form_kwargs = {'data': request.POST, 'instance': instance}
        if form_class is not CountyForm:
            form_kwargs['user'] = request.user
        form = form_class(**form_kwargs)
        if form.is_valid():
            try:
                with transaction.atomic():
                    saved = form.save()
                    record_audit_event(
                        actor=request.user,
                        action='create' if action == 'create' else 'update',
                        summary=f'{label} {saved.name} was '
                        f'{"created" if action == "create" else "updated"}.',
                        **_hierarchy_audit_fields(saved),
                    )
            except IntegrityError:
                form.add_error(
                    None,
                    'A record with that name or code already exists in this area.',
                )
            else:
                messages.success(
                    request,
                    f'{label} {saved.name} was '
                    f'{"created" if action == "create" else "updated"}.',
                )
                return redirect(route_name)
        submitted_form = form

    elif action == 'delete':
        instance = get_object_or_404(queryset, pk=object_id)
        name = instance.name
        if _hierarchy_has_dependents(instance):
            messages.error(
                request,
                f'{label} {name} cannot be deleted while it has dependent '
                'areas, centres, or staff assignments. Remove or reassign '
                'those records first.',
            )
        else:
            try:
                with transaction.atomic():
                    record_audit_event(
                        actor=request.user,
                        action='status',
                        summary=f'{label} {name} was deleted.',
                        details={'deleted_id': instance.pk, 'record_type': label},
                        **_hierarchy_audit_fields(instance),
                    )
                    instance.delete()
            except ProtectedError:
                messages.error(
                    request,
                    f'{label} {name} cannot be deleted while protected '
                    'records still reference it.',
                )
            else:
                messages.success(request, f'{label} {name} was deleted.')
                return redirect(route_name)

    create_form = None
    if allow_create:
        create_kwargs = {'data': request.POST if action == 'create' else None}
        if form_class is not CountyForm:
            create_kwargs['user'] = request.user
        create_form = (
            submitted_form
            if action == 'create' and submitted_form
            else form_class(**create_kwargs)
        )

    editors = []
    for instance in queryset:
        form_kwargs = {'instance': instance, 'prefix': f'record-{instance.pk}'}
        if form_class is not CountyForm:
            form_kwargs['user'] = request.user
        edit_form = (
            submitted_form
            if action == 'update'
            and submitted_form
            and submitted_form.instance.pk == instance.pk
            else form_class(**form_kwargs)
        )
        editors.append({'object': instance, 'form': edit_form})

    return render(request, template_name, {
        'create_form': create_form,
        'editors': editors,
        'can_create': allow_create,
        'label': label,
    })


@login_required
def manage_counties(request):
    if not can_manage_ecde(request.user):
        raise PermissionDenied
    counties = manageable_counties(request.user).order_by('name')
    return _manage_hierarchy_page(
        request,
        form_class=CountyForm,
        queryset=counties,
        route_name='ecde:manage_counties',
        template_name='ecde/manage_counties.html',
        label='County',
        allow_create=request.user.is_superuser,
    )


@login_required
def manage_subcounties(request):
    if not can_manage_ecde(request.user):
        raise PermissionDenied
    subcounties = SubCounty.objects.filter(
        county__in=manageable_counties(request.user),
    ).select_related('county').order_by('county__name', 'name')
    return _manage_hierarchy_page(
        request,
        form_class=SubCountyForm,
        queryset=subcounties,
        route_name='ecde:manage_subcounties',
        template_name='ecde/manage_subcounties.html',
        label='Sub-county',
    )


@login_required
def manage_wards(request):
    if not can_manage_ecde(request.user):
        raise PermissionDenied
    wards = Ward.objects.filter(
        subcounty__county__in=manageable_counties(request.user),
    ).select_related('subcounty__county').order_by(
        'subcounty__county__name', 'subcounty__name', 'name',
    )
    return _manage_hierarchy_page(
        request,
        form_class=WardForm,
        queryset=wards,
        route_name='ecde:manage_wards',
        template_name='ecde/manage_wards.html',
        label='Ward',
    )


@login_required
def manage_centres(request):
    if not can_manage_ecde(request.user):
        raise PermissionDenied

    centres = ECDECentre.objects.filter(
        ward__subcounty__county__in=manageable_counties(request.user),
    ).select_related('ward__subcounty__county')
    action = request.POST.get('action') if request.method == 'POST' else None

    if action == 'toggle_centre':
        centre = get_object_or_404(centres, pk=request.POST.get('object_id'))
        centre.is_active = not centre.is_active
        centre.save(update_fields=['is_active', 'modified'])
        record_audit_event(
            actor=request.user,
            action='status',
            summary=f'Centre {centre.name} was {"activated" if centre.is_active else "deactivated"}.',
            centre=centre,
            details={'active': centre.is_active},
        )
        messages.success(request, 'The centre status was updated.')
        return redirect('ecde:manage_centres')

    if action == 'update_centre':
        centre = get_object_or_404(centres, pk=request.POST.get('object_id'))
        form = ECDECentreForm(
            request.POST, instance=centre, user=request.user,
            prefix=f'centre-{centre.pk}',
        )
        if form.is_valid():
            changed_fields = form.changed_data
            with transaction.atomic():
                centre = form.save()
                record_audit_event(
                    actor=request.user,
                    action='update',
                    summary=f'Operational details for {centre.name} were updated.',
                    centre=centre,
                    details={'changed_fields': changed_fields},
                )
            messages.success(request, f'{centre.name} was updated.')
            return redirect('ecde:manage_centres')
        submitted_centre_form = form
        messages.error(request, 'Please correct the errors in the centre form.')
    else:
        submitted_centre_form = None

    centre_editors = [
        {
            'centre': centre,
            'form': (
                submitted_centre_form
                if submitted_centre_form
                and submitted_centre_form.instance.pk == centre.pk
                else ECDECentreForm(
                    instance=centre, user=request.user,
                    prefix=f'centre-{centre.pk}',
                )
            ),
        }
        for centre in centres
    ]
    return render(request, 'ecde/manage_centres.html', {
        'centre_editors': centre_editors,
        'centre_count': len(centre_editors),
        'use_list_view': len(centre_editors) >= 5,
    })


@login_required
def add_centre(request):
    if not can_manage_ecde(request.user):
        raise PermissionDenied

    create_form = ECDECentreForm(
        request.POST if request.method == 'POST' else None,
        user=request.user,
    )
    if request.method == 'POST' and create_form.is_valid():
        try:
            with transaction.atomic():
                centre = create_form.save()
                record_audit_event(
                    actor=request.user,
                    action='create',
                    summary=f'ECDE centre {centre.name} was created.',
                    centre=centre,
                )
        except IntegrityError:
            create_form.add_error(
                None,
                'A centre with that name or code already exists in this area.',
            )
        else:
            messages.success(request, f'{centre} was created.')
            return redirect('ecde:manage_centres')

    return render(request, 'ecde/add_centre.html', {
        'create_form': create_form,
    })


@login_required
def manage_staff(request):
    if not can_manage_ecde(request.user):
        raise PermissionDenied

    action = request.POST.get('action') if request.method == 'POST' else None
    submitted_membership_form = None
    submitted_profile_form = None

    if action == 'toggle_membership':
        membership = get_object_or_404(
            manageable_memberships(request.user),
            pk=request.POST.get('object_id'),
        )
        membership.is_active = not membership.is_active
        membership.save(update_fields=['is_active', 'modified'])
        record_audit_event(
            actor=request.user,
            action='status',
            summary=f'ECDE access assignment {membership.pk} status changed.',
            county=membership.county,
            subcounty=membership.subcounty,
            ward=membership.ward,
            centre=membership.centre,
            details={'membership_id': membership.pk, 'active': membership.is_active},
        )
        messages.success(request, 'The staff access status was updated.')
        return redirect('ecde:manage_staff')

    if action == 'update_teacher_profile':
        membership = get_object_or_404(
            manageable_memberships(request.user),
            pk=request.POST.get('object_id'),
            role=ECDEMembership.ROLE_ECDE_TEACHER,
        )
        profile = getattr(membership, 'teacher_profile', None)
        if profile is None:
            profile = ECDETeacherProfile(membership=membership)
        profile_form = ECDETeacherProfileForm(
            request.POST,
            instance=profile,
            prefix=f'teacher-{membership.pk}',
        )
        if profile_form.is_valid():
            changed_fields = profile_form.changed_data
            with transaction.atomic():
                saved_profile = profile_form.save()
                record_audit_event(
                    actor=request.user,
                    action='update',
                    summary='An ECDE teacher personnel profile was updated.',
                    centre=membership.centre,
                    details={
                        'membership_id': membership.pk,
                        'profile_id': saved_profile.pk,
                        'changed_fields': changed_fields,
                    },
                )
            messages.success(request, 'The teacher profile was updated.')
            return redirect('ecde:manage_staff')
        submitted_profile_form = profile_form
        messages.error(request, 'Please correct the errors in the teacher profile.')

    membership_form = ECDEMembershipForm(
        request.POST if action == 'create_membership' else None,
        user=request.user,
    )
    if action == 'create_membership' and membership_form.is_valid():
        try:
            with transaction.atomic():
                membership = membership_form.save()
                membership_form.save_teacher_profile()
                record_audit_event(
                    actor=request.user,
                    action='create',
                    summary=f'ECDE role assignment {membership.pk} was created.',
                    county=membership.county,
                    subcounty=membership.subcounty,
                    ward=membership.ward,
                    centre=membership.centre,
                    details={
                        'membership_id': membership.pk,
                        'role': membership.role,
                        'active': membership.is_active,
                    },
                )
        except IntegrityError:
            membership_form.add_error(
                None,
                'This user already has an assignment with that role in the selected area.',
            )
        else:
            messages.success(request, f'{membership} was assigned.')
            return redirect('ecde:manage_staff')
    elif action == 'create_membership':
        submitted_membership_form = membership_form

    memberships = manageable_memberships(request.user).select_related(
        'user', 'county', 'subcounty', 'ward', 'centre',
    ).prefetch_related('teacher_profile')
    staff_profiles = []
    for membership in memberships.filter(role=ECDEMembership.ROLE_ECDE_TEACHER):
        profile = getattr(membership, 'teacher_profile', None)
        if profile is None:
            profile = ECDETeacherProfile(membership=membership)
        staff_profiles.append({
            'membership': membership,
            'form': (
                submitted_profile_form
                if submitted_profile_form
                and submitted_profile_form.instance.membership_id == membership.pk
                else ECDETeacherProfileForm(
                    instance=profile,
                    prefix=f'teacher-{membership.pk}',
                )
            ),
        })

    return render(request, 'ecde/manage_staff.html', {
        'membership_form': submitted_membership_form or membership_form,
        'memberships': memberships,
        'staff_profiles': staff_profiles,
    })


@login_required
def children(request, centre_id):
    centre = _centre_for_user(request.user, centre_id)
    can_edit = can_record_at_centre(request.user, centre)
    can_manage_lifecycle = request.user.is_superuser or centre.county in manageable_counties(
        request.user,
    )
    action = request.POST.get('action') if request.method == 'POST' else None
    if request.method == 'POST' and not action:
        action = 'enrol_child'
    destination_centres = accessible_centres(request.user)
    child_records = centre.children.all()
    search_query = request.GET.get('q', '').strip()
    selected_level = request.GET.get('level', '')
    selected_status = request.GET.get('status', '')
    if search_query:
        child_records = child_records.filter(
            Q(first_name__icontains=search_query)
            | Q(middle_names__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(learner_number__icontains=search_query)
            | Q(admission_number__icontains=search_query)
            | Q(guardian_name__icontains=search_query)
            | Q(guardian_phone__icontains=search_query)
        )
    if selected_level in dict(ECDEChild.LEVEL_CHOICES):
        child_records = child_records.filter(level=selected_level)
    if selected_status in dict(ECDEChild.STATUS_CHOICES):
        child_records = child_records.filter(status=selected_status)
    child_page = Paginator(
        child_records.order_by('last_name', 'first_name', 'pk'),
        50,
    ).get_page(request.GET.get('page'))
    form = ECDEChildForm(
        request.POST if action == 'enrol_child' else None,
        centre=centre,
    )
    transfer_form = ECDEChildTransferForm(
        request.POST if action == 'transfer_child' else None,
        from_centre=centre,
        destination_centres=destination_centres,
    )
    if request.method == 'POST':
        if action == 'enrol_child':
            if not can_edit:
                raise PermissionDenied
            if form.is_valid():
                try:
                    with transaction.atomic():
                        child = form.save(commit=False)
                        child.centre = centre
                        child.enrolled_by = request.user
                        child.full_clean()
                        child.save()
                        record_audit_event(
                            actor=request.user,
                            action='create',
                            summary='A child record was enrolled.',
                            centre=centre,
                            details={'child_id': child.pk, 'level': child.level},
                        )
                except IntegrityError:
                    form.add_error(
                        None,
                        'That learner or admission number is already in use at this centre.',
                    )
                else:
                    messages.success(request, f'{child} was enrolled.')
                    return redirect('ecde:children', centre_id=centre.pk)
        elif action == 'transfer_child':
            if not can_manage_lifecycle:
                raise PermissionDenied
            if transfer_form.is_valid():
                try:
                    with transaction.atomic():
                        transfer = transfer_form.save(recorded_by=request.user)
                        record_audit_event(
                            actor=request.user,
                            action='transfer',
                            summary='A child was transferred to another ECDE centre.',
                            centre=transfer.from_centre,
                            related_centre=transfer.to_centre,
                            details={
                                'child_id': transfer.child_id,
                                'from_centre_id': transfer.from_centre_id,
                                'to_centre_id': transfer.to_centre_id,
                                'from_level': transfer.from_level,
                                'to_level': transfer.to_level,
                                'transfer_id': transfer.pk,
                            },
                        )
                except ValidationError as exc:
                    transfer_form.add_error(None, ' '.join(exc.messages))
                except IntegrityError:
                    transfer_form.add_error(
                        None,
                        'The destination centre already has a conflicting learner or admission number.',
                    )
                else:
                    messages.success(request, 'The child transfer was recorded.')
                    return redirect('ecde:children', centre_id=centre.pk)
        elif action == 'update_lifecycle':
            if not can_manage_lifecycle:
                raise PermissionDenied
            child = get_object_or_404(
                centre.children, pk=request.POST.get('child_id'),
            )
            lifecycle_form = ECDEChildLifecycleForm(request.POST, instance=child)
            if lifecycle_form.is_valid():
                updated_child = lifecycle_form.save(commit=False)
                updated_child.is_active = (
                    updated_child.status == ECDEChild.STATUS_ENROLLED
                )
                try:
                    with transaction.atomic():
                        updated_child.full_clean()
                        updated_child.save()
                        record_audit_event(
                            actor=request.user,
                            action='status',
                            summary='A child enrolment status was updated.',
                            centre=centre,
                            details={
                                'child_id': child.pk,
                                'status': updated_child.status,
                            },
                        )
                except ValidationError as exc:
                    lifecycle_form.add_error(None, ' '.join(exc.messages))
                else:
                    messages.success(request, 'The child status was updated.')
                    return redirect('ecde:children', centre_id=centre.pk)
            form = ECDEChildForm(centre=centre)
            transfer_form = ECDEChildTransferForm(
                from_centre=centre,
                destination_centres=destination_centres,
            )
            return render(request, 'ecde/children.html', {
                'centre': centre,
                'form': form,
                'children': child_page,
                'can_edit': can_edit,
                'can_manage_lifecycle': can_manage_lifecycle,
                'transfer_form': transfer_form,
                'lifecycle_errors': lifecycle_form.errors,
                'lifecycle_child_id': child.pk,
                'search_query': search_query,
                'selected_level': selected_level,
                'selected_status': selected_status,
                'level_choices': ECDEChild.LEVEL_CHOICES,
                'status_choices': ECDEChild.STATUS_CHOICES,
            })
        else:
            raise PermissionDenied

    return render(request, 'ecde/children.html', {
        'centre': centre,
        'form': form,
        'children': child_page,
        'can_edit': can_edit,
        'can_manage_lifecycle': can_manage_lifecycle,
        'transfer_form': transfer_form,
        'search_query': search_query,
        'selected_level': selected_level,
        'selected_status': selected_status,
        'level_choices': ECDEChild.LEVEL_CHOICES,
        'status_choices': ECDEChild.STATUS_CHOICES,
    })


@login_required
def child_detail(request, centre_id, child_id):
    centre = _centre_for_user(request.user, centre_id)
    child = get_object_or_404(
        centre.children.select_related('enrolled_by'),
        pk=child_id,
    )
    can_edit = can_record_at_centre(request.user, centre)
    form = ECDEChildProfileForm(
        request.POST if request.method == 'POST' else None,
        instance=child,
        centre=centre,
    )

    if request.method == 'POST':
        if not can_edit:
            raise PermissionDenied
        if form.is_valid():
            changed_fields = form.changed_data
            try:
                with transaction.atomic():
                    child = form.save(commit=False)
                    child.full_clean()
                    child.save()
                    if changed_fields:
                        record_audit_event(
                            actor=request.user,
                            action='update',
                            summary='A learner profile was updated.',
                            centre=centre,
                            details={
                                'child_id': child.pk,
                                'changed_fields': changed_fields,
                            },
                        )
            except IntegrityError:
                form.add_error(
                    None,
                    'That learner or admission number is already used at this centre.',
                )
            except ValidationError as exc:
                form.add_error(None, ' '.join(exc.messages))
            else:
                messages.success(request, 'Learner details were updated.')
                return redirect(
                    'ecde:child_detail',
                    centre_id=centre.pk,
                    child_id=child.pk,
                )

    return render(request, 'ecde/child_detail.html', {
        'centre': centre,
        'child': child,
        'form': form,
        'can_edit': can_edit,
        'attendance_records': child.attendance_records.filter(
            centre__in=accessible_centres(request.user),
        ).select_related('recorded_by', 'centre')[:30],
        'progress_records': child.cbc_progress_records.filter(
            centre__in=accessible_centres(request.user),
        ).select_related('recorded_by', 'centre')[:30],
        'transfers': child.transfers.filter(
            Q(from_centre__in=accessible_centres(request.user))
            | Q(to_centre__in=accessible_centres(request.user)),
        ).select_related('from_centre', 'to_centre', 'recorded_by'),
    })


@login_required
def attendance(request, centre_id):
    centre = _centre_for_user(request.user, centre_id)
    can_edit = can_record_at_centre(request.user, centre)
    if request.method == 'POST' and not can_edit:
        raise PermissionDenied
    form = AttendanceRecordForm(
        request.POST or None, centre=centre,
        initial={'date': timezone.localdate()},
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                record = form.save(recorded_by=request.user)
                record_audit_event(
                    actor=request.user, action='attendance',
                    summary='Child attendance was recorded.',
                    centre=centre,
                    details={
                        'attendance_id': record.pk,
                        'child_id': record.child_id,
                        'date': record.date.isoformat(),
                        'status': record.status,
                    },
                )
        except ValidationError as exc:
            form.add_error(None, ' '.join(exc.messages))
        except IntegrityError:
            form.add_error(
                None,
                'Attendance for this child and date has already been recorded.',
            )
        else:
            messages.success(request, 'Attendance was recorded.')
            return redirect('ecde:attendance', centre_id=centre.pk)

    records = AttendanceRecord.objects.filter(
        centre=centre,
    ).select_related('child', 'recorded_by')[:100]
    return render(request, 'ecde/attendance.html', {
        'centre': centre,
        'form': form,
        'records': records,
        'can_edit': can_edit,
    })


@login_required
def progress(request, centre_id):
    centre = _centre_for_user(request.user, centre_id)
    can_edit = can_record_at_centre(request.user, centre)
    if request.method == 'POST' and not can_edit:
        raise PermissionDenied
    form = CBCProgressRecordForm(
        request.POST or None, centre=centre,
        initial={'evidence_date': timezone.localdate()},
    )
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            record = form.save(recorded_by=request.user)
            record_audit_event(
                actor=request.user, action='cbc_observation',
                summary='A CBC learning observation was recorded.',
                centre=centre,
                details={
                    'progress_record_id': record.pk,
                    'child_id': record.child_id,
                    'learning_area': record.learning_area,
                    'progress': record.progress,
                    'evidence_date': record.evidence_date.isoformat(),
                },
            )
        messages.success(request, f'Progress for {record.child} was saved.')
        return redirect('ecde:progress', centre_id=centre.pk)

    records = CBCProgressRecord.objects.filter(
        centre=centre,
    ).select_related('child', 'recorded_by')[:100]
    return render(request, 'ecde/progress.html', {
        'centre': centre,
        'form': form,
        'records': records,
        'can_edit': can_edit,
    })


@login_required
def audit_log(request):
    events = accessible_audit_events(request.user)
    if not request.user.is_superuser and not events.exists():
        if not ECDEMembership.objects.filter(
            user=request.user, is_active=True,
        ).exists():
            raise PermissionDenied
    return render(request, 'ecde/audit_log.html', {
        'events': events[:200],
    })
