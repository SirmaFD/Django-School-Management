from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.test import RequestFactory

from django_school_management.accounts.models import User
from context_processors.attach_resources import attach_dashboard_menu_items

from .access import accessible_centres
from .audit import record_audit_event
from .resource_forms import SupplyAllocationForm
from .models import (
    AttendanceRecord, CBCProgressRecord, County, ECDEAuditEvent,
    CentreAnnualPlan, CentreDeliveryReceipt, CentreInventoryItem,
    CentreInventoryMovement, CentreNeedsAssessment, CentreProcurementRequest,
    CentreSupplyAllocation, CentreSupplyReceipt, CountyInventoryItem,
    CountyInventoryMovement, ECDECentre, ECDEChild, ECDEChildTransfer,
    ECDEMembership, ECDETeacherProfile, SubCounty, Ward,
)


class ECDEWorkflowTests(TestCase):
    def setUp(self):
        self.county = County.objects.create(name='Sample County', code='999')
        self.subcounty = SubCounty.objects.create(
            county=self.county, name='Sample Sub-county', code='999-1',
        )
        self.ward = Ward.objects.create(
            subcounty=self.subcounty, name='Sample Ward', code='999-1-1',
        )
        self.centre = ECDECentre.objects.create(
            ward=self.ward, name='Sample ECDE Centre', code='SAMPLE-1',
        )
        sibling_ward = Ward.objects.create(
            subcounty=self.subcounty, name='Second Ward', code='999-1-2',
        )
        self.sibling_centre = ECDECentre.objects.create(
            ward=sibling_ward, name='Second ECDE Centre', code='SAMPLE-2',
        )
        other_county = County.objects.create(name='Other County', code='998')
        other_subcounty = SubCounty.objects.create(
            county=other_county, name='Other Sub-county', code='998-1',
        )
        other_ward = Ward.objects.create(
            subcounty=other_subcounty, name='Other Ward', code='998-1-1',
        )
        self.other_centre = ECDECentre.objects.create(
            ward=other_ward, name='Other ECDE Centre', code='OTHER-1',
        )
        self.user = User.objects.create_user(
            username='county-officer',
            email='county@example.test',
            password='test-password',
        )
        self.child = ECDEChild.objects.create(
            centre=self.centre,
            first_name='Amani',
            last_name='Otieno',
            date_of_birth=date(2021, 2, 1),
            gender='F',
            level='PP1',
            guardian_name='Guardian Otieno',
            guardian_phone='0712345678',
            enrolled_by=self.user,
        )

    def test_seed_demo_centres_is_repeatable_and_marks_synthetic_records(self):
        output = StringIO()

        call_command('seed_demo_centres', stdout=output)

        nandi = County.objects.get(code='029', name='Nandi')
        centres = ECDECentre.objects.filter(
            ward__subcounty__county=nandi,
            code__startswith='NDI-DEMO-',
        )
        self.assertEqual(centres.count(), 12)
        self.assertTrue(
            all(centre.name.startswith('DEMO -') for centre in centres)
        )
        self.assertTrue(
            centres.first().address.startswith('Synthetic demo location')
        )
        self.assertEqual(centres.first().registration_status, 'unknown')

        call_command('seed_demo_centres', stdout=StringIO())

        self.assertEqual(centres.count(), 12)
        self.assertIn('12 centres created', output.getvalue())

    def test_county_membership_sees_only_centres_in_its_county(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )

        self.assertQuerySetEqual(
            accessible_centres(self.user).order_by('pk'),
            [self.centre, self.sibling_centre],
        )

    def test_subcounty_membership_sees_its_wards_only(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_SUBCOUNTY_OFFICER,
            subcounty=self.subcounty,
        )

        self.assertQuerySetEqual(
            accessible_centres(self.user).order_by('pk'),
            [self.centre, self.sibling_centre],
        )

    def test_ward_membership_sees_only_its_ward_centres(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_WARD_COORDINATOR,
            ward=self.ward,
        )

        self.assertQuerySetEqual(accessible_centres(self.user), [self.centre])

    def test_centre_membership_sees_only_its_assigned_centre(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )

        self.assertQuerySetEqual(accessible_centres(self.user), [self.centre])

    def test_unassigned_user_sees_no_centres(self):
        self.assertFalse(accessible_centres(self.user).exists())

    def test_county_admin_can_open_management_page_and_dashboard_link(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('ecde:manage'))
        dashboard = self.client.get(reverse('ecde:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sub-counties')
        self.assertContains(response, 'county hierarchy')
        self.assertNotContains(response, 'Register an ECDE centre')
        self.assertNotContains(response, 'Assign ECDE access')
        centres_response = self.client.get(reverse('ecde:manage_centres'))
        self.assertEqual(centres_response.status_code, 200)
        self.assertContains(centres_response, 'ECDE centre management')
        self.assertContains(centres_response, reverse('ecde:add_centre'))
        add_centre_response = self.client.get(reverse('ecde:add_centre'))
        self.assertContains(add_centre_response, 'Register an ECDE centre')
        staff_response = self.client.get(reverse('ecde:manage_staff'))
        self.assertEqual(staff_response.status_code, 200)
        self.assertContains(staff_response, 'Assign ECDE access')
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, reverse('ecde:manage'))
        self.assertContains(dashboard, '<table')
        self.assertContains(dashboard, 'Centres in your assigned area')
        self.assertContains(dashboard, self.centre.name)
        self.assertContains(
            dashboard,
            reverse('ecde:children', args=[self.centre.pk]),
        )
        self.assertContains(
            dashboard,
            reverse('ecde:resources', args=[self.centre.pk]),
        )

    def test_dashboard_sidebar_menu_context_includes_ecde_links_by_role(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        request = RequestFactory().get('/account/dashboard/')
        request.user = self.user

        menu_context = attach_dashboard_menu_items(request)

        self.assertTrue(menu_context['has_ecde_access'])
        self.assertTrue(menu_context['can_manage_ecde'])
        menu_urls = {item['url'] for item in menu_context['ecde_menu_items']}
        self.assertIn(reverse('ecde:dashboard'), menu_urls)
        self.assertIn(reverse('ecde:manage'), menu_urls)
        self.assertIn(reverse('ecde:manage_counties'), menu_urls)
        self.assertIn(reverse('ecde:manage_subcounties'), menu_urls)
        self.assertIn(reverse('ecde:manage_wards'), menu_urls)
        self.assertIn(reverse('ecde:manage_centres'), menu_urls)
        self.assertIn(reverse('ecde:add_centre'), menu_urls)
        self.assertIn(reverse('ecde:audit_log'), menu_urls)
        self.assertIn(reverse('ecde:children', args=[self.centre.pk]), menu_urls)
        self.assertIn(reverse('ecde:attendance', args=[self.centre.pk]), menu_urls)
        self.assertIn(reverse('ecde:progress', args=[self.centre.pk]), menu_urls)
        self.assertIn(reverse('ecde:resources', args=[self.centre.pk]), menu_urls)
        self.assertIn(
            reverse('ecde:children', args=[self.sibling_centre.pk]),
            menu_urls,
        )
        self.assertNotIn(
            reverse('ecde:children', args=[self.other_centre.pk]),
            menu_urls,
        )

    def test_centre_staff_menu_contains_only_assigned_centre_workflows(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        request = RequestFactory().get('/account/dashboard/')
        request.user = self.user

        menu_context = attach_dashboard_menu_items(request)
        menu_urls = {item['url'] for item in menu_context['ecde_menu_items']}

        self.assertTrue(menu_context['has_ecde_access'])
        self.assertFalse(menu_context['can_manage_ecde'])
        self.assertIn(reverse('ecde:audit_log'), menu_urls)
        self.assertIn(reverse('ecde:children', args=[self.centre.pk]), menu_urls)
        self.assertIn(reverse('ecde:attendance', args=[self.centre.pk]), menu_urls)
        self.assertIn(reverse('ecde:progress', args=[self.centre.pk]), menu_urls)
        self.assertNotIn(reverse('ecde:manage'), menu_urls)
        self.assertNotIn(reverse('ecde:manage_centres'), menu_urls)
        self.assertNotIn(
            reverse('ecde:children', args=[self.sibling_centre.pk]),
            menu_urls,
        )
        self.assertNotIn(
            reverse('ecde:children', args=[self.other_centre.pk]),
            menu_urls,
        )

    def test_dashboard_sidebar_menu_hides_ecde_links_from_unassigned_user(self):
        request = RequestFactory().get('/account/dashboard/')
        request.user = self.user

        menu_context = attach_dashboard_menu_items(request)

        self.assertFalse(menu_context['has_ecde_access'])
        self.assertFalse(menu_context['can_manage_ecde'])

    def test_account_dashboard_sidebar_renders_ecde_navigation_links(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.user.approval_status = 'a'
        self.user.requested_role = 'admin'
        self.user.save(update_fields=['approval_status', 'requested_role'])
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('account:dashboard'),
            {'skip_onboarding': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('ecde:dashboard'))
        self.assertContains(response, reverse('ecde:manage'))
        self.assertContains(response, reverse('ecde:manage_counties'))
        self.assertContains(response, reverse('ecde:manage_subcounties'))
        self.assertContains(response, reverse('ecde:manage_wards'))
        self.assertContains(response, 'Manage administrative areas')
        self.assertContains(response, reverse('ecde:manage_centres'))
        self.assertContains(response, reverse('ecde:add_centre'))
        self.assertContains(response, 'Add ECDE centre')
        self.assertContains(response, 'Manage centres')
        self.assertContains(response, reverse('ecde:audit_log'))
        self.assertContains(
            response,
            reverse('ecde:children', args=[self.centre.pk]),
        )
        self.assertContains(
            response,
            reverse('ecde:attendance', args=[self.centre.pk]),
        )
        self.assertContains(
            response,
            reverse('ecde:progress', args=[self.centre.pk]),
        )
        self.assertContains(response, reverse('ecde:resources', args=[self.centre.pk]))
        self.assertContains(response, reverse('ecde:manage_staff'))
        self.assertContains(response, 'Manage ECDE staff access')

    def test_ecde_pages_inherit_the_shared_dashboard_shell(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)
        urls = [
            reverse('ecde:dashboard'),
            reverse('ecde:manage'),
            reverse('ecde:manage_counties'),
            reverse('ecde:manage_subcounties'),
            reverse('ecde:manage_wards'),
            reverse('ecde:manage_centres'),
            reverse('ecde:add_centre'),
            reverse('ecde:manage_staff'),
            reverse('ecde:audit_log'),
            reverse('ecde:children', args=[self.centre.pk]),
            reverse('ecde:child_detail', args=[self.centre.pk, self.child.pk]),
            reverse('ecde:attendance', args=[self.centre.pk]),
            reverse('ecde:progress', args=[self.centre.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'css/dashboard-modern.css')
                self.assertContains(response, 'id="sidebar-toggle"')

    def test_unassigned_user_cannot_open_management_page(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('ecde:manage'))
        counties_response = self.client.get(reverse('ecde:manage_counties'))
        subcounties_response = self.client.get(reverse('ecde:manage_subcounties'))
        wards_response = self.client.get(reverse('ecde:manage_wards'))
        staff_response = self.client.get(reverse('ecde:manage_staff'))
        centres_response = self.client.get(reverse('ecde:manage_centres'))
        add_centre_response = self.client.get(reverse('ecde:add_centre'))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(counties_response.status_code, 403)
        self.assertEqual(subcounties_response.status_code, 403)
        self.assertEqual(wards_response.status_code, 403)
        self.assertEqual(staff_response.status_code, 403)
        self.assertEqual(centres_response.status_code, 403)
        self.assertEqual(add_centre_response.status_code, 403)

    def test_county_admin_can_create_subcounty_only_in_own_county(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:manage'),
            {
                'action': 'create_subcounty',
                'county': self.county.pk,
                'name': 'New Sub-county',
                'code': '999-3',
            },
        )

        self.assertRedirects(response, reverse('ecde:manage'))
        self.assertTrue(
            SubCounty.objects.filter(
                county=self.county, name='New Sub-county',
            ).exists(),
        )

    def test_subcounty_page_supports_scoped_create_update_and_delete(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)
        url = reverse('ecde:manage_subcounties')

        create_response = self.client.post(url, {
            'action': 'create',
            'county': self.county.pk,
            'name': 'New Sub-county',
            'code': '999-3',
        })
        subcounty = SubCounty.objects.get(code='999-3')
        self.assertRedirects(create_response, url)

        update_response = self.client.post(url, {
            'action': 'update',
            'object_id': subcounty.pk,
            'county': self.county.pk,
            'name': 'Updated Sub-county',
            'code': '999-4',
        })
        subcounty.refresh_from_db()
        self.assertRedirects(update_response, url)
        self.assertEqual(subcounty.name, 'Updated Sub-county')

        delete_response = self.client.post(url, {
            'action': 'delete',
            'object_id': subcounty.pk,
        })
        self.assertRedirects(delete_response, url)
        self.assertFalse(SubCounty.objects.filter(pk=subcounty.pk).exists())

    def test_subcounty_delete_is_blocked_when_it_has_wards(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse('ecde:manage_subcounties'), {
            'action': 'delete',
            'object_id': self.subcounty.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(SubCounty.objects.filter(pk=self.subcounty.pk).exists())
        self.assertContains(response, 'cannot be deleted')

    def test_county_admin_cannot_edit_or_delete_out_of_scope_subcounty(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)
        url = reverse('ecde:manage_subcounties')

        update_response = self.client.post(url, {
            'action': 'update',
            'object_id': self.other_centre.subcounty.pk,
            'county': self.county.pk,
            'name': 'Unauthorized change',
            'code': '999-8',
        })
        delete_response = self.client.post(url, {
            'action': 'delete',
            'object_id': self.other_centre.subcounty.pk,
        })

        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertEqual(
            self.other_centre.subcounty.name,
            'Other Sub-county',
        )

    def test_ward_page_supports_scoped_create_update_and_delete(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)
        url = reverse('ecde:manage_wards')
        subcounty = SubCounty.objects.create(
            county=self.county, name='Empty Sub-county', code='999-9',
        )

        create_response = self.client.post(url, {
            'action': 'create',
            'subcounty': subcounty.pk,
            'name': 'New Ward',
            'code': '999-9-1',
        })
        ward = Ward.objects.get(code='999-9-1')
        self.assertRedirects(create_response, url)

        update_response = self.client.post(url, {
            'action': 'update',
            'object_id': ward.pk,
            'subcounty': subcounty.pk,
            'name': 'Updated Ward',
            'code': '999-9-2',
        })
        ward.refresh_from_db()
        self.assertRedirects(update_response, url)
        self.assertEqual(ward.name, 'Updated Ward')

        delete_response = self.client.post(url, {
            'action': 'delete',
            'object_id': ward.pk,
        })
        self.assertRedirects(delete_response, url)
        self.assertFalse(Ward.objects.filter(pk=ward.pk).exists())

    def test_ward_delete_is_blocked_when_it_has_centres(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse('ecde:manage_wards'), {
            'action': 'delete',
            'object_id': self.ward.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Ward.objects.filter(pk=self.ward.pk).exists())
        self.assertContains(response, 'cannot be deleted')

    def test_county_page_allows_superuser_create_update_and_delete(self):
        admin = User.objects.create_superuser(
            username='ecde-superuser',
            email='ecde-superuser@example.test',
            password='test-password',
        )
        self.client.force_login(admin)
        url = reverse('ecde:manage_counties')

        create_response = self.client.post(url, {
            'action': 'create',
            'name': 'Temporary County',
            'code': '996',
        })
        county = County.objects.get(code='996')
        self.assertRedirects(create_response, url)

        update_response = self.client.post(url, {
            'action': 'update',
            'object_id': county.pk,
            'name': 'Updated Temporary County',
            'code': '995',
        })
        county.refresh_from_db()
        self.assertRedirects(update_response, url)
        self.assertEqual(county.name, 'Updated Temporary County')

        delete_response = self.client.post(url, {
            'action': 'delete',
            'object_id': county.pk,
        })
        self.assertRedirects(delete_response, url)
        self.assertFalse(County.objects.filter(pk=county.pk).exists())

    def test_county_delete_is_blocked_when_staff_are_assigned(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        admin = User.objects.create_superuser(
            username='ecde-superuser',
            email='ecde-superuser@example.test',
            password='test-password',
        )
        self.client.force_login(admin)

        response = self.client.post(reverse('ecde:manage_counties'), {
            'action': 'delete',
            'object_id': self.county.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(County.objects.filter(pk=self.county.pk).exists())
        self.assertTrue(ECDEMembership.objects.filter(user=self.user).exists())
        self.assertContains(response, 'cannot be deleted')

    def test_county_admin_can_register_centre_on_dedicated_add_page(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:add_centre'),
            {
                'ward': self.ward.pk,
                'name': 'New Centre',
                'code': 'NEW-01',
                'registration_status': 'pending',
                'ownership': 'community',
                'capacity': '40',
                'classroom_count': '2',
                'water_source': 'borehole',
                'electricity': 'yes',
                'kitchen': 'no',
                'playground': 'yes',
                'disability_access': 'unknown',
                'facility_condition': 'good',
                'meals_program': 'yes',
                'learning_materials': 'yes',
                'staffing_adequate': 'no',
                'first_aid_ready': 'unknown',
                'safeguarding_procedures': 'yes',
            },
        )

        self.assertRedirects(response, reverse('ecde:manage_centres'))
        centre = ECDECentre.objects.get(code='NEW-01')
        self.assertEqual(centre.ward, self.ward)
        self.assertEqual(centre.capacity, 40)
        self.assertEqual(centre.meals_program, 'yes')
        self.assertEqual(centre.learning_materials, 'yes')
        self.assertEqual(centre.staffing_adequate, 'no')
        self.assertEqual(centre.first_aid_ready, 'unknown')
        self.assertEqual(centre.safeguarding_procedures, 'yes')
        self.assertTrue(
            ECDEAuditEvent.objects.filter(
                action='create',
                summary='ECDE centre New Centre was created.',
            ).exists(),
        )

    def test_resource_planning_procurement_receipts_and_manual_inventory(self):
        manager = User.objects.create_user(
            username='resource-manager',
            email='resource-manager@example.test',
            password='test-password',
        )
        ECDEMembership.objects.create(
            user=manager,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        url = reverse('ecde:resources', args=[self.centre.pk])
        self.client.force_login(manager)

        response = self.client.post(url, {
            'action': 'create_assessment',
            'assessment_year': '2026',
            'assessed_on': '2026-10-22',
            'summary': 'The centre needs learning materials.',
            'status': 'draft',
        })
        self.assertRedirects(response, f'{url}#needs-assessments')
        assessment = CentreNeedsAssessment.objects.get(centre=self.centre)

        response = self.client.post(url, {
            'action': 'add_need',
            'assessment_id': assessment.pk,
            'category': 'learning_materials',
            'description': 'CBC learner books',
            'quantity': '20',
            'estimated_cost': '12000.00',
            'priority': 'high',
        })
        self.assertRedirects(response, f'{url}#needs-assessments')
        self.assertEqual(assessment.needs.count(), 1)

        response = self.client.post(url, {
            'action': 'submit_assessment',
            'assessment_id': assessment.pk,
        })
        self.assertRedirects(response, f'{url}#needs-assessments')
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, 'submitted')

        response = self.client.post(url, {
            'action': 'create_plan',
            'year': '2026',
            'title': '2026 ECDE work plan',
            'objectives': 'Improve access to learning materials.',
        })
        self.assertRedirects(response, f'{url}#annual-plans')
        plan = CentreAnnualPlan.objects.get(centre=self.centre)

        response = self.client.post(url, {
            'action': 'add_budget_line',
            'plan': plan.pk,
            'category': 'learning_materials',
            'description': 'CBC learner books',
            'quantity': '20',
            'unit_cost': '600.00',
            'funding_source': 'County allocation',
        })
        self.assertRedirects(response, f'{url}#annual-plans')
        self.assertEqual(plan.budget_lines.get().total_cost, Decimal('12000.00'))

        response = self.client.post(url, {
            'action': 'submit_plan',
            'plan_id': plan.pk,
        })
        self.assertRedirects(response, f'{url}#annual-plans')
        self.client.force_login(self.user)
        response = self.client.post(url, {
            'action': 'review_plan',
            'plan_id': plan.pk,
            'decision': 'approved',
            'notes': 'Approved within annual allocation.',
        })
        self.assertRedirects(response, f'{url}#annual-plans')
        plan.refresh_from_db()
        self.assertEqual(plan.status, 'approved')

        self.client.force_login(manager)
        response = self.client.post(url, {
            'action': 'create_procurement',
            'plan': plan.pk,
            'title': 'Purchase learner books',
            'description': 'Twenty CBC learner books.',
            'requested_amount': '12000.00',
        })
        self.assertRedirects(response, f'{url}#procurement')
        procurement = CentreProcurementRequest.objects.get(centre=self.centre)

        self.client.force_login(self.user)
        response = self.client.post(url, {
            'action': 'decide_procurement',
            'procurement_id': procurement.pk,
            'decision': 'approved',
            'notes': 'Approved.',
        })
        self.assertRedirects(response, f'{url}#procurement')
        procurement.refresh_from_db()
        self.assertEqual(procurement.status, 'approved')

        response = self.client.post(url, {
            'action': 'mark_ordered',
            'procurement_id': procurement.pk,
        })
        self.assertRedirects(response, f'{url}#procurement')
        procurement.refresh_from_db()
        self.assertEqual(procurement.status, 'ordered')

        self.client.force_login(manager)
        response = self.client.post(url, {
            'action': 'record_receipt',
            'procurement_id': procurement.pk,
            'receipt_reference': 'DEL-001',
            'supplier': 'Demo supplier',
            'received_on': '2026-10-22',
            'items_received': 'CBC learner books',
            'quantity_received': '20',
            'condition': 'good',
            'notes': '',
            'delivery_complete': 'on',
        })
        self.assertRedirects(response, f'{url}#procurement')
        self.assertEqual(
            CentreDeliveryReceipt.objects.get(
                procurement_request=procurement,
            ).quantity_received,
            20,
        )
        procurement.refresh_from_db()
        self.assertEqual(procurement.status, 'received')

        response = self.client.post(url, {
            'action': 'create_inventory_item',
            'name': 'CBC learner books',
            'unit': 'books',
            'opening_quantity': '5',
            'reorder_level': '2',
            'notes': 'Opening count.',
        })
        self.assertRedirects(response, f'{url}#inventory')
        item = CentreInventoryItem.objects.get(centre=self.centre)
        self.assertEqual(item.quantity_on_hand, Decimal('5'))

        response = self.client.post(url, {
            'action': 'record_inventory_movement',
            'item_id': item.pk,
            'movement_type': 'in',
            'quantity': '10',
            'moved_on': '2026-10-22',
            'reference': 'STOCK-001',
            'notes': 'Manual stock record after receipt verification.',
        })
        self.assertRedirects(response, f'{url}#inventory')
        item.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, Decimal('15'))

        response = self.client.post(url, {
            'action': 'record_inventory_movement',
            'item_id': item.pk,
            'movement_type': 'out',
            'quantity': '20',
            'moved_on': '2026-10-22',
            'reference': 'ISSUE-001',
            'usage_purpose': 'teaching',
            'notes': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(item.movements.count(), 1)
        self.assertContains(response, 'Only 15.00 books are in stock.')

    def test_county_admin_dispatch_reduces_county_stock_once(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)
        stock_url = reverse('ecde:county_supply_stock')

        response = self.client.post(stock_url, {
            'action': 'create_stock_item',
            'county': self.county.pk,
            'name': 'Story books',
            'unit': 'books',
            'opening_quantity': '10',
            'notes': '',
        })
        self.assertRedirects(response, stock_url)
        item = CountyInventoryItem.objects.get(name='Story books')
        self.assertEqual(item.quantity_on_hand, Decimal('10'))

        response = self.client.post(stock_url, {
            'action': 'create_allocation',
            'centre': self.centre.pk,
            'stock_item': item.pk,
            'quantity': '7',
            'reference': 'DIST-001',
            'notes': '',
        })
        self.assertRedirects(response, stock_url)
        allocation = CentreSupplyAllocation.objects.get(centre=self.centre)
        self.assertEqual(allocation.status, 'draft')

        response = self.client.post(stock_url, {
            'action': 'dispatch_allocation',
            'allocation_id': allocation.pk,
        })
        self.assertRedirects(response, stock_url)
        item.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, Decimal('3'))
        self.assertEqual(allocation.status, 'dispatched')
        self.assertEqual(
            CountyInventoryMovement.objects.filter(
                allocation=allocation,
                movement_type='out',
            ).count(),
            1,
        )

        duplicate_dispatch = self.client.post(stock_url, {
            'action': 'dispatch_allocation',
            'allocation_id': allocation.pk,
        })
        self.assertEqual(duplicate_dispatch.status_code, 404)
        self.assertEqual(item.quantity_on_hand, Decimal('3'))
        self.assertEqual(
            CountyInventoryMovement.objects.filter(allocation=allocation).count(),
            1,
        )

    def test_dispatch_rejects_quantity_above_county_stock(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        item = CountyInventoryItem.objects.create(
            county=self.county,
            name='Exercise mats',
            unit='mats',
            opening_quantity=Decimal('2'),
        )
        allocation = CentreSupplyAllocation.objects.create(
            centre=self.centre,
            stock_item=item,
            quantity=Decimal('3'),
            allocated_by=self.user,
        )
        self.client.force_login(self.user)

        response = self.client.post(reverse('ecde:county_supply_stock'), {
            'action': 'dispatch_allocation',
            'allocation_id': allocation.pk,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Insufficient county stock')
        item.refresh_from_db()
        allocation.refresh_from_db()
        self.assertEqual(item.quantity_on_hand, Decimal('2'))
        self.assertEqual(allocation.status, 'draft')
        self.assertFalse(
            CountyInventoryMovement.objects.filter(allocation=allocation).exists(),
        )

    def test_supply_allocation_form_rejects_cross_county_stock(self):
        other_item = CountyInventoryItem.objects.create(
            county=self.other_centre.county,
            name='Other county books',
            unit='books',
            opening_quantity=Decimal('10'),
        )
        county_admin = User.objects.create_superuser(
            username='distribution-superuser',
            email='distribution-superuser@example.test',
            password='test-password',
        )
        form = SupplyAllocationForm(
            data={
                'centre': self.centre.pk,
                'stock_item': other_item.pk,
                'quantity': '1',
                'reference': '',
                'notes': '',
            },
            user=county_admin,
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            'Choose stock from the selected centre’s county.',
            form.errors['stock_item'],
        )

    def test_centre_manager_confirms_partial_distribution_into_inventory(self):
        manager = User.objects.create_user(
            username='distribution-manager',
            email='distribution-manager@example.test',
            password='test-password',
        )
        ECDEMembership.objects.create(
            user=manager,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        item = CountyInventoryItem.objects.create(
            county=self.county,
            name='Learning kits',
            unit='kits',
            opening_quantity=Decimal('10'),
        )
        allocation = CentreSupplyAllocation.objects.create(
            centre=self.centre,
            stock_item=item,
            quantity=Decimal('6'),
            status='dispatched',
            allocated_by=self.user,
            dispatched_by=self.user,
        )
        self.client.force_login(manager)
        url = reverse('ecde:resources', args=[self.centre.pk])

        response = self.client.post(url, {
            'action': 'confirm_distribution',
            'allocation_id': allocation.pk,
            'receipt_reference': 'DEL-001',
            'quantity_received': '2',
            'received_on': '2026-10-22',
            'condition': 'partial',
            'notes': 'Four kits were short.',
        })
        self.assertRedirects(response, f'{url}#distributions')
        allocation.refresh_from_db()
        centre_item = CentreInventoryItem.objects.get(
            centre=self.centre,
            name='Learning kits',
            unit='kits',
        )
        self.assertEqual(allocation.status, 'part_received')
        self.assertEqual(centre_item.quantity_on_hand, Decimal('2'))

        response = self.client.post(url, {
            'action': 'confirm_distribution',
            'allocation_id': allocation.pk,
            'receipt_reference': 'DEL-002',
            'quantity_received': '4',
            'received_on': '2026-10-23',
            'condition': 'good',
            'notes': '',
        })
        self.assertRedirects(response, f'{url}#distributions')
        allocation.refresh_from_db()
        centre_item.refresh_from_db()
        self.assertEqual(allocation.status, 'received')
        self.assertEqual(allocation.quantity_received, Decimal('6'))
        self.assertEqual(centre_item.quantity_on_hand, Decimal('6'))
        self.assertEqual(
            CentreInventoryMovement.objects.filter(
                distribution_receipt__allocation=allocation,
                movement_type='in',
            ).count(),
            2,
        )

    def test_distribution_receipt_cannot_exceed_allocation_and_teacher_cannot_confirm(self):
        manager = User.objects.create_user(
            username='receipt-manager',
            email='receipt-manager@example.test',
            password='test-password',
        )
        teacher = User.objects.create_user(
            username='receipt-teacher',
            email='receipt-teacher@example.test',
            password='test-password',
        )
        ECDEMembership.objects.create(
            user=manager,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        ECDEMembership.objects.create(
            user=teacher,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        item = CountyInventoryItem.objects.create(
            county=self.county,
            name='First aid packs',
            unit='packs',
            opening_quantity=Decimal('5'),
        )
        allocation = CentreSupplyAllocation.objects.create(
            centre=self.centre,
            stock_item=item,
            quantity=Decimal('5'),
            status='dispatched',
            allocated_by=self.user,
            dispatched_by=self.user,
        )
        url = reverse('ecde:resources', args=[self.centre.pk])
        self.client.force_login(manager)

        excessive_receipt = self.client.post(url, {
            'action': 'confirm_distribution',
            'allocation_id': allocation.pk,
            'receipt_reference': 'OVER-001',
            'quantity_received': '6',
            'received_on': '2026-10-22',
            'condition': 'good',
            'notes': '',
        })
        self.assertEqual(excessive_receipt.status_code, 200)
        self.assertContains(excessive_receipt, 'cannot exceed the allocated quantity')
        self.assertFalse(CentreSupplyReceipt.objects.filter(allocation=allocation).exists())
        self.assertFalse(CentreInventoryItem.objects.filter(centre=self.centre).exists())

        self.client.force_login(teacher)
        unauthorized = self.client.post(url, {
            'action': 'confirm_distribution',
            'allocation_id': allocation.pk,
            'receipt_reference': 'TEACHER-001',
            'quantity_received': '1',
            'received_on': '2026-10-22',
            'condition': 'good',
            'notes': '',
        })
        self.assertEqual(unauthorized.status_code, 403)
        self.assertFalse(CentreSupplyReceipt.objects.filter(allocation=allocation).exists())

    def test_inventory_stock_out_requires_and_records_usage_purpose(self):
        manager = User.objects.create_user(
            username='inventory-manager',
            email='inventory-manager@example.test',
            password='test-password',
        )
        ECDEMembership.objects.create(
            user=manager,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        item = CentreInventoryItem.objects.create(
            centre=self.centre,
            name='Pencils',
            unit='boxes',
            opening_quantity=Decimal('5'),
        )
        self.client.force_login(manager)
        url = reverse('ecde:resources', args=[self.centre.pk])
        response = self.client.post(url, {
            'action': 'record_inventory_movement',
            'item_id': item.pk,
            'movement_type': 'out',
            'quantity': '2',
            'moved_on': '2026-10-22',
            'reference': 'ISSUE-101',
            'usage_purpose': '',
            'notes': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a purpose for stock issued from inventory.')
        self.assertFalse(CentreInventoryMovement.objects.filter(item=item).exists())

        response = self.client.post(url, {
            'action': 'record_inventory_movement',
            'item_id': item.pk,
            'movement_type': 'out',
            'quantity': '2',
            'moved_on': '2026-10-22',
            'reference': 'ISSUE-102',
            'usage_purpose': 'teaching',
            'notes': '',
        })
        self.assertRedirects(response, f'{url}#inventory')
        movement = CentreInventoryMovement.objects.get(item=item)
        self.assertEqual(movement.usage_purpose, 'teaching')
        self.assertContains(self.client.get(url), 'Teaching and learning')

    def test_resource_page_is_scoped_and_centre_teacher_cannot_manage_resources(self):
        teacher = User.objects.create_user(
            username='resource-teacher',
            email='resource-teacher@example.test',
            password='test-password',
        )
        ECDEMembership.objects.create(
            user=teacher,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        self.client.force_login(teacher)
        url = reverse('ecde:resources', args=[self.centre.pk])

        page_response = self.client.get(url)
        write_response = self.client.post(url, {
            'action': 'create_assessment',
            'assessment_year': '2026',
            'assessed_on': '2026-10-22',
            'summary': 'Teacher should not submit resource plans.',
            'status': 'draft',
        })
        other_centre_response = self.client.get(
            reverse('ecde:resources', args=[self.other_centre.pk]),
        )

        self.assertEqual(page_response.status_code, 200)
        self.assertFalse(page_response.context['can_manage_resources'])
        self.assertEqual(write_response.status_code, 403)
        self.assertEqual(other_centre_response.status_code, 404)
        self.assertFalse(
            CentreNeedsAssessment.objects.filter(centre=self.centre).exists(),
        )

    def test_procurement_rejection_requires_a_reason(self):
        manager = User.objects.create_user(
            username='procurement-manager',
            email='procurement-manager@example.test',
            password='test-password',
        )
        ECDEMembership.objects.create(
            user=manager,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(manager)
        url = reverse('ecde:resources', args=[self.centre.pk])
        self.client.post(url, {
            'action': 'create_procurement',
            'plan': '',
            'title': 'Procurement request requiring review',
            'description': 'Test request.',
            'requested_amount': '500.00',
        })
        request_record = CentreProcurementRequest.objects.get(
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.post(url, {
            'action': 'decide_procurement',
            'procurement_id': request_record.pk,
            'decision': 'rejected',
            'notes': '',
        })

        self.assertEqual(response.status_code, 200)
        request_record.refresh_from_db()
        self.assertEqual(request_record.status, 'pending')
        self.assertContains(response, 'A reason is required')

    def test_centre_directory_uses_cards_when_fewer_than_five(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('ecde:manage_centres'))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['use_list_view'])
        self.assertContains(response, 'class="card h-100"')
        self.assertNotContains(response, '<table')

    def test_centre_directory_uses_list_when_five_or_more_centres(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        for index in range(3):
            ECDECentre.objects.create(
                ward=self.ward,
                name=f'Additional Centre {index}',
                code=f'ADDITIONAL-{index}',
            )
        self.client.force_login(self.user)

        response = self.client.get(reverse('ecde:manage_centres'))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['use_list_view'])
        self.assertContains(response, '<table')
        self.assertNotContains(response, 'class="card h-100"')

    def test_county_admin_cannot_create_subcounty_in_another_county(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:manage_centres'),
            {
                'action': 'create_subcounty',
                'county': self.other_centre.county.pk,
                'name': 'Unauthorized Sub-county',
                'code': '998-2',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            SubCounty.objects.filter(name='Unauthorized Sub-county').exists(),
        )

    def test_county_admin_can_assign_teacher_to_own_centre(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        teacher = User.objects.create_user(
            username='teacher',
            email='teacher@example.test',
            password='test-password',
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:manage_staff'),
            {
                'action': 'create_membership',
                'user': teacher.pk,
                'role': ECDEMembership.ROLE_ECDE_TEACHER,
                'centre': self.centre.pk,
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('ecde:manage_staff'))
        self.assertTrue(
            ECDEMembership.objects.filter(
                user=teacher,
                role=ECDEMembership.ROLE_ECDE_TEACHER,
                centre=self.centre,
                is_active=True,
            ).exists(),
        )

    def test_only_superuser_can_create_county(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:manage_staff'),
            {
                'action': 'create_county',
                'name': 'Unauthorized County',
                'code': '997',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(County.objects.filter(code='997').exists())

    def test_membership_rejects_scope_at_wrong_hierarchy_level(self):
        membership = ECDEMembership(
            user=self.user,
            role=ECDEMembership.ROLE_WARD_COORDINATOR,
            county=self.county,
            ward=self.ward,
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_user_cannot_open_a_centre_outside_assigned_scope(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('ecde:children', args=[self.other_centre.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_county_officer_can_view_but_not_create_centre_records(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:children', args=[self.centre.pk]),
            {
                'first_name': 'Nia',
                'last_name': 'Wanjiku',
                'date_of_birth': '2021-06-12',
                'gender': 'F',
                'level': 'PP1',
                'guardian_name': 'Wanjiku Parent',
                'guardian_phone': '0712345678',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ECDEChild.objects.filter(first_name='Nia').exists())

    def test_centre_manager_can_enrol_a_child(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:children', args=[self.centre.pk]),
            {
                'admission_number': 'PP-001',
                'first_name': 'Nia',
                'last_name': 'Wanjiku',
                'date_of_birth': '2021-06-12',
                'gender': 'F',
                'level': 'PP1',
                'guardian_name': 'Wanjiku Parent',
                'guardian_phone': '0712345678',
            },
        )

        self.assertRedirects(
            response, reverse('ecde:children', args=[self.centre.pk]),
        )
        enrolled = ECDEChild.objects.get(admission_number='PP-001')
        self.assertEqual(enrolled.centre, self.centre)
        self.assertEqual(enrolled.enrolled_by, self.user)
        self.assertEqual(enrolled.status, ECDEChild.STATUS_ENROLLED)
        self.assertTrue(
            ECDEAuditEvent.objects.filter(
                action='create', details__child_id=enrolled.pk,
            ).exists(),
        )

    def test_learner_register_can_search_and_filter(self):
        second_child = ECDEChild.objects.create(
            centre=self.centre,
            first_name='Nia',
            last_name='Kamau',
            date_of_birth=date(2021, 6, 12),
            gender='F',
            level='PP2',
            guardian_name='Kamau Parent',
            guardian_phone='0799999999',
            enrolled_by=self.user,
        )
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('ecde:children', args=[self.centre.pk]),
            {'q': 'Nia', 'level': 'PP2', 'status': 'enrolled'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['children'].object_list), [second_child])
        self.assertContains(response, reverse(
            'ecde:child_detail', args=[self.centre.pk, second_child.pk],
        ))
        self.assertNotContains(response, 'Amani Otieno')

    def test_centre_manager_can_view_and_update_learner_profile(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_CENTRE_MANAGER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('ecde:child_detail', args=[self.centre.pk, self.child.pk]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Learner details')
        self.assertContains(response, 'Recent attendance')
        self.assertContains(response, 'Recent CBC observations')

        response = self.client.post(
            reverse('ecde:child_detail', args=[self.centre.pk, self.child.pk]),
            {
                'learner_number': 'COUNTY-001',
                'admission_number': '',
                'first_name': 'Amani',
                'middle_names': 'Wanjiru',
                'last_name': 'Otieno',
                'date_of_birth': '2021-02-01',
                'gender': 'F',
                'level': 'PP1',
                'guardian_name': 'Guardian Otieno',
                'guardian_relationship': '',
                'guardian_phone': '0712345678',
                'alternate_guardian_name': '',
                'alternate_guardian_phone': '',
                'guardian_email': '',
                'home_village': 'Kibera',
            },
        )

        self.assertRedirects(
            response,
            reverse('ecde:child_detail', args=[self.centre.pk, self.child.pk]),
        )
        self.child.refresh_from_db()
        self.assertEqual(self.child.middle_names, 'Wanjiru')
        self.assertEqual(self.child.learner_number, 'COUNTY-001')
        event = ECDEAuditEvent.objects.get(
            action='update',
            details__child_id=self.child.pk,
        )
        self.assertIn('middle_names', event.details['changed_fields'])
        self.assertNotIn('Guardian Otieno', str(event.details))

    def test_child_detail_is_scoped_to_accessible_centres(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('ecde:child_detail', args=[self.other_centre.pk, self.child.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_county_admin_can_complete_or_withdraw_child_with_exit_details(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:children', args=[self.centre.pk]),
            {
                'action': 'update_lifecycle',
                'child_id': self.child.pk,
                'status': 'withdrawn',
                'exit_date': self.child.enrollment_date.isoformat(),
                'exit_reason': 'Family relocated',
            },
        )

        self.assertRedirects(
            response, reverse('ecde:children', args=[self.centre.pk]),
        )
        self.child.refresh_from_db()
        self.assertEqual(self.child.status, ECDEChild.STATUS_WITHDRAWN)
        self.assertFalse(self.child.is_active)
        self.assertTrue(
            ECDEAuditEvent.objects.filter(
                action='status', details__child_id=self.child.pk,
            ).exists(),
        )

    def test_withdrawal_requires_date_and_reason(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:children', args=[self.centre.pk]),
            {
                'action': 'update_lifecycle',
                'child_id': self.child.pk,
                'status': 'withdrawn',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.status, ECDEChild.STATUS_ENROLLED)
        self.assertTrue(response.context['lifecycle_errors'])

    def test_county_admin_can_transfer_child_between_centres(self):
        original_enrollment_date = self.child.enrollment_date
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:children', args=[self.centre.pk]),
            {
                'action': 'transfer_child',
                'child': self.child.pk,
                'to_centre': self.sibling_centre.pk,
                'to_level': 'PP2',
                'transfer_date': self.child.enrollment_date.isoformat(),
                'reason': 'Family moved within the county',
            },
        )

        self.assertRedirects(
            response, reverse('ecde:children', args=[self.centre.pk]),
        )
        self.child.refresh_from_db()
        transfer = ECDEChildTransfer.objects.get(child=self.child)
        self.assertEqual(self.child.centre, self.sibling_centre)
        self.assertEqual(self.child.level, 'PP2')
        self.assertEqual(self.child.enrollment_date, original_enrollment_date)
        self.assertEqual(transfer.from_level, 'PP1')
        self.assertEqual(transfer.to_level, 'PP2')
        event = ECDEAuditEvent.objects.get(action='transfer')
        self.assertEqual(event.centre, self.centre)
        self.assertEqual(event.related_centre, self.sibling_centre)

    def test_county_admin_cannot_transfer_child_to_another_county(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:children', args=[self.centre.pk]),
            {
                'action': 'transfer_child',
                'child': self.child.pk,
                'to_centre': self.other_centre.pk,
                'to_level': 'PP2',
                'transfer_date': self.child.enrollment_date.isoformat(),
                'reason': 'Moved',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ECDEChildTransfer.objects.exists())
        self.child.refresh_from_db()
        self.assertEqual(self.child.centre, self.centre)

    def test_teacher_assignment_creates_personnel_profile(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        teacher = User.objects.create_user(
            username='profile-teacher',
            email='profile-teacher@example.test',
            password='test-password',
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:manage_staff'),
            {
                'action': 'create_membership',
                'user': teacher.pk,
                'role': ECDEMembership.ROLE_ECDE_TEACHER,
                'centre': self.centre.pk,
                'is_active': 'on',
                'staff_number': 'STAFF-01',
                'tsc_registration_number': 'TSC-123',
                'highest_qualification': 'ECDE Diploma',
                'employment_type': 'permanent',
                'phone': '0712345678',
            },
        )

        self.assertRedirects(response, reverse('ecde:manage_staff'))
        profile = ECDETeacherProfile.objects.get(
            membership__user=teacher,
        )
        self.assertEqual(profile.staff_number, 'STAFF-01')
        self.assertEqual(profile.tsc_registration_number, 'TSC-123')

    def test_county_admin_can_update_centre_operational_details(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:manage_centres'),
            {
                'action': 'update_centre',
                'object_id': self.centre.pk,
                f'centre-{self.centre.pk}-ward': self.ward.pk,
                f'centre-{self.centre.pk}-name': self.centre.name,
                f'centre-{self.centre.pk}-code': self.centre.code,
                f'centre-{self.centre.pk}-registration_number': 'REG-01',
                f'centre-{self.centre.pk}-registration_status': 'registered',
                f'centre-{self.centre.pk}-ownership': 'public',
                f'centre-{self.centre.pk}-established_date': '2018-01-01',
                f'centre-{self.centre.pk}-capacity': '80',
                f'centre-{self.centre.pk}-contact_phone': '0712345678',
                f'centre-{self.centre.pk}-contact_email': 'centre@example.test',
                f'centre-{self.centre.pk}-address': 'Main road',
                f'centre-{self.centre.pk}-classroom_count': '3',
                f'centre-{self.centre.pk}-toilet_count': '4',
                f'centre-{self.centre.pk}-water_source': 'borehole',
                f'centre-{self.centre.pk}-electricity': 'yes',
                f'centre-{self.centre.pk}-kitchen': 'yes',
                f'centre-{self.centre.pk}-playground': 'no',
                f'centre-{self.centre.pk}-disability_access': 'unknown',
                f'centre-{self.centre.pk}-facility_condition': 'needs_repair',
                f'centre-{self.centre.pk}-meals_program': 'yes',
                f'centre-{self.centre.pk}-learning_materials': 'no',
                f'centre-{self.centre.pk}-staffing_adequate': 'no',
                f'centre-{self.centre.pk}-first_aid_ready': 'yes',
                f'centre-{self.centre.pk}-safeguarding_procedures': 'yes',
            },
        )

        self.assertRedirects(response, reverse('ecde:manage_centres'))
        self.centre.refresh_from_db()
        self.assertEqual(self.centre.capacity, 80)
        self.assertEqual(self.centre.ownership, 'public')
        self.assertEqual(self.centre.classroom_count, 3)
        self.assertEqual(self.centre.water_source, 'borehole')
        self.assertEqual(self.centre.meals_program, 'yes')
        self.assertEqual(self.centre.learning_materials, 'no')
        self.assertEqual(self.centre.staffing_adequate, 'no')
        self.assertEqual(self.centre.first_aid_ready, 'yes')
        self.assertEqual(self.centre.safeguarding_procedures, 'yes')
        event = ECDEAuditEvent.objects.get(
            action='update',
            summary__contains='Operational details',
        )
        self.assertIn('capacity', event.details['changed_fields'])

    def test_county_admin_can_update_teacher_personnel_profile(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        teacher = User.objects.create_user(
            username='profile-update-teacher',
            email='profile-update-teacher@example.test',
            password='test-password',
        )
        membership = ECDEMembership.objects.create(
            user=teacher,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:manage_staff'),
            {
                'action': 'update_teacher_profile',
                'object_id': membership.pk,
                f'teacher-{membership.pk}-staff_number': 'STAFF-22',
                f'teacher-{membership.pk}-tsc_registration_number': 'TSC-222',
                f'teacher-{membership.pk}-highest_qualification': 'Diploma',
                f'teacher-{membership.pk}-employment_type': 'contract',
                f'teacher-{membership.pk}-phone': '0722222222',
                f'teacher-{membership.pk}-date_joined': '',
                f'teacher-{membership.pk}-notes': 'Verified by county officer',
            },
        )

        self.assertRedirects(response, reverse('ecde:manage_staff'))
        profile = ECDETeacherProfile.objects.get(membership=membership)
        self.assertEqual(profile.staff_number, 'STAFF-22')
        self.assertEqual(profile.employment_type, 'contract')
        self.assertTrue(
            ECDEAuditEvent.objects.filter(
                action='update',
                summary='An ECDE teacher personnel profile was updated.',
            ).exists(),
        )

    def test_audit_events_are_scoped_and_immutable(self):
        own_event = record_audit_event(
            actor=self.user,
            action='create',
            summary='Own centre event',
            centre=self.centre,
        )
        record_audit_event(
            actor=self.user,
            action='create',
            summary='Other county event',
            centre=self.other_centre,
        )
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_COUNTY_ADMIN,
            county=self.county,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse('ecde:audit_log'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Own centre event')
        self.assertNotContains(response, 'Other county event')
        own_event.summary = 'Altered'
        with self.assertRaises(ValidationError):
            own_event.save()

    def test_teacher_can_record_attendance_for_own_centre_child(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:attendance', args=[self.centre.pk]),
            {
                'child': self.child.pk,
                'date': '2026-10-20',
                'status': 'present',
                'notes': '',
            },
        )

        self.assertRedirects(
            response, reverse('ecde:attendance', args=[self.centre.pk]),
        )
        record = AttendanceRecord.objects.get(child=self.child)
        self.assertEqual(record.centre, self.centre)
        self.assertEqual(record.recorded_by, self.user)

    def test_teacher_can_record_cbc_observation_without_exam_marks(self):
        ECDEMembership.objects.create(
            user=self.user,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('ecde:progress', args=[self.centre.pk]),
            {
                'child': self.child.pk,
                'learning_area': 'language',
                'competency': 'Communicates a familiar experience',
                'progress': 'developing',
                'observation': 'Described an event using several connected ideas.',
                'evidence_date': '2026-10-20',
            },
        )

        self.assertRedirects(
            response, reverse('ecde:progress', args=[self.centre.pk]),
        )
        record = CBCProgressRecord.objects.get(child=self.child)
        self.assertEqual(record.centre, self.centre)
        self.assertEqual(record.recorded_by, self.user)
