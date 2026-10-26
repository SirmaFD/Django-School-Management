from django.db import migrations


LEARNING_AREAS = [
    ('KE_PP_LANGUAGE', 'Language Activities', 1),
    ('KE_PP_MATHEMATICS', 'Mathematical Activities', 2),
    ('KE_PP_ENVIRONMENT', 'Environmental Activities', 3),
    ('KE_PP_PSYCHOMOTOR_CREATIVE', 'Psychomotor and Creative Activities', 4),
    ('KE_PP_RELIGIOUS_EDUCATION', 'Religious Education Activities', 5),
]


def seed_kenya_preprimary(apps, schema_editor):
    Curriculum = apps.get_model('curriculum', 'Curriculum')
    CurriculumLevel = apps.get_model('curriculum', 'CurriculumLevel')
    SubjectTemplate = apps.get_model('curriculum', 'SubjectTemplate')
    CurriculumSubject = apps.get_model('curriculum', 'CurriculumSubject')

    curriculum, _ = Curriculum.objects.get_or_create(
        code='KE-CBC-PP',
        defaults={
            'name': 'Kenya CBC Pre-Primary',
            'description': (
                'Kenyan Competency-Based Curriculum for Pre-Primary 1 and 2.'
            ),
            'institute_type': 'school',
            'is_active': True,
            'display_order': 30,
        },
    )

    for level_number, name in ((1, 'PP1'), (2, 'PP2')):
        level, _ = CurriculumLevel.objects.get_or_create(
            curriculum=curriculum,
            level_number=level_number,
            defaults={
                'name': name,
                'semester_number': level_number,
                'streams_applicable': False,
                'display_order': level_number,
            },
        )

        for code, area_name, display_order in LEARNING_AREAS:
            template, _ = SubjectTemplate.objects.get_or_create(
                code=code,
                defaults={
                    'name': area_name,
                    'description': (
                        'CBC learning area; assess learner progress through '
                        'observations and evidence, not aggregate exam marks.'
                    ),
                    'default_theory_marks': 0,
                    'default_practical_marks': 0,
                    'is_elective': False,
                    'display_order': display_order,
                },
            )
            CurriculumSubject.objects.get_or_create(
                curriculum=curriculum,
                level=level,
                stream=None,
                subject_template=template,
                defaults={
                    'is_compulsory': True,
                    'display_order': display_order,
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ('curriculum', '0003_seed_bd_subjects_school_madrasah'),
    ]

    operations = [
        migrations.RunPython(seed_kenya_preprimary, migrations.RunPython.noop),
    ]
