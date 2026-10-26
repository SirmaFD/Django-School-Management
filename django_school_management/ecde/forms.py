from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    AttendanceRecord, CBCProgressRecord, ECDEChild, ECDEChildTransfer,
)


def _style_fields(form):
    for field in form.fields.values():
        css_class = 'form-check-input' if isinstance(
            field.widget, forms.CheckboxInput,
        ) else 'form-control'
        current_class = field.widget.attrs.get('class', '')
        field.widget.attrs['class'] = f'{current_class} {css_class}'.strip()


class ECDEChildForm(forms.ModelForm):
    def __init__(self, *args, centre, **kwargs):
        super().__init__(*args, **kwargs)
        self.centre = centre
        if 'enrollment_date' in self.fields:
            self.fields['enrollment_date'].required = False
        _style_fields(self)

    class Meta:
        model = ECDEChild
        fields = [
            'learner_number', 'admission_number', 'first_name', 'middle_names',
            'last_name', 'date_of_birth', 'gender', 'level', 'enrollment_date',
            'guardian_name', 'guardian_relationship', 'guardian_phone',
            'alternate_guardian_name', 'alternate_guardian_phone',
            'guardian_email', 'home_village',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'enrollment_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_date_of_birth(self):
        value = self.cleaned_data['date_of_birth']
        if value >= timezone.localdate():
            raise ValidationError('Date of birth must be in the past.')
        return value

    def clean_enrollment_date(self):
        return (
            self.cleaned_data.get('enrollment_date')
            or self.instance.enrollment_date
            or timezone.localdate()
        )

    def clean(self):
        cleaned_data = super().clean()
        admission_number = cleaned_data.get('admission_number')
        if admission_number and ECDEChild.objects.filter(
            centre=self.centre,
            admission_number=admission_number,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error(
                'admission_number',
                'This admission number is already used at this centre.',
            )
        learner_number = cleaned_data.get('learner_number')
        if learner_number and ECDEChild.objects.filter(
            centre=self.centre,
            learner_number=learner_number,
        ).exclude(pk=self.instance.pk).exists():
            self.add_error(
                'learner_number',
                'This learner number is already used at this centre.',
            )
        return cleaned_data


class ECDEChildProfileForm(ECDEChildForm):
    class Meta(ECDEChildForm.Meta):
        fields = [
            'learner_number', 'admission_number', 'first_name', 'middle_names',
            'last_name', 'date_of_birth', 'gender', 'level',
            'guardian_name', 'guardian_relationship', 'guardian_phone',
            'alternate_guardian_name', 'alternate_guardian_phone',
            'guardian_email', 'home_village',
        ]


class ECDEChildLifecycleForm(forms.ModelForm):
    class Meta:
        model = ECDEChild
        fields = ['status', 'exit_date', 'exit_reason']
        widgets = {'exit_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class ECDEChildTransferForm(forms.ModelForm):
    class Meta:
        model = ECDEChildTransfer
        fields = ['child', 'to_centre', 'to_level', 'transfer_date', 'reason']
        widgets = {'transfer_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, from_centre, destination_centres, **kwargs):
        super().__init__(*args, **kwargs)
        self.from_centre = from_centre
        self.fields['child'].queryset = from_centre.children.filter(
            is_active=True, status=ECDEChild.STATUS_ENROLLED,
        )
        self.fields['to_centre'].queryset = destination_centres.exclude(
            pk=from_centre.pk,
        )
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        child = cleaned.get('child')
        destination = cleaned.get('to_centre')
        transfer_date = cleaned.get('transfer_date')
        if child and transfer_date and transfer_date < child.enrollment_date:
            self.add_error(
                'transfer_date',
                "The transfer date cannot be before the child's enrolment date.",
            )
        if child and destination:
            if child.admission_number and destination.children.exclude(
                pk=child.pk,
            ).filter(admission_number=child.admission_number).exists():
                self.add_error(
                    'child',
                    'The destination centre already uses this admission number.',
                )
            if child.learner_number and destination.children.exclude(
                pk=child.pk,
            ).filter(learner_number=child.learner_number).exists():
                self.add_error(
                    'child',
                    'The destination centre already uses this learner number.',
                )
        return cleaned

    def save(self, commit=True, *, recorded_by):
        transfer = super().save(commit=False)
        transfer.from_centre = self.from_centre
        transfer.from_level = transfer.child.level
        transfer.recorded_by = recorded_by
        if commit:
            transfer.full_clean()
            transfer.save()
            transfer.child.centre = transfer.to_centre
            transfer.child.level = transfer.to_level
            transfer.child.full_clean()
            transfer.child.save(update_fields=[
                'centre', 'level', 'modified',
            ])
        return transfer


class AttendanceRecordForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ['child', 'date', 'status', 'notes']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, centre, **kwargs):
        super().__init__(*args, **kwargs)
        self.centre = centre
        self.fields['child'].queryset = centre.children.filter(is_active=True)
        _style_fields(self)

    def save(self, commit=True, *, recorded_by):
        record = super().save(commit=False)
        record.centre = self.centre
        record.recorded_by = recorded_by
        if commit:
            record.full_clean()
            record.save()
        return record


class CBCProgressRecordForm(forms.ModelForm):
    class Meta:
        model = CBCProgressRecord
        fields = [
            'child', 'learning_area', 'competency', 'progress',
            'observation', 'evidence_date',
        ]
        widgets = {'evidence_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, centre, **kwargs):
        super().__init__(*args, **kwargs)
        self.centre = centre
        self.fields['child'].queryset = centre.children.filter(is_active=True)
        _style_fields(self)

    def save(self, commit=True, *, recorded_by):
        record = super().save(commit=False)
        record.centre = self.centre
        record.recorded_by = recorded_by
        if commit:
            record.full_clean()
            record.save()
        return record
