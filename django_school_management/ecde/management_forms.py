from django import forms

from django_school_management.accounts.models import User

from .models import (
    County, ECDECentre, ECDEMembership, ECDETeacherProfile, SubCounty, Ward,
)


def _style_fields(form):
    for field in form.fields.values():
        css_class = 'form-check-input' if isinstance(
            field.widget, forms.CheckboxInput,
        ) else 'form-control'
        current_class = field.widget.attrs.get('class', '')
        field.widget.attrs['class'] = f'{current_class} {css_class}'.strip()


def manageable_counties(user):
    if user.is_superuser:
        return County.objects.all()
    return County.objects.filter(
        memberships__user=user,
        memberships__role=ECDEMembership.ROLE_COUNTY_ADMIN,
        memberships__is_active=True,
    ).distinct()


class CountyForm(forms.ModelForm):
    class Meta:
        model = County
        fields = ['name', 'code']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class SubCountyForm(forms.ModelForm):
    class Meta:
        model = SubCounty
        fields = ['county', 'name', 'code']

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['county'].queryset = manageable_counties(user)
        _style_fields(self)


class WardForm(forms.ModelForm):
    class Meta:
        model = Ward
        fields = ['subcounty', 'name', 'code']

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['subcounty'].queryset = SubCounty.objects.filter(
            county__in=manageable_counties(user),
        ).select_related('county')
        _style_fields(self)


class ECDECentreForm(forms.ModelForm):
    class Meta:
        model = ECDECentre
        fields = [
            'ward', 'name', 'code', 'registration_number',
            'registration_status', 'ownership', 'established_date',
            'capacity', 'contact_phone', 'contact_email', 'address',
            'classroom_count', 'toilet_count', 'water_source', 'electricity',
            'kitchen', 'playground', 'disability_access', 'facility_condition',
            'meals_program', 'learning_materials', 'staffing_adequate',
            'first_aid_ready', 'safeguarding_procedures',
        ]
        widgets = {'established_date': forms.DateInput(attrs={'type': 'date'})}
        labels = {
            'meals_program': 'Meals / nutrition programme',
            'learning_materials': 'Learning materials available',
            'staffing_adequate': 'Staffing adequate',
            'first_aid_ready': 'First aid readiness',
            'safeguarding_procedures': 'Child safeguarding procedures',
        }
        help_texts = {
            'meals_program': 'Whether a meals or nutrition programme is provided.',
            'learning_materials': 'Whether required ECDE learning materials are available.',
            'staffing_adequate': 'Whether staffing is adequate for current enrolment.',
            'first_aid_ready': 'Whether basic first aid and health-safety support is available.',
            'safeguarding_procedures': 'Whether child safeguarding procedures are in place.',
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ward'].queryset = Ward.objects.filter(
            subcounty__county__in=manageable_counties(user),
        ).select_related('subcounty__county')
        _style_fields(self)


class ECDEMembershipForm(forms.ModelForm):
    staff_number = forms.CharField(max_length=40, required=False)
    tsc_registration_number = forms.CharField(max_length=40, required=False)
    highest_qualification = forms.CharField(max_length=120, required=False)
    employment_type = forms.ChoiceField(
        choices=[('', 'Not recorded')] + ECDETeacherProfile.EMPLOYMENT_TYPE_CHOICES,
        required=False,
    )
    date_joined = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'}),
    )
    phone = forms.CharField(max_length=30, required=False)

    class Meta:
        model = ECDEMembership
        fields = [
            'user', 'role', 'county', 'subcounty', 'ward', 'centre', 'is_active',
        ]

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        counties = manageable_counties(user)
        self.fields['user'].queryset = User.objects.filter(
            is_active=True,
        ).order_by('email', 'username')
        self.fields['user'].label_from_instance = (
            lambda account: f'{account.get_full_name() or account.username} '
            f'({account.email})'
        )
        self.fields['county'].queryset = counties
        self.fields['subcounty'].queryset = SubCounty.objects.filter(
            county__in=counties,
        ).select_related('county')
        self.fields['ward'].queryset = Ward.objects.filter(
            subcounty__county__in=counties,
        ).select_related('subcounty__county')
        self.fields['centre'].queryset = ECDECentre.objects.filter(
            ward__subcounty__county__in=counties,
        ).select_related('ward__subcounty__county')
        self.fields['is_active'].initial = True
        for field_name in (
            'staff_number', 'tsc_registration_number', 'highest_qualification',
            'employment_type', 'date_joined', 'phone',
        ):
            self.fields[field_name].widget.attrs['data-ecde-teacher-profile'] = 'true'
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        county = cleaned.get('county')
        subcounty = cleaned.get('subcounty')
        ward = cleaned.get('ward')
        centre = cleaned.get('centre')

        if subcounty and county and subcounty.county_id != county.pk:
            self.add_error('subcounty', 'Select a sub-county in the selected county.')
        if ward and subcounty and ward.subcounty_id != subcounty.pk:
            self.add_error('ward', 'Select a ward in the selected sub-county.')
        if centre and ward and centre.ward_id != ward.pk:
            self.add_error('centre', 'Select a centre in the selected ward.')
        return cleaned

    def save_teacher_profile(self):
        membership = self.instance
        if membership.role != ECDEMembership.ROLE_ECDE_TEACHER:
            return None
        profile, _ = ECDETeacherProfile.objects.update_or_create(
            membership=membership,
            defaults={
                field_name: self.cleaned_data[field_name]
                for field_name in (
                    'staff_number', 'tsc_registration_number',
                    'highest_qualification', 'employment_type',
                    'date_joined', 'phone',
                )
            },
        )
        return profile


class ECDETeacherProfileForm(forms.ModelForm):
    class Meta:
        model = ECDETeacherProfile
        fields = [
            'staff_number', 'tsc_registration_number',
            'highest_qualification', 'employment_type',
            'date_joined', 'phone', 'notes',
        ]
        widgets = {'date_joined': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
