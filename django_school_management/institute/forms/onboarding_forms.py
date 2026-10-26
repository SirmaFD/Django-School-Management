from django import forms
from django.db import models
from django_countries.fields import CountryField

from django_school_management.institute.models import (
    InstituteProfile,
    INSTITUTE_TYPE_SCHOOL,
    INSTITUTE_TYPE_CHOICES,
)
from django_school_management.academics.models import Department, AcademicSession


FC = {'class': 'form-control'}


class OnboardingStep1Form(forms.ModelForm):
    """Institute profile basics including institute type."""

    class Meta:
        model = InstituteProfile
        fields = [
            'name', 'country', 'logo', 'motto', 'description',
            'date_of_estashment', 'institute_type',
        ]
        widgets = {
            'name': forms.TextInput(attrs={**FC, 'placeholder': 'Your institute name'}),
            'date_of_estashment': forms.DateInput(attrs={**FC, 'type': 'date'}),
            'motto': forms.Textarea(attrs={**FC, 'rows': 2, 'placeholder': 'Institute motto'}),
            'description': forms.Textarea(attrs={**FC, 'rows': 3, 'placeholder': 'Brief description'}),
            'institute_type': forms.Select(attrs={**FC}),
        }
        labels = {
            'date_of_estashment': 'Date of Establishment',
            'institute_type': 'Type of institution',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            ('', '---------'),
            (
                INSTITUTE_TYPE_SCHOOL,
                'Kenyan CBC School (Pre-Primary)',
            ),
        ]
        current_type = getattr(self.instance, 'institute_type', None)
        if current_type and current_type != INSTITUTE_TYPE_SCHOOL:
            legacy_choices = dict(INSTITUTE_TYPE_CHOICES)
            choices.append((current_type, legacy_choices[current_type]))
        self.fields['institute_type'].choices = choices
        if not self.instance.pk:
            self.fields['institute_type'].initial = INSTITUTE_TYPE_SCHOOL
            self.fields['country'].initial = 'KE'
        if 'country' in self.fields:
            self.fields['country'].widget.attrs.update(FC)


class OnboardingDepartmentForm(forms.Form):
    """Plain form for adding new departments during onboarding.
    All fields optional so empty rows are silently skipped."""

    name = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={**FC, 'placeholder': 'e.g. Computer Science'}),
    )
    short_name = forms.CharField(
        max_length=5, required=False,
        widget=forms.TextInput(attrs={**FC, 'placeholder': 'e.g. CSE'}),
    )
    code = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={**FC, 'placeholder': 'e.g. 101'}),
    )


OnboardingDepartmentFormSet = forms.formset_factory(
    OnboardingDepartmentForm,
    extra=1,
    max_num=20,
)


class OnboardingAcademicSessionForm(forms.ModelForm):
    """Academic session for onboarding."""

    class Meta:
        model = AcademicSession
        fields = ['year']
        widgets = {
            'year': forms.NumberInput(attrs={**FC, 'placeholder': 'e.g. 2026'}),
        }


class LoadSubjectsFromCurriculumForm(forms.Form):
    """Select a curriculum and its levels for loading subjects during onboarding."""

    curriculum = forms.ModelChoiceField(
        queryset=None,
        required=True,
        empty_label='Select curriculum',
        widget=forms.Select(attrs={**FC}),
        label='Curriculum',
    )
    class_range = forms.MultipleChoiceField(
        required=True,
        choices=(),
        widget=forms.CheckboxSelectMultiple,
        label='Classes / levels to set up',
    )

    def __init__(self, *args, **kwargs):
        self.institute = kwargs.pop('institute', None)
        super().__init__(*args, **kwargs)
        from django_school_management.curriculum.models import Curriculum

        if self.institute:
            qs = Curriculum.objects.filter(is_active=True)
            itype = getattr(self.institute, 'institute_type', None)
            if itype:
                qs = qs.filter(models.Q(institute_type=itype) | models.Q(institute_type=''))
            country = getattr(self.institute, 'country', None)
            country_code = getattr(country, 'code', str(country) if country else '')
            if country_code == 'KE':
                qs = qs.filter(
                    models.Q(code__startswith='KE-')
                    | models.Q(board__country='KE')
                )
        else:
            qs = Curriculum.objects.filter(is_active=True)

        qs = qs.prefetch_related('levels').order_by('display_order', 'name')
        self.fields['curriculum'].queryset = qs
        self.curriculum_level_choices = {
            str(curriculum.pk): [
                {
                    'value': str(level.level_number),
                    'label': level.name,
                }
                for level in curriculum.levels.all()
            ]
            for curriculum in qs
        }

        selected_curriculum = (
            self.data.get('curriculum') if self.is_bound
            else self.initial.get('curriculum')
        )
        selected_levels = self.curriculum_level_choices.get(
            str(selected_curriculum), []
        )
        self.fields['class_range'].choices = [
            (level['value'], level['label']) for level in selected_levels
        ]

    def get_class_numbers(self):
        """Return selected curriculum level numbers."""
        return sorted(int(number) for number in self.cleaned_data['class_range'])
