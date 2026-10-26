from types import SimpleNamespace

from django.test import TestCase

from django_school_management.academics.models import Semester, Subject
from .models import Curriculum, CurriculumLevel, CurriculumSubject
from .helpers import load_subjects_from_curriculum
from django_school_management.institute.forms.onboarding_forms import (
    LoadSubjectsFromCurriculumForm,
    OnboardingStep1Form,
)
from django_school_management.institute.models import InstituteProfile


class KenyaPreprimaryCurriculumTests(TestCase):
    def test_new_onboarding_defaults_to_a_kenyan_cbc_school(self):
        form = OnboardingStep1Form()

        self.assertEqual(
            form.fields['institute_type'].choices,
            [
                ('', '---------'),
                ('school', 'Kenyan CBC School (Pre-Primary)'),
            ],
        )
        self.assertEqual(form.fields['institute_type'].initial, 'school')
        self.assertEqual(form.fields['country'].initial, 'KE')

    def test_kenyan_onboarding_only_offers_kenyan_curricula(self):
        curriculum = Curriculum.objects.get(code='KE-CBC-PP')
        form = LoadSubjectsFromCurriculumForm(
            institute=SimpleNamespace(
                institute_type='school',
                country='KE',
            ),
        )

        self.assertEqual(
            list(form.fields['curriculum'].queryset),
            [curriculum],
        )

    def test_pp1_and_pp2_have_the_five_cbc_learning_areas(self):
        curriculum = Curriculum.objects.get(code='KE-CBC-PP')

        self.assertEqual(
            list(curriculum.levels.values_list('name', flat=True)),
            ['PP1', 'PP2'],
        )

        expected_areas = {
            'Language Activities',
            'Mathematical Activities',
            'Environmental Activities',
            'Psychomotor and Creative Activities',
            'Religious Education Activities',
        }
        for level in CurriculumLevel.objects.filter(curriculum=curriculum):
            with self.subTest(level=level.name):
                subjects = CurriculumSubject.objects.filter(
                    curriculum=curriculum,
                    level=level,
                ).select_related('subject_template')
                self.assertEqual(
                    {item.subject_template.name for item in subjects},
                    expected_areas,
                )
                self.assertTrue(all(item.is_compulsory for item in subjects))
                self.assertTrue(all(
                    item.subject_template.default_theory_marks == 0
                    and item.subject_template.default_practical_marks == 0
                    for item in subjects
                ))

    def test_onboarding_offers_pp1_and_pp2_as_individual_class_choices(self):
        curriculum = Curriculum.objects.get(code='KE-CBC-PP')
        form = LoadSubjectsFromCurriculumForm(
            data={
                'curriculum': str(curriculum.pk),
                'class_range': ['1', '2'],
            },
            institute=SimpleNamespace(institute_type='school'),
        )

        self.assertEqual(
            list(form.fields['class_range'].choices),
            [('1', 'PP1'), ('2', 'PP2')],
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_class_numbers(), [1, 2])

    def test_onboarding_rejects_levels_not_in_selected_curriculum(self):
        curriculum = Curriculum.objects.get(code='KE-CBC-PP')
        form = LoadSubjectsFromCurriculumForm(
            data={
                'curriculum': str(curriculum.pk),
                'class_range': ['3'],
            },
            institute=SimpleNamespace(institute_type='school'),
        )

        self.assertFalse(form.is_valid())
        self.assertIn('class_range', form.errors)

    def test_loading_preprimary_creates_only_selected_named_classes(self):
        curriculum = Curriculum.objects.get(code='KE-CBC-PP')
        institute = InstituteProfile.objects.create(
            name='Test Pre-Primary School',
            country='KE',
        )

        result = load_subjects_from_curriculum(
            institute,
            curriculum,
            [1, 2],
            created_by=None,
        )

        self.assertEqual(result['semesters_created'], 2)
        self.assertEqual(result['subjects_created'], 5)
        self.assertEqual(result['subject_groups_created'], 0)
        self.assertEqual(
            list(Semester.objects.order_by('number').values_list(
                'display_name', flat=True
            )),
            ['PP1', 'PP2'],
        )
        self.assertEqual(Subject.objects.count(), 5)

    def test_loading_only_pp1_does_not_create_pp2(self):
        curriculum = Curriculum.objects.get(code='KE-CBC-PP')
        institute = InstituteProfile.objects.create(
            name='Test PP1 School',
            country='KE',
        )

        load_subjects_from_curriculum(
            institute,
            curriculum,
            [1],
            created_by=None,
        )

        self.assertEqual(
            list(Semester.objects.values_list('display_name', flat=True)),
            ['PP1'],
        )
