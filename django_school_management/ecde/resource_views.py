from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .access import accessible_centres
from .audit import record_audit_event
from .management import can_manage_ecde
from .management_forms import manageable_counties
from .models import (
    CentreAnnualPlan, CentreAssessedNeed, CentreBudgetLine,
    CentreDeliveryReceipt, CentreInventoryItem, CentreInventoryMovement,
    CentreNeedsAssessment, CentreProcurementRequest, CentreSupplyAllocation,
    CentreSupplyReceipt, CountyInventoryItem, CountyInventoryMovement,
    ECDEMembership,
)
from .resource_forms import (
    CentreAnnualPlanForm, CentreAssessedNeedForm, CentreBudgetLineForm,
    CentreDeliveryReceiptForm, CentreInventoryItemForm,
    CentreInventoryMovementForm, CentreNeedsAssessmentForm,
    CentreProcurementRequestForm, CentreSupplyReceiptForm,
    CountyInventoryItemForm, CountyStockInForm, ProcurementDecisionForm,
    SupplyAllocationForm,
)


def _centre_manager_or_superuser(user, centre):
    return user.is_superuser or ECDEMembership.objects.filter(
        user=user,
        centre=centre,
        role=ECDEMembership.ROLE_CENTRE_MANAGER,
        is_active=True,
    ).exists()


def _can_approve_procurement(user, centre):
    return user.is_superuser or centre.county in manageable_counties(user)


def _resource_context(request, centre, bound_forms=None):
    bound_forms = bound_forms or {}
    plans = CentreAnnualPlan.objects.filter(centre=centre).prefetch_related(
        'budget_lines',
    )
    assessments = CentreNeedsAssessment.objects.filter(
        centre=centre,
    ).prefetch_related('needs')
    requests = CentreProcurementRequest.objects.filter(
        centre=centre,
    ).select_related('plan', 'requested_by', 'approved_by').prefetch_related(
        'delivery_receipts',
    )
    items = CentreInventoryItem.objects.filter(
        centre=centre,
    ).prefetch_related('movements')
    allocations = CentreSupplyAllocation.objects.filter(
        centre=centre,
    ).select_related(
        'stock_item', 'allocated_by', 'dispatched_by',
    ).prefetch_related('receipts__confirmed_by')
    return {
        'centre': centre,
        'assessments': assessments,
        'plans': plans,
        'procurement_requests': requests,
        'inventory_items': items,
        'supply_allocations': allocations,
        'can_manage_resources': _centre_manager_or_superuser(
            request.user, centre,
        ),
        'can_confirm_distributions': _centre_manager_or_superuser(
            request.user, centre,
        ),
        'can_approve_procurement': _can_approve_procurement(
            request.user, centre,
        ),
        'assessment_form': bound_forms.get(
            'assessment',
            CentreNeedsAssessmentForm(),
        ),
        'need_form': bound_forms.get('need', CentreAssessedNeedForm()),
        'plan_form': bound_forms.get('plan', CentreAnnualPlanForm()),
        'budget_form': bound_forms.get(
            'budget',
            CentreBudgetLineForm(
                plan_queryset=CentreAnnualPlan.objects.filter(centre=centre),
            ),
        ),
        'procurement_form': bound_forms.get(
            'procurement',
            CentreProcurementRequestForm(
                plan_queryset=CentreAnnualPlan.objects.filter(centre=centre),
            ),
        ),
        'receipt_form': bound_forms.get('receipt', CentreDeliveryReceiptForm()),
        'inventory_item_form': bound_forms.get(
            'inventory_item', CentreInventoryItemForm(),
        ),
        'inventory_movement_form': bound_forms.get(
            'inventory_movement', CentreInventoryMovementForm(),
        ),
        'decision_form': bound_forms.get('decision', ProcurementDecisionForm()),
        'distribution_receipt_form': bound_forms.get(
            'distribution_receipt', CentreSupplyReceiptForm(),
        ),
        'bound_distribution_allocation_id': bound_forms.get(
            'distribution_allocation_id',
        ),
    }


def _redirect_resources(centre, anchor=None):
    url = reverse('ecde:resources', args=[centre.pk])
    if anchor:
        url += f'#{anchor}'
    return redirect(url)


@login_required
def county_supply_stock(request):
    counties = manageable_counties(request.user)
    if not can_manage_ecde(request.user):
        raise PermissionDenied

    items = CountyInventoryItem.objects.filter(
        county__in=counties,
    ).select_related('county').prefetch_related('movements')
    centres = accessible_centres(request.user).filter(
        ward__subcounty__county__in=counties,
    ).select_related('ward__subcounty__county')
    allocations = CentreSupplyAllocation.objects.filter(
        centre__ward__subcounty__county__in=counties,
    ).select_related('centre', 'stock_item', 'allocated_by').prefetch_related(
        'receipts',
    )
    bound_forms = {}

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_stock_item':
            form = CountyInventoryItemForm(request.POST, user=request.user)
            bound_forms['stock_item'] = form
            if form.is_valid():
                item = form.save()
                record_audit_event(
                    actor=request.user,
                    action='create',
                    summary=f'County stock item {item.name} was created.',
                    county=item.county,
                    details={
                        'item_id': item.pk,
                        'unit': item.unit,
                        'opening_quantity': str(item.opening_quantity),
                    },
                )
                messages.success(request, 'County stock item created.')
                return redirect('ecde:county_supply_stock')

        elif action == 'stock_in':
            form = CountyStockInForm(
                request.POST,
                item_queryset=items,
            )
            bound_forms['stock_in'] = form
            if form.is_valid():
                item = form.cleaned_data['item']
                movement = CountyInventoryMovement(
                    item=item,
                    movement_type='in',
                    quantity=form.cleaned_data['quantity'],
                    moved_on=form.cleaned_data['moved_on'],
                    reference=form.cleaned_data['reference'],
                    notes=form.cleaned_data['notes'],
                    recorded_by=request.user,
                )
                movement.save()
                record_audit_event(
                    actor=request.user,
                    action='update',
                    summary=f'County stock replenished: {item.name}.',
                    county=item.county,
                    details={
                        'item_id': item.pk,
                        'movement_id': movement.pk,
                        'quantity': str(movement.quantity),
                        'reference': movement.reference,
                    },
                )
                messages.success(request, 'County stock replenished.')
                return redirect('ecde:county_supply_stock')

        elif action == 'create_allocation':
            form = SupplyAllocationForm(request.POST, user=request.user)
            bound_forms['allocation'] = form
            if form.is_valid():
                allocation = form.save(commit=False)
                allocation.allocated_by = request.user
                try:
                    allocation.full_clean()
                    allocation.save()
                    record_audit_event(
                        actor=request.user,
                        action='create',
                        summary=(
                            f'{allocation.quantity} {allocation.stock_item.unit} '
                            f'{allocation.stock_item.name} allocated to '
                            f'{allocation.centre.name}.'
                        ),
                        centre=allocation.centre,
                        details={
                            'allocation_id': allocation.pk,
                            'stock_item_id': allocation.stock_item_id,
                            'quantity': str(allocation.quantity),
                            'status': allocation.status,
                        },
                    )
                except ValidationError as exc:
                    form.add_error(None, ' '.join(exc.messages))
                except IntegrityError:
                    form.add_error(None, 'The supply allocation could not be saved.')
                else:
                    messages.success(request, 'Supply allocation created as a draft.')
                    return redirect('ecde:county_supply_stock')

        elif action == 'dispatch_allocation':
            allocation = get_object_or_404(
                allocations,
                pk=request.POST.get('allocation_id'),
                status='draft',
            )
            try:
                with transaction.atomic():
                    allocation = CentreSupplyAllocation.objects.select_for_update().get(
                        pk=allocation.pk,
                        status='draft',
                    )
                    item = CountyInventoryItem.objects.select_for_update().get(
                        pk=allocation.stock_item_id,
                    )
                    if allocation.quantity > item.quantity_on_hand:
                        raise ValidationError(
                            f'Insufficient county stock. Only '
                            f'{item.quantity_on_hand} {item.unit} are available.'
                        )
                    movement = CountyInventoryMovement(
                        item=item,
                        movement_type='out',
                        quantity=allocation.quantity,
                        moved_on=timezone.localdate(),
                        reference=allocation.reference or f'ALLOC-{allocation.pk}',
                        notes=f'Dispatched to {allocation.centre.name}.',
                        allocation=allocation,
                        recorded_by=request.user,
                    )
                    movement.full_clean()
                    movement.save()
                    allocation.status = 'dispatched'
                    allocation.dispatched_by = request.user
                    allocation.dispatched_at = timezone.now()
                    allocation.save(update_fields=[
                        'status', 'dispatched_by', 'dispatched_at', 'modified',
                    ])
                    record_audit_event(
                        actor=request.user,
                        action='status',
                        summary=(
                            f'{allocation.quantity} {item.unit} {item.name} '
                            f'dispatched to {allocation.centre.name}.'
                        ),
                        centre=allocation.centre,
                        details={
                            'allocation_id': allocation.pk,
                            'stock_item_id': item.pk,
                            'quantity': str(allocation.quantity),
                            'county_stock_movement_id': movement.pk,
                        },
                    )
            except ValidationError as exc:
                messages.error(request, ' '.join(exc.messages))
            else:
                messages.success(request, 'Supplies dispatched; county stock reduced.')
                return redirect('ecde:county_supply_stock')

        elif action == 'cancel_allocation':
            allocation = get_object_or_404(
                allocations,
                pk=request.POST.get('allocation_id'),
                status='draft',
            )
            allocation.status = 'cancelled'
            allocation.save(update_fields=['status', 'modified'])
            record_audit_event(
                actor=request.user,
                action='status',
                summary=f'Supply allocation {allocation.pk} was cancelled.',
                centre=allocation.centre,
                details={'allocation_id': allocation.pk, 'status': 'cancelled'},
            )
            messages.success(request, 'Draft allocation cancelled.')
            return redirect('ecde:county_supply_stock')
        else:
            raise PermissionDenied

    item_form = bound_forms.get(
        'stock_item',
        CountyInventoryItemForm(user=request.user),
    )
    stock_in_form = bound_forms.get(
        'stock_in',
        CountyStockInForm(item_queryset=items),
    )
    allocation_form = bound_forms.get(
        'allocation',
        SupplyAllocationForm(user=request.user),
    )
    return render(request, 'ecde/county_supply_stock.html', {
        'counties': counties,
        'items': items,
        'centres': centres,
        'allocations': allocations,
        'stock_item_form': item_form,
        'stock_in_form': stock_in_form,
        'allocation_form': allocation_form,
    })


@login_required
def centre_resources(request, centre_id):
    centre = get_object_or_404(accessible_centres(request.user), pk=centre_id)
    can_manage = _centre_manager_or_superuser(request.user, centre)
    can_approve = _can_approve_procurement(request.user, centre)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action in {
            'create_assessment', 'add_need', 'submit_assessment',
            'create_plan', 'add_budget_line', 'submit_plan',
            'create_procurement', 'record_receipt',
            'create_inventory_item',
            'record_inventory_movement',
        } and not can_manage:
            raise PermissionDenied
        if action in {
            'decide_procurement', 'review_plan', 'mark_ordered',
        } and not can_approve:
            raise PermissionDenied
        if action == 'confirm_distribution' and not _centre_manager_or_superuser(
            request.user, centre,
        ):
            raise PermissionDenied

        bound_forms = {}
        if action == 'create_assessment':
            form = CentreNeedsAssessmentForm(request.POST)
            bound_forms['assessment'] = form
            if form.is_valid():
                assessment = form.save(commit=False)
                assessment.centre = centre
                assessment.created_by = request.user
                try:
                    with transaction.atomic():
                        assessment.save()
                        record_audit_event(
                            actor=request.user,
                            action='create',
                            summary='A centre needs assessment was created.',
                            centre=centre,
                            details={'assessment_id': assessment.pk},
                        )
                except IntegrityError:
                    form.add_error(
                        'assessment_year',
                        'An assessment already exists for this centre and year.',
                    )
                else:
                    messages.success(request, 'Needs assessment created.')
                    return _redirect_resources(centre, 'needs-assessments')

        elif action == 'add_need':
            assessment = get_object_or_404(
                CentreNeedsAssessment.objects.filter(centre=centre),
                pk=request.POST.get('assessment_id'),
                status='draft',
            )
            form = CentreAssessedNeedForm(request.POST)
            bound_forms['need'] = form
            if form.is_valid():
                need = form.save(commit=False)
                need.assessment = assessment
                need.save()
                record_audit_event(
                    actor=request.user,
                    action='create',
                    summary='A need was added to a centre assessment.',
                    centre=centre,
                    details={
                        'assessment_id': assessment.pk,
                        'need_id': need.pk,
                        'category': need.category,
                    },
                )
                messages.success(request, 'Assessed need added.')
                return _redirect_resources(centre, 'needs-assessments')

        elif action == 'submit_assessment':
            assessment = get_object_or_404(
                CentreNeedsAssessment.objects.filter(centre=centre),
                pk=request.POST.get('assessment_id'),
                status='draft',
            )
            assessment.status = 'submitted'
            assessment.save(update_fields=['status', 'modified'])
            record_audit_event(
                actor=request.user,
                action='status',
                summary='A centre needs assessment was submitted.',
                centre=centre,
                details={'assessment_id': assessment.pk, 'status': assessment.status},
            )
            messages.success(request, 'Needs assessment submitted.')
            return _redirect_resources(centre, 'needs-assessments')

        elif action == 'create_plan':
            form = CentreAnnualPlanForm(request.POST)
            bound_forms['plan'] = form
            if form.is_valid():
                plan = form.save(commit=False)
                plan.centre = centre
                plan.created_by = request.user
                try:
                    with transaction.atomic():
                        plan.save()
                        record_audit_event(
                            actor=request.user,
                            action='create',
                            summary=f'Annual plan {plan.year} was created.',
                            centre=centre,
                            details={'plan_id': plan.pk, 'year': plan.year},
                        )
                except IntegrityError:
                    form.add_error('year', 'An annual plan already exists for this year.')
                else:
                    messages.success(request, 'Annual plan created.')
                    return _redirect_resources(centre, 'annual-plans')

        elif action == 'add_budget_line':
            form = CentreBudgetLineForm(
                request.POST,
                plan_queryset=CentreAnnualPlan.objects.filter(
                    centre=centre, status='draft',
                ),
            )
            bound_forms['budget'] = form
            if form.is_valid():
                line = form.save()
                record_audit_event(
                    actor=request.user,
                    action='create',
                    summary='A budget line was added to an annual plan.',
                    centre=centre,
                    details={
                        'budget_line_id': line.pk,
                        'plan_id': line.plan_id,
                        'amount': str(line.total_cost),
                    },
                )
                messages.success(request, 'Budget line added.')
                return _redirect_resources(centre, 'annual-plans')

        elif action == 'submit_plan':
            plan = get_object_or_404(
                CentreAnnualPlan.objects.filter(centre=centre),
                pk=request.POST.get('plan_id'),
                status='draft',
            )
            plan.status = 'submitted'
            plan.save(update_fields=['status', 'modified'])
            record_audit_event(
                actor=request.user,
                action='status',
                summary=f'Annual plan {plan.year} was submitted for review.',
                centre=centre,
                details={'plan_id': plan.pk, 'status': plan.status},
            )
            messages.success(request, 'Annual plan submitted for review.')
            return _redirect_resources(centre, 'annual-plans')

        elif action == 'review_plan':
            plan = get_object_or_404(
                CentreAnnualPlan.objects.filter(centre=centre),
                pk=request.POST.get('plan_id'),
                status='submitted',
            )
            form = ProcurementDecisionForm(request.POST)
            bound_forms['decision'] = form
            if form.is_valid():
                decision = form.cleaned_data['decision']
                plan.status = 'approved' if decision == 'approved' else 'returned'
                plan.reviewed_by = request.user
                plan.reviewed_at = timezone.now()
                plan.review_notes = form.cleaned_data['notes']
                plan.save(update_fields=[
                    'status', 'reviewed_by', 'reviewed_at', 'review_notes',
                    'modified',
                ])
                record_audit_event(
                    actor=request.user,
                    action='status',
                    summary=f'Annual plan {plan.year} was {plan.status}.',
                    centre=centre,
                    details={'plan_id': plan.pk, 'review_notes': plan.review_notes},
                )
                messages.success(request, f'Annual plan marked {plan.status}.')
                return _redirect_resources(centre, 'annual-plans')

        elif action == 'create_procurement':
            form = CentreProcurementRequestForm(
                request.POST,
                plan_queryset=CentreAnnualPlan.objects.filter(
                    centre=centre, status='approved',
                ),
            )
            bound_forms['procurement'] = form
            if form.is_valid():
                procurement = form.save(commit=False)
                procurement.centre = centre
                procurement.requested_by = request.user
                try:
                    procurement.full_clean()
                    procurement.save()
                    record_audit_event(
                        actor=request.user,
                        action='create',
                        summary=f'Procurement request {procurement.title} submitted.',
                        centre=centre,
                        details={
                            'procurement_id': procurement.pk,
                            'requested_amount': str(procurement.requested_amount),
                        },
                    )
                except ValidationError as exc:
                    form.add_error(None, ' '.join(exc.messages))
                except IntegrityError:
                    form.add_error(None, 'The procurement request could not be saved.')
                else:
                    messages.success(request, 'Procurement request submitted for approval.')
                    return _redirect_resources(centre, 'procurement')

        elif action == 'decide_procurement':
            procurement = get_object_or_404(
                CentreProcurementRequest.objects.filter(centre=centre),
                pk=request.POST.get('procurement_id'),
                status='pending',
            )
            form = ProcurementDecisionForm(request.POST)
            bound_forms['decision'] = form
            if form.is_valid():
                decision = form.cleaned_data['decision']
                notes = form.cleaned_data['notes']
                if decision == 'rejected' and not notes.strip():
                    form.add_error('notes', 'A reason is required when rejecting a request.')
                else:
                    procurement.status = decision
                    procurement.approved_by = request.user
                    procurement.approved_at = timezone.now()
                    procurement.approval_notes = notes
                    procurement.save(update_fields=[
                        'status', 'approved_by', 'approved_at',
                        'approval_notes', 'modified',
                    ])
                    record_audit_event(
                        actor=request.user,
                        action='status',
                        summary=f'Procurement request {procurement.title} was {decision}.',
                        centre=centre,
                        details={
                            'procurement_id': procurement.pk,
                            'status': decision,
                            'notes': notes,
                        },
                    )
                    messages.success(request, f'Procurement request {decision}.')
                    return _redirect_resources(centre, 'procurement')

        elif action == 'record_receipt':
            procurement = get_object_or_404(
                CentreProcurementRequest.objects.filter(centre=centre),
                pk=request.POST.get('procurement_id'),
                status__in=['approved', 'ordered', 'part_received'],
            )
            form = CentreDeliveryReceiptForm(request.POST)
            bound_forms['receipt'] = form
            if form.is_valid():
                receipt = form.save(commit=False)
                receipt.procurement_request = procurement
                receipt.recorded_by = request.user
                try:
                    with transaction.atomic():
                        receipt.save()
                        procurement.status = (
                            'received' if request.POST.get('delivery_complete')
                            else 'part_received'
                        )
                        procurement.save(update_fields=['status', 'modified'])
                        record_audit_event(
                            actor=request.user,
                            action='create',
                            summary=f'Delivery receipt recorded for {procurement.title}.',
                            centre=centre,
                            details={
                                'receipt_id': receipt.pk,
                                'procurement_id': procurement.pk,
                                'receipt_reference': receipt.receipt_reference,
                                'delivery_complete': procurement.status == 'received',
                            },
                        )
                except IntegrityError:
                    form.add_error(
                        'receipt_reference',
                        'This receipt reference is already recorded for the request.',
                    )
                else:
                    messages.success(
                        request,
                        'Delivery receipt recorded. Update inventory separately if needed.',
                    )
                    return _redirect_resources(centre, 'procurement')

        elif action == 'mark_ordered':
            procurement = get_object_or_404(
                CentreProcurementRequest.objects.filter(centre=centre),
                pk=request.POST.get('procurement_id'),
                status='approved',
            )
            procurement.status = 'ordered'
            procurement.save(update_fields=['status', 'modified'])
            record_audit_event(
                actor=request.user,
                action='status',
                summary=f'Procurement request {procurement.title} was ordered.',
                centre=centre,
                details={'procurement_id': procurement.pk, 'status': 'ordered'},
            )
            messages.success(request, 'Procurement marked as ordered.')
            return _redirect_resources(centre, 'procurement')

        elif action == 'create_inventory_item':
            form = CentreInventoryItemForm(request.POST)
            bound_forms['inventory_item'] = form
            if form.is_valid():
                item = form.save(commit=False)
                item.centre = centre
                try:
                    item.save()
                    record_audit_event(
                        actor=request.user,
                        action='create',
                        summary=f'Inventory item {item.name} was created.',
                        centre=centre,
                        details={'inventory_item_id': item.pk, 'unit': item.unit},
                    )
                except IntegrityError:
                    form.add_error(
                        'name',
                        'An inventory item with this name and unit already exists.',
                    )
                else:
                    messages.success(request, 'Inventory item created.')
                    return _redirect_resources(centre, 'inventory')

        elif action == 'record_inventory_movement':
            item = get_object_or_404(
                CentreInventoryItem.objects.filter(centre=centre),
                pk=request.POST.get('item_id'),
            )
            form = CentreInventoryMovementForm(request.POST)
            bound_forms['inventory_movement'] = form
            if form.is_valid():
                movement = form.save(commit=False)
                movement.item = item
                movement.recorded_by = request.user
                try:
                    with transaction.atomic():
                        locked_item = CentreInventoryItem.objects.select_for_update().get(
                            pk=item.pk,
                        )
                        if (
                            movement.movement_type == 'out'
                            and movement.quantity > locked_item.quantity_on_hand
                        ):
                            form.add_error(
                                'quantity',
                                f'Only {locked_item.quantity_on_hand} '
                                f'{locked_item.unit} are in stock.',
                            )
                        else:
                            movement.save()
                            record_audit_event(
                                actor=request.user,
                                action='update',
                                summary=f'Inventory stock {movement.get_movement_type_display().lower()} for {item.name}.',
                                centre=centre,
                                details={
                                    'movement_id': movement.pk,
                                    'inventory_item_id': item.pk,
                                    'quantity': str(movement.quantity),
                                    'usage_purpose': movement.usage_purpose,
                                },
                            )
                except IntegrityError:
                    form.add_error(None, 'The inventory movement could not be saved.')
                else:
                    if not form.errors:
                        messages.success(request, 'Inventory movement recorded.')
                        return _redirect_resources(centre, 'inventory')

        elif action == 'confirm_distribution':
            allocation = get_object_or_404(
                CentreSupplyAllocation.objects.filter(centre=centre),
                pk=request.POST.get('allocation_id'),
                status__in=['dispatched', 'part_received'],
            )
            form = CentreSupplyReceiptForm(request.POST)
            bound_forms['distribution_receipt'] = form
            bound_forms['distribution_allocation_id'] = allocation.pk
            if form.is_valid():
                try:
                    with transaction.atomic():
                        allocation = CentreSupplyAllocation.objects.select_for_update().get(
                            pk=allocation.pk,
                            centre=centre,
                            status__in=['dispatched', 'part_received'],
                        )
                        receipt = form.save(commit=False)
                        receipt.allocation = allocation
                        receipt.confirmed_by = request.user
                        receipt.full_clean()
                        receipt.save()
                        inventory_item, _ = CentreInventoryItem.objects.get_or_create(
                            centre=centre,
                            name=allocation.stock_item.name,
                            unit=allocation.stock_item.unit,
                            defaults={
                                'opening_quantity': 0,
                                'notes': 'Created from a county supply distribution receipt.',
                            },
                        )
                        movement = CentreInventoryMovement(
                            item=inventory_item,
                            movement_type='in',
                            quantity=receipt.quantity_received,
                            moved_on=receipt.received_on,
                            reference=receipt.receipt_reference,
                            notes=receipt.notes,
                            recorded_by=request.user,
                            distribution_receipt=receipt,
                        )
                        movement.full_clean()
                        movement.save()
                        allocation.status = (
                            'received'
                            if allocation.quantity_received >= allocation.quantity
                            else 'part_received'
                        )
                        allocation.save(update_fields=['status', 'modified'])
                        record_audit_event(
                            actor=request.user,
                            action='create',
                            summary=(
                                f'Distribution receipt confirmed for '
                                f'{allocation.stock_item.name}.'
                            ),
                            centre=centre,
                            details={
                                'allocation_id': allocation.pk,
                                'receipt_id': receipt.pk,
                                'quantity_received': str(receipt.quantity_received),
                                'allocation_status': allocation.status,
                            },
                        )
                except ValidationError as exc:
                    form.add_error(None, ' '.join(exc.messages))
                except IntegrityError:
                    form.add_error(
                        'receipt_reference',
                        'This receipt reference is already recorded.',
                    )
                else:
                    messages.success(
                        request,
                        'Distribution receipt confirmed and centre inventory updated.',
                    )
                    return _redirect_resources(centre, 'distributions')

        elif action:
            raise PermissionDenied

        return render(
            request,
            'ecde/resources.html',
            _resource_context(request, centre, bound_forms),
        )

    return render(request, 'ecde/resources.html', _resource_context(request, centre))
