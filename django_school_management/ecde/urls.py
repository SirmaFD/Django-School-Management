from django.urls import path

from . import resource_views, views

app_name = 'ecde'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('manage/', views.manage, name='manage'),
    path('manage/counties/', views.manage_counties, name='manage_counties'),
    path(
        'manage/subcounties/',
        views.manage_subcounties,
        name='manage_subcounties',
    ),
    path('manage/wards/', views.manage_wards, name='manage_wards'),
    path('manage/centres/', views.manage_centres, name='manage_centres'),
    path(
        'manage/centres/add/',
        views.add_centre,
        name='add_centre',
    ),
    path('manage/staff/', views.manage_staff, name='manage_staff'),
    path(
        'manage/county-supplies/',
        resource_views.county_supply_stock,
        name='county_supply_stock',
    ),
    path('audit/', views.audit_log, name='audit_log'),
    path('centres/<int:centre_id>/children/', views.children, name='children'),
    path(
        'centres/<int:centre_id>/children/<int:child_id>/',
        views.child_detail,
        name='child_detail',
    ),
    path('centres/<int:centre_id>/attendance/', views.attendance, name='attendance'),
    path('centres/<int:centre_id>/progress/', views.progress, name='progress'),
    path(
        'centres/<int:centre_id>/resources/',
        resource_views.centre_resources,
        name='resources',
    ),
]
