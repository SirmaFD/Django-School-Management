from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from model_utils.models import TimeStampedModel


class County(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'counties'

    def __str__(self):
        return self.name


class SubCounty(TimeStampedModel):
    county = models.ForeignKey(
        County, on_delete=models.PROTECT, related_name='subcounties',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)

    class Meta:
        ordering = ['county__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['county', 'name'], name='ecde_subcounty_name_per_county',
            ),
            models.UniqueConstraint(
                fields=['county', 'code'], name='ecde_subcounty_code_per_county',
            ),
        ]

    def __str__(self):
        return f'{self.name}, {self.county}'


class Ward(TimeStampedModel):
    subcounty = models.ForeignKey(
        SubCounty, on_delete=models.PROTECT, related_name='wards',
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20)

    class Meta:
        ordering = ['subcounty__county__name', 'subcounty__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['subcounty', 'name'], name='ecde_ward_name_per_subcounty',
            ),
            models.UniqueConstraint(
                fields=['subcounty', 'code'], name='ecde_ward_code_per_subcounty',
            ),
        ]

    def __str__(self):
        return f'{self.name}, {self.subcounty}'


class ECDECentre(TimeStampedModel):
    REGISTRATION_STATUS_CHOICES = [
        ('registered', 'Registered'),
        ('pending', 'Registration pending'),
        ('not_registered', 'Not registered'),
        ('unknown', 'Not verified'),
    ]
    OWNERSHIP_CHOICES = [
        ('public', 'Public'),
        ('private', 'Private'),
        ('community', 'Community'),
        ('other', 'Other'),
        ('', 'Not recorded'),
    ]
    WATER_SOURCE_CHOICES = [
        ('piped', 'Piped water'),
        ('borehole', 'Borehole / well'),
        ('rainwater', 'Rainwater'),
        ('river', 'River / stream'),
        ('other', 'Other'),
        ('unknown', 'Not verified'),
    ]
    FACILITY_STATUS_CHOICES = [
        ('yes', 'Yes'),
        ('no', 'No'),
        ('unknown', 'Not verified'),
    ]
    FACILITY_CONDITION_CHOICES = [
        ('good', 'Good'),
        ('needs_repair', 'Needs repair'),
        ('unsafe', 'Unsafe'),
        ('unknown', 'Not assessed'),
    ]

    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name='centres')
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=30)
    registration_number = models.CharField(max_length=50, blank=True)
    registration_status = models.CharField(
        max_length=20, choices=REGISTRATION_STATUS_CHOICES, default='unknown',
    )
    ownership = models.CharField(
        max_length=20, choices=OWNERSHIP_CHOICES, blank=True,
    )
    established_date = models.DateField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    classroom_count = models.PositiveSmallIntegerField(null=True, blank=True)
    toilet_count = models.PositiveSmallIntegerField(null=True, blank=True)
    water_source = models.CharField(
        max_length=20, choices=WATER_SOURCE_CHOICES, blank=True, default='unknown',
    )
    electricity = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    kitchen = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    playground = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    disability_access = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    meals_program = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    learning_materials = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    staffing_adequate = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    first_aid_ready = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    safeguarding_procedures = models.CharField(
        max_length=10, choices=FACILITY_STATUS_CHOICES, blank=True, default='unknown',
    )
    facility_condition = models.CharField(
        max_length=20, choices=FACILITY_CONDITION_CHOICES,
        blank=True, default='unknown',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['ward', 'code'], name='ecde_centre_code_per_ward',
            ),
        ]
        verbose_name = 'ECDE centre'
        verbose_name_plural = 'ECDE centres'

    @property
    def county(self):
        return self.ward.subcounty.county

    @property
    def subcounty(self):
        return self.ward.subcounty

    def __str__(self):
        return self.name


class ECDEMembership(TimeStampedModel):
    ROLE_COUNTY_ADMIN = 'county_admin'
    ROLE_SUBCOUNTY_OFFICER = 'subcounty_officer'
    ROLE_WARD_COORDINATOR = 'ward_coordinator'
    ROLE_CENTRE_MANAGER = 'centre_manager'
    ROLE_ECDE_TEACHER = 'ecde_teacher'
    ROLE_CHOICES = [
        (ROLE_COUNTY_ADMIN, 'County ECDE administrator'),
        (ROLE_SUBCOUNTY_OFFICER, 'Sub-county officer'),
        (ROLE_WARD_COORDINATOR, 'Ward coordinator'),
        (ROLE_CENTRE_MANAGER, 'Centre manager / staff'),
        (ROLE_ECDE_TEACHER, 'ECDE teacher'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ecde_memberships',
    )
    role = models.CharField(max_length=24, choices=ROLE_CHOICES)
    county = models.ForeignKey(
        County, on_delete=models.CASCADE, null=True, blank=True,
        related_name='memberships',
    )
    subcounty = models.ForeignKey(
        SubCounty, on_delete=models.CASCADE, null=True, blank=True,
        related_name='memberships',
    )
    ward = models.ForeignKey(
        Ward, on_delete=models.CASCADE, null=True, blank=True,
        related_name='memberships',
    )
    centre = models.ForeignKey(
        ECDECentre, on_delete=models.CASCADE, null=True, blank=True,
        related_name='memberships',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['user__username', 'role']
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(role='county_admin', county__isnull=False,
                      subcounty__isnull=True, ward__isnull=True, centre__isnull=True)
                    | Q(role='subcounty_officer', county__isnull=True,
                        subcounty__isnull=False, ward__isnull=True, centre__isnull=True)
                    | Q(role='ward_coordinator', county__isnull=True,
                        subcounty__isnull=True, ward__isnull=False, centre__isnull=True)
                    | Q(role__in=['centre_manager', 'ecde_teacher'],
                        county__isnull=True, subcounty__isnull=True, ward__isnull=True,
                        centre__isnull=False)
                ),
                name='ecde_membership_role_scope_consistent',
            ),
            models.UniqueConstraint(
                fields=['user', 'role', 'county'],
                condition=Q(county__isnull=False),
                name='ecde_unique_user_county_role',
            ),
            models.UniqueConstraint(
                fields=['user', 'role', 'subcounty'],
                condition=Q(subcounty__isnull=False),
                name='ecde_unique_user_subcounty_role',
            ),
            models.UniqueConstraint(
                fields=['user', 'role', 'ward'],
                condition=Q(ward__isnull=False),
                name='ecde_unique_user_ward_role',
            ),
            models.UniqueConstraint(
                fields=['user', 'role', 'centre'],
                condition=Q(centre__isnull=False),
                name='ecde_unique_user_centre_role',
            ),
        ]

    def clean(self):
        super().clean()
        required_scope = {
            self.ROLE_COUNTY_ADMIN: 'county',
            self.ROLE_SUBCOUNTY_OFFICER: 'subcounty',
            self.ROLE_WARD_COORDINATOR: 'ward',
            self.ROLE_CENTRE_MANAGER: 'centre',
            self.ROLE_ECDE_TEACHER: 'centre',
        }.get(self.role)
        if required_scope is None:
            raise ValidationError({'role': 'Select a valid ECDE role.'})

        scope_fields = ('county', 'subcounty', 'ward', 'centre')
        if any(
            bool(getattr(self, field)) != (field == required_scope)
            for field in scope_fields
        ):
            raise ValidationError({
                required_scope: f'This role must be assigned at the {required_scope} level only.',
            })

    def __str__(self):
        return f'{self.user} — {self.get_role_display()}'


class ECDEChild(TimeStampedModel):
    LEVEL_CHOICES = [('PP1', 'PP1'), ('PP2', 'PP2')]
    GENDER_CHOICES = [('F', 'Female'), ('M', 'Male')]
    STATUS_ENROLLED = 'enrolled'
    STATUS_COMPLETED = 'completed'
    STATUS_WITHDRAWN = 'withdrawn'
    STATUS_CHOICES = [
        (STATUS_ENROLLED, 'Enrolled'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_WITHDRAWN, 'Withdrawn'),
    ]

    centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='children',
    )
    learner_number = models.CharField(
        max_length=40, blank=True,
        help_text='Optional county or national learner identifier.',
    )
    admission_number = models.CharField(max_length=30, blank=True)
    middle_names = models.CharField(max_length=120, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    level = models.CharField(max_length=3, choices=LEVEL_CHOICES)
    guardian_name = models.CharField(max_length=150)
    guardian_relationship = models.CharField(max_length=50, blank=True)
    guardian_phone = models.CharField(max_length=30)
    alternate_guardian_name = models.CharField(max_length=150, blank=True)
    alternate_guardian_phone = models.CharField(max_length=30, blank=True)
    guardian_email = models.EmailField(blank=True)
    home_village = models.CharField(max_length=120, blank=True)
    enrollment_date = models.DateField(default=timezone.localdate)
    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default=STATUS_ENROLLED,
    )
    exit_date = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    enrolled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_children_enrolled',
    )

    class Meta:
        ordering = ['first_name', 'last_name']
        constraints = [
            models.UniqueConstraint(
                fields=['centre', 'admission_number'],
                condition=~Q(admission_number=''),
                name='ecde_child_admission_number_per_centre',
            ),
            models.UniqueConstraint(
                fields=['centre', 'learner_number'],
                condition=~Q(learner_number=''),
                name='ecde_child_learner_number_per_centre',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.status == self.STATUS_ENROLLED and (self.exit_date or self.exit_reason):
            errors['exit_date'] = 'An enrolled child cannot have exit details.'
        elif self.status != self.STATUS_ENROLLED and not self.exit_date:
            errors['exit_date'] = 'An exit date is required for a completed or withdrawn child.'
        elif self.status == self.STATUS_WITHDRAWN and not self.exit_reason:
            errors['exit_reason'] = 'A reason is required when a child withdraws.'
        if (
            self.exit_date and self.enrollment_date
            and self.exit_date < self.enrollment_date
        ):
            errors['exit_date'] = 'The exit date cannot be before the enrolment date.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


class ECDEChildTransfer(TimeStampedModel):
    child = models.ForeignKey(
        ECDEChild, on_delete=models.PROTECT, related_name='transfers',
    )
    from_centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='outgoing_transfers',
    )
    to_centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='incoming_transfers',
    )
    from_level = models.CharField(max_length=3, choices=ECDEChild.LEVEL_CHOICES)
    to_level = models.CharField(max_length=3, choices=ECDEChild.LEVEL_CHOICES)
    transfer_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_child_transfers_recorded',
    )

    class Meta:
        ordering = ['-transfer_date', '-created']

    def clean(self):
        super().clean()
        errors = {}
        if self.from_centre_id and self.to_centre_id and self.from_centre_id == self.to_centre_id:
            errors['to_centre'] = 'Choose a different centre for the transfer.'
        if self.child_id and self.from_centre_id and self.child.centre_id != self.from_centre_id:
            errors['from_centre'] = 'The child is not currently enrolled at this centre.'
        if self.child_id and self.child.status != ECDEChild.STATUS_ENROLLED:
            errors['child'] = 'Only an enrolled child can be transferred.'
        if (
            self.child_id and self.transfer_date
            and self.transfer_date < self.child.enrollment_date
        ):
            errors['transfer_date'] = 'The transfer date cannot be before the enrolment date.'
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.child}: {self.from_centre} to {self.to_centre}'


class ECDETeacherProfile(TimeStampedModel):
    EMPLOYMENT_TYPE_CHOICES = [
        ('permanent', 'Permanent'),
        ('contract', 'Contract'),
        ('volunteer', 'Volunteer'),
        ('other', 'Other'),
    ]

    membership = models.OneToOneField(
        ECDEMembership, on_delete=models.CASCADE, related_name='teacher_profile',
        limit_choices_to={'role': ECDEMembership.ROLE_ECDE_TEACHER},
    )
    staff_number = models.CharField(max_length=40, blank=True)
    tsc_registration_number = models.CharField(max_length=40, blank=True)
    highest_qualification = models.CharField(max_length=120, blank=True)
    employment_type = models.CharField(
        max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, blank=True,
    )
    date_joined = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    def clean(self):
        super().clean()
        if self.membership_id and self.membership.role != ECDEMembership.ROLE_ECDE_TEACHER:
            raise ValidationError({
                'membership': 'Personnel profiles can only be linked to ECDE teachers.',
            })

    def __str__(self):
        return f'ECDE teacher profile: {self.membership.user}'


class CentreNeedsAssessment(TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
    ]

    centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='needs_assessments',
    )
    assessment_year = models.PositiveSmallIntegerField()
    assessed_on = models.DateField(default=timezone.localdate)
    summary = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_needs_assessments',
    )

    class Meta:
        ordering = ['-assessment_year', '-assessed_on']
        constraints = [
            models.UniqueConstraint(
                fields=['centre', 'assessment_year'],
                name='ecde_one_needs_assessment_per_centre_year',
            ),
        ]

    def __str__(self):
        return f'{self.centre} needs assessment {self.assessment_year}'


class CentreAssessedNeed(TimeStampedModel):
    PRIORITY_CHOICES = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    ]
    CATEGORY_CHOICES = [
        ('learning_materials', 'Learning materials'),
        ('infrastructure', 'Infrastructure / repairs'),
        ('furniture', 'Furniture'),
        ('meals', 'Meals / nutrition'),
        ('health_safety', 'Health and safety'),
        ('staffing', 'Staffing'),
        ('other', 'Other'),
    ]

    assessment = models.ForeignKey(
        CentreNeedsAssessment, on_delete=models.CASCADE, related_name='needs',
    )
    category = models.CharField(max_length=24, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    priority = models.CharField(max_length=8, choices=PRIORITY_CHOICES)

    class Meta:
        ordering = ['priority', 'category', 'description']

    def __str__(self):
        return self.description


class CentreAnnualPlan(TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('returned', 'Returned for revision'),
    ]

    centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='annual_plans',
    )
    year = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=180)
    objectives = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_annual_plans_created',
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ecde_annual_plans_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-year', 'title']
        constraints = [
            models.UniqueConstraint(
                fields=['centre', 'year'],
                name='ecde_one_annual_plan_per_centre_year',
            ),
        ]

    @property
    def budget_total(self):
        return sum(
            (line.total_cost for line in self.budget_lines.all()),
            start=0,
        )

    def __str__(self):
        return f'{self.centre} — {self.year} {self.title}'


class CentreBudgetLine(TimeStampedModel):
    CATEGORY_CHOICES = [
        ('learning_materials', 'Learning materials'),
        ('infrastructure', 'Infrastructure / repairs'),
        ('furniture', 'Furniture'),
        ('meals', 'Meals / nutrition'),
        ('health_safety', 'Health and safety'),
        ('staffing', 'Staffing'),
        ('other', 'Other'),
    ]

    plan = models.ForeignKey(
        CentreAnnualPlan, on_delete=models.CASCADE, related_name='budget_lines',
    )
    category = models.CharField(max_length=24, choices=CATEGORY_CHOICES)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2)
    funding_source = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['category', 'description']

    @property
    def total_cost(self):
        return self.quantity * self.unit_cost

    def __str__(self):
        return self.description


class CentreProcurementRequest(TimeStampedModel):
    STATUS_CHOICES = [
        ('pending', 'Pending approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('ordered', 'Ordered'),
        ('part_received', 'Partially received'),
        ('received', 'Received'),
    ]

    centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='procurement_requests',
    )
    plan = models.ForeignKey(
        CentreAnnualPlan, on_delete=models.PROTECT,
        null=True, blank=True, related_name='procurement_requests',
    )
    title = models.CharField(max_length=180)
    description = models.TextField()
    requested_amount = models.DecimalField(max_digits=12, decimal_places=2)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_procurement_requests',
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default='pending',
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ecde_procurement_approvals',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-requested_at']

    def clean(self):
        super().clean()
        if self.plan_id and self.centre_id and self.plan.centre_id != self.centre_id:
            raise ValidationError({'plan': 'Choose an annual plan for this centre.'})

    def __str__(self):
        return self.title


class CentreDeliveryReceipt(TimeStampedModel):
    CONDITION_CHOICES = [
        ('good', 'Good'),
        ('partial', 'Partial delivery'),
        ('damaged', 'Damaged / needs follow-up'),
    ]

    procurement_request = models.ForeignKey(
        CentreProcurementRequest, on_delete=models.PROTECT,
        related_name='delivery_receipts',
    )
    receipt_reference = models.CharField(max_length=80)
    supplier = models.CharField(max_length=180)
    received_on = models.DateField(default=timezone.localdate)
    items_received = models.CharField(max_length=255)
    quantity_received = models.PositiveIntegerField()
    condition = models.CharField(max_length=12, choices=CONDITION_CHOICES)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_delivery_receipts',
    )

    class Meta:
        ordering = ['-received_on', '-created']
        constraints = [
            models.UniqueConstraint(
                fields=['procurement_request', 'receipt_reference'],
                name='ecde_unique_procurement_receipt_reference',
            ),
        ]

    def __str__(self):
        return f'{self.receipt_reference}: {self.items_received}'


class CentreInventoryItem(TimeStampedModel):
    centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='inventory_items',
    )
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=40)
    opening_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    reorder_level = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['centre', 'name', 'unit'],
                name='ecde_unique_inventory_item_per_centre_unit',
            ),
        ]

    @property
    def quantity_on_hand(self):
        movements = self.movements.aggregate(
            stock_in=models.Sum(
                'quantity', filter=Q(movement_type='in'),
            ),
            stock_out=models.Sum(
                'quantity', filter=Q(movement_type='out'),
            ),
        )
        return self.opening_quantity + (movements['stock_in'] or 0) - (
            movements['stock_out'] or 0
        )

    def __str__(self):
        return f'{self.name} ({self.centre})'


class CentreInventoryMovement(TimeStampedModel):
    MOVEMENT_CHOICES = [
        ('in', 'Stock in'),
        ('out', 'Stock out'),
    ]
    USAGE_PURPOSE_CHOICES = [
        ('teaching', 'Teaching and learning'),
        ('meals', 'Meals / nutrition programme'),
        ('health_safety', 'Health and safety'),
        ('maintenance', 'Maintenance and repairs'),
        ('administration', 'Centre administration'),
        ('other', 'Other'),
    ]

    item = models.ForeignKey(
        CentreInventoryItem, on_delete=models.PROTECT, related_name='movements',
    )
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    moved_on = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    usage_purpose = models.CharField(
        max_length=24, choices=[('', 'Not applicable')] + USAGE_PURPOSE_CHOICES,
        blank=True,
    )
    notes = models.TextField(blank=True)
    distribution_receipt = models.OneToOneField(
        'CentreSupplyReceipt', on_delete=models.PROTECT,
        null=True, blank=True, related_name='inventory_movement',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_inventory_movements',
    )

    class Meta:
        ordering = ['-moved_on', '-created']

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.movement_type == 'out' and not self.usage_purpose:
            raise ValidationError({
                'usage_purpose': 'Choose how the supplies were used.',
            })
        if self.item_id and self.movement_type == 'out':
            available = self.item.quantity_on_hand
            if self.quantity and self.quantity > available:
                raise ValidationError({
                    'quantity': f'Only {available} {self.item.unit} are in stock.',
                })

    def __str__(self):
        return f'{self.get_movement_type_display()}: {self.item.name}'


class CountyInventoryItem(TimeStampedModel):
    county = models.ForeignKey(
        County, on_delete=models.PROTECT, related_name='supply_inventory_items',
    )
    name = models.CharField(max_length=160)
    unit = models.CharField(max_length=40)
    opening_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['county__name', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['county', 'name', 'unit'],
                name='ecde_unique_county_inventory_item',
            ),
        ]

    @property
    def quantity_on_hand(self):
        movements = self.movements.aggregate(
            stock_in=models.Sum('quantity', filter=Q(movement_type='in')),
            stock_out=models.Sum('quantity', filter=Q(movement_type='out')),
        )
        return self.opening_quantity + (movements['stock_in'] or 0) - (
            movements['stock_out'] or 0
        )

    def __str__(self):
        return f'{self.name} ({self.county})'


class CentreSupplyAllocation(TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('dispatched', 'Dispatched'),
        ('part_received', 'Partially received'),
        ('received', 'Received'),
        ('cancelled', 'Cancelled'),
    ]

    centre = models.ForeignKey(
        ECDECentre, on_delete=models.PROTECT, related_name='supply_allocations',
    )
    stock_item = models.ForeignKey(
        CountyInventoryItem, on_delete=models.PROTECT,
        related_name='allocations',
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_supply_allocations_created',
    )
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ecde_supply_allocations_dispatched',
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created']

    def clean(self):
        super().clean()
        errors = {}
        if self.quantity is not None and self.quantity <= 0:
            errors['quantity'] = 'Allocated quantity must be greater than zero.'
        if (
            self.stock_item_id and self.centre_id
            and self.stock_item.county_id != self.centre.county.pk
        ):
            errors['stock_item'] = 'Stock must come from the centre county.'
        if errors:
            raise ValidationError(errors)

    @property
    def quantity_received(self):
        return self.receipts.aggregate(total=models.Sum('quantity_received'))[
            'total'
        ] or 0

    def __str__(self):
        return f'{self.quantity} {self.stock_item.unit} {self.stock_item.name} → {self.centre}'


class CountyInventoryMovement(TimeStampedModel):
    MOVEMENT_CHOICES = [
        ('in', 'Stock in'),
        ('out', 'Stock out'),
    ]

    item = models.ForeignKey(
        CountyInventoryItem, on_delete=models.PROTECT,
        related_name='movements',
    )
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_CHOICES)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    moved_on = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    allocation = models.OneToOneField(
        CentreSupplyAllocation, on_delete=models.PROTECT,
        null=True, blank=True, related_name='stock_movement',
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_county_inventory_movements',
    )

    class Meta:
        ordering = ['-moved_on', '-created']

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.allocation_id and (
            self.allocation.stock_item_id != self.item_id
            or self.movement_type != 'out'
            or self.quantity != self.allocation.quantity
        ):
            raise ValidationError({
                'allocation': 'The dispatch movement must match its allocation.',
            })

    def __str__(self):
        return f'{self.get_movement_type_display()}: {self.item.name}'


class CentreSupplyReceipt(TimeStampedModel):
    CONDITION_CHOICES = [
        ('good', 'Good'),
        ('partial', 'Partial / short'),
        ('damaged', 'Damaged'),
    ]

    allocation = models.ForeignKey(
        CentreSupplyAllocation, on_delete=models.PROTECT, related_name='receipts',
    )
    receipt_reference = models.CharField(max_length=100)
    quantity_received = models.DecimalField(max_digits=12, decimal_places=2)
    received_on = models.DateField(default=timezone.localdate)
    condition = models.CharField(max_length=12, choices=CONDITION_CHOICES)
    notes = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_supply_receipts_confirmed',
    )

    class Meta:
        ordering = ['-received_on', '-created']
        constraints = [
            models.UniqueConstraint(
                fields=['allocation', 'receipt_reference'],
                name='ecde_unique_supply_receipt_reference',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.quantity_received is not None and self.quantity_received <= 0:
            errors['quantity_received'] = 'Received quantity must be greater than zero.'
        if self.allocation_id and self.quantity_received:
            received_before = self.allocation.quantity_received
            if self.pk:
                received_before -= self.quantity_received
            if received_before + self.quantity_received > self.allocation.quantity:
                errors['quantity_received'] = (
                    'Confirmed quantity cannot exceed the allocated quantity.'
                )
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f'{self.receipt_reference}: {self.allocation}'


class AttendanceRecord(TimeStampedModel):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ]

    centre = models.ForeignKey(
        ECDECentre, on_delete=models.CASCADE, related_name='attendance_records',
    )
    child = models.ForeignKey(
        ECDEChild, on_delete=models.CASCADE, related_name='attendance_records',
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    notes = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_attendance_records',
    )

    class Meta:
        ordering = ['-date', 'child__first_name', 'child__last_name']
        constraints = [
            models.UniqueConstraint(
                fields=['child', 'date'], name='ecde_one_attendance_per_child_day',
            ),
        ]

    def clean(self):
        super().clean()
        if self.child_id and self.centre_id and self.child.centre_id != self.centre_id:
            raise ValidationError({'child': 'The child must belong to this centre.'})

    def __str__(self):
        return f'{self.child} — {self.date} ({self.get_status_display()})'


class CBCProgressRecord(TimeStampedModel):
    AREA_CHOICES = [
        ('language', 'Language Activities'),
        ('mathematics', 'Mathematical Activities'),
        ('environment', 'Environmental Activities'),
        ('psychomotor_creative', 'Psychomotor and Creative Activities'),
        ('religious_education', 'Religious Education Activities'),
    ]
    PROGRESS_CHOICES = [
        ('not_yet_observed', 'Not yet observed'),
        ('emerging', 'Emerging'),
        ('developing', 'Developing'),
        ('demonstrating', 'Demonstrating'),
    ]

    centre = models.ForeignKey(
        ECDECentre, on_delete=models.CASCADE, related_name='progress_records',
    )
    child = models.ForeignKey(
        ECDEChild, on_delete=models.CASCADE, related_name='cbc_progress_records',
    )
    learning_area = models.CharField(max_length=32, choices=AREA_CHOICES)
    competency = models.CharField(max_length=200)
    progress = models.CharField(max_length=24, choices=PROGRESS_CHOICES)
    observation = models.TextField()
    evidence_date = models.DateField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='ecde_progress_records',
    )

    class Meta:
        ordering = ['-evidence_date', 'child__first_name', 'learning_area']

    def clean(self):
        super().clean()
        if self.child_id and self.centre_id and self.child.centre_id != self.centre_id:
            raise ValidationError({'child': 'The child must belong to this centre.'})

    def __str__(self):
        return f'{self.child} — {self.get_learning_area_display()}'


class ECDEAuditEvent(models.Model):
    ACTION_CHOICES = [
        ('create', 'Created'),
        ('update', 'Updated'),
        ('transfer', 'Transferred'),
        ('status', 'Status changed'),
        ('attendance', 'Attendance recorded'),
        ('cbc_observation', 'CBC observation recorded'),
    ]

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='ecde_audit_events',
    )
    action = models.CharField(max_length=24, choices=ACTION_CHOICES)
    summary = models.CharField(max_length=255)
    details = models.JSONField(default=dict, blank=True)
    county = models.ForeignKey(
        County, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_events',
    )
    subcounty = models.ForeignKey(
        SubCounty, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_events',
    )
    ward = models.ForeignKey(
        Ward, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_events',
    )
    centre = models.ForeignKey(
        ECDECentre, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_events',
    )
    related_centre = models.ForeignKey(
        ECDECentre, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='related_audit_events',
    )

    class Meta:
        ordering = ['-occurred_at', '-pk']
        verbose_name = 'ECDE audit event'
        verbose_name_plural = 'ECDE audit events'

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('ECDE audit events cannot be modified.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('ECDE audit events cannot be deleted.')

    def __str__(self):
        return f'{self.get_action_display()}: {self.summary}'
