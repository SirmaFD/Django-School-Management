from django.contrib import admin

from .models import (
    AttendanceRecord, CBCProgressRecord, County, ECDECentre,
    ECDEAuditEvent, ECDEChild, ECDEChildTransfer, ECDEMembership,
    ECDETeacherProfile, SubCounty, Ward,
)


class SubCountyInline(admin.TabularInline):
    model = SubCounty
    extra = 0


class WardInline(admin.TabularInline):
    model = Ward
    extra = 0


@admin.register(County)
class CountyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')
    inlines = [SubCountyInline]


@admin.register(SubCounty)
class SubCountyAdmin(admin.ModelAdmin):
    list_display = ('name', 'county', 'code')
    list_filter = ('county',)
    search_fields = ('name', 'code', 'county__name')
    inlines = [WardInline]


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ('name', 'subcounty', 'code')
    list_filter = ('subcounty__county', 'subcounty')
    search_fields = ('name', 'code', 'subcounty__name', 'subcounty__county__name')


@admin.register(ECDECentre)
class ECDECentreAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'ward', 'is_active')
    list_filter = ('is_active', 'ward__subcounty__county')
    search_fields = ('name', 'code', 'registration_number', 'ward__name')


@admin.register(ECDEMembership)
class ECDEMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'county', 'subcounty', 'ward', 'centre', 'is_active')
    list_filter = ('role', 'is_active', 'county')
    search_fields = ('user__username', 'user__email')
    autocomplete_fields = ('user', 'county', 'subcounty', 'ward', 'centre')


@admin.register(ECDETeacherProfile)
class ECDETeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('membership', 'staff_number', 'tsc_registration_number', 'employment_type')
    search_fields = (
        'membership__user__username', 'membership__user__email',
        'staff_number', 'tsc_registration_number',
    )
    autocomplete_fields = ('membership',)


@admin.register(ECDEChild)
class ECDEChildAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'centre', 'level', 'is_active')
    list_filter = ('level', 'is_active', 'centre__ward__subcounty__county')
    search_fields = ('first_name', 'last_name', 'admission_number')


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('child', 'centre', 'date', 'status', 'recorded_by')
    list_filter = ('status', 'date', 'centre__ward__subcounty__county')
    search_fields = ('child__first_name', 'child__last_name', 'centre__name')


@admin.register(CBCProgressRecord)
class CBCProgressRecordAdmin(admin.ModelAdmin):
    list_display = ('child', 'centre', 'learning_area', 'progress', 'evidence_date')
    list_filter = ('learning_area', 'progress', 'evidence_date')
    search_fields = ('child__first_name', 'child__last_name', 'competency')


@admin.register(ECDEChildTransfer)
class ECDEChildTransferAdmin(admin.ModelAdmin):
    list_display = ('child', 'from_centre', 'to_centre', 'transfer_date', 'recorded_by')
    list_filter = ('transfer_date', 'from_centre__ward__subcounty__county')
    search_fields = ('child__first_name', 'child__last_name', 'from_centre__name', 'to_centre__name')
    readonly_fields = (
        'child', 'from_centre', 'to_centre', 'from_level', 'to_level',
        'transfer_date', 'reason', 'recorded_by', 'created', 'modified',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ECDEAuditEvent)
class ECDEAuditEventAdmin(admin.ModelAdmin):
    list_display = ('occurred_at', 'actor', 'action', 'summary', 'centre', 'county')
    list_filter = ('action', 'occurred_at', 'county')
    search_fields = ('summary', 'actor__username', 'centre__name')
    readonly_fields = (
        'occurred_at', 'actor', 'action', 'summary', 'details',
        'county', 'subcounty', 'ward', 'centre', 'related_centre',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
