from django.test import TestCase
from django.urls import reverse

from django_school_management.accounts.models import User
from django_school_management.ecde.models import (
    County, ECDECentre, ECDEMembership, ECDETeacherProfile, SubCounty, Ward,
)


class TeacherDirectoryTests(TestCase):
    def setUp(self):
        county = County.objects.create(name='Teacher Test County', code='TC')
        subcounty = SubCounty.objects.create(
            county=county, name='Teacher Test Sub-county', code='TC-1',
        )
        ward = Ward.objects.create(
            subcounty=subcounty, name='Teacher Test Ward', code='TC-1-1',
        )
        self.centre = ECDECentre.objects.create(
            ward=ward, name='Teacher Test Centre', code='TC-1-1-1',
        )
        self.teacher_user = User.objects.create_user(
            username='ecde-teacher',
            email='ecde-teacher@example.test',
            first_name='Wanjiku',
            last_name='Muthoni',
            password='test-password',
        )
        ECDEMembership.objects.create(
            user=self.teacher_user,
            role=ECDEMembership.ROLE_ECDE_TEACHER,
            centre=self.centre,
        )

    def test_ecde_teacher_can_view_staff_directory_and_own_assignment(self):
        self.client.force_login(self.teacher_user)

        response = self.client.get(reverse('teachers:all_teacher'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Wanjiku Muthoni')
        self.assertContains(response, 'ECDE Teacher')
        self.assertContains(response, self.centre.name)
        self.assertNotContains(response, 'Add Teacher')

    def test_ecde_teacher_profile_details_appear_in_directory(self):
        membership = self.teacher_user.ecde_memberships.get()
        ECDETeacherProfile.objects.create(
            membership=membership,
            staff_number='ECDE-009',
            tsc_registration_number='TSC-007',
            highest_qualification='ECDE Certificate',
            phone='0712345678',
        )
        self.client.force_login(self.teacher_user)

        response = self.client.get(reverse('teachers:all_teacher'))

        self.assertContains(response, 'ECDE Certificate')
        self.assertContains(response, 'ECDE-009')
        self.assertContains(response, 'TSC-007')
        self.assertContains(response, '0712345678')

    def test_unassigned_user_cannot_view_teacher_directory(self):
        user = User.objects.create_user(
            username='unassigned',
            email='unassigned@example.test',
            password='test-password',
        )
        self.client.force_login(user)

        response = self.client.get(reverse('teachers:all_teacher'))

        self.assertEqual(response.status_code, 403)
