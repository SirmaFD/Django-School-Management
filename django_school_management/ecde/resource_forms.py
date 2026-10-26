from django import forms

from .models import (
    CentreAnnualPlan, CentreAssessedNeed, CentreBudgetLine,
    CentreDeliveryReceipt, CentreInventoryItem, CentreInventoryMovement,
    CentreNeedsAssessment, CentreProcurementRequest, CentreSupplyAllocation,
    CentreSupplyReceipt, CountyInventoryItem,
)
from .management_forms import _style_fields, manageable_counties
from .access import accessible_centres


class CentreNeedsAssessmentForm(forms.ModelForm):
    class Meta:
        model = CentreNeedsAssessment
        fields = ['assessment_year', 'assessed_on', 'summary', 'status']
        widgets = {'assessed_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class CentreAssessedNeedForm(forms.ModelForm):
    estimated_cost = forms.DecimalField(
        min_value=0, max_digits=12, decimal_places=2, required=False,
    )

    class Meta:
        model = CentreAssessedNeed
        fields = [
            'category', 'description', 'quantity', 'estimated_cost', 'priority',
        ]
        labels = {'estimated_cost': 'Estimated cost (KES)'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class CentreAnnualPlanForm(forms.ModelForm):
    class Meta:
        model = CentreAnnualPlan
        fields = ['year', 'title', 'objectives']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class CentreBudgetLineForm(forms.ModelForm):
    quantity = forms.IntegerField(min_value=1)
    unit_cost = forms.DecimalField(min_value=0, max_digits=12, decimal_places=2)

    class Meta:
        model = CentreBudgetLine
        fields = [
            'plan', 'category', 'description', 'quantity', 'unit_cost',
            'funding_source',
        ]
        labels = {'unit_cost': 'Unit cost (KES)'}

    def __init__(self, *args, plan_queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].queryset = plan_queryset
        _style_fields(self)


class CentreProcurementRequestForm(forms.ModelForm):
    requested_amount = forms.DecimalField(
        min_value=0.01, max_digits=12, decimal_places=2,
    )

    class Meta:
        model = CentreProcurementRequest
        fields = ['plan', 'title', 'description', 'requested_amount']
        labels = {'requested_amount': 'Requested amount (KES)'}

    def __init__(self, *args, plan_queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plan'].queryset = plan_queryset
        _style_fields(self)


class CentreDeliveryReceiptForm(forms.ModelForm):
    quantity_received = forms.IntegerField(min_value=1)

    class Meta:
        model = CentreDeliveryReceipt
        fields = [
            'receipt_reference', 'supplier', 'received_on', 'items_received',
            'quantity_received', 'condition', 'notes',
        ]
        widgets = {'received_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class CentreInventoryItemForm(forms.ModelForm):
    opening_quantity = forms.DecimalField(
        min_value=0, max_digits=12, decimal_places=2,
    )
    reorder_level = forms.DecimalField(
        min_value=0, max_digits=12, decimal_places=2, required=False,
    )

    class Meta:
        model = CentreInventoryItem
        fields = ['name', 'unit', 'opening_quantity', 'reorder_level', 'notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)


class CentreInventoryMovementForm(forms.ModelForm):
    quantity = forms.DecimalField(
        min_value=0.01, max_digits=12, decimal_places=2,
    )

    class Meta:
        model = CentreInventoryMovement
        fields = [
            'movement_type', 'quantity', 'moved_on', 'reference',
            'usage_purpose', 'notes',
        ]
        widgets = {'moved_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['usage_purpose'].required = False
        _style_fields(self)


    def clean(self):
        cleaned = super().clean()
        if (
            cleaned.get('movement_type') == 'out'
            and not cleaned.get('usage_purpose')
        ):
            self.add_error(
                'usage_purpose',
                'Select a purpose for stock issued from inventory.',
            )
        return cleaned


class CountyInventoryItemForm(forms.ModelForm):
    opening_quantity = forms.DecimalField(
        min_value=0, max_digits=12, decimal_places=2,
    )

    class Meta:
        model = CountyInventoryItem
        fields = ['county', 'name', 'unit', 'opening_quantity', 'notes']

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['county'].queryset = manageable_counties(user)
        _style_fields(self)


class CountyStockInForm(forms.Form):
    item = forms.ModelChoiceField(queryset=CountyInventoryItem.objects.none())
    quantity = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2)
    moved_on = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
    )
    reference = forms.CharField(max_length=100, required=False)
    notes = forms.CharField(
        required=False, widget=forms.Textarea(attrs={'rows': 2}),
    )

    def __init__(self, *args, item_queryset, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = item_queryset
        _style_fields(self)


class SupplyAllocationForm(forms.ModelForm):
    class Meta:
        model = CentreSupplyAllocation
        fields = ['centre', 'stock_item', 'quantity', 'reference', 'notes']

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        counties = manageable_counties(user)
        self.fields['centre'].queryset = accessible_centres(user).filter(
            ward__subcounty__county__in=counties,
        ).select_related('ward__subcounty__county')
        self.fields['stock_item'].queryset = CountyInventoryItem.objects.filter(
            county__in=counties,
        ).select_related('county')
        self.fields['quantity'].min_value = 0.01
        _style_fields(self)

    def clean(self):
        cleaned = super().clean()
        centre = cleaned.get('centre')
        stock_item = cleaned.get('stock_item')
        if centre and stock_item and centre.county.pk != stock_item.county_id:
            self.add_error(
                'stock_item',
                'Choose stock from the selected centre’s county.',
            )
        return cleaned


class CentreSupplyReceiptForm(forms.ModelForm):
    class Meta:
        model = CentreSupplyReceipt
        fields = [
            'receipt_reference', 'quantity_received', 'received_on',
            'condition', 'notes',
        ]
        widgets = {'received_on': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quantity_received'].min_value = 0.01
        _style_fields(self)


class ProcurementDecisionForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[('approved', 'Approve'), ('rejected', 'Reject')],
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_fields(self)
