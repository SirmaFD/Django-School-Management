from django.core.management.base import BaseCommand, CommandError

from django_school_management.ecde.models import County, ECDECentre, SubCounty, Ward


DEMO_AREAS = (
    ("Aldai", "Aldai Demo Ward"),
    ("Chesumei", "Chesumei Demo Ward"),
    ("Emgwen", "Emgwen Demo Ward"),
    ("Mosop", "Mosop Demo Ward"),
    ("Nandi Hills", "Nandi Hills Demo Ward"),
    ("Tinderet", "Tinderet Demo Ward"),
)


class Command(BaseCommand):
    help = "Create clearly labeled synthetic ECDE centre data for Nandi County."

    def handle(self, *args, **options):
        county, _ = County.objects.get_or_create(
            code="029",
            defaults={"name": "Nandi"},
        )
        if county.name != "Nandi":
            raise CommandError(
                f"County code 029 belongs to {county.name!r}, not Nandi."
            )

        created_subcounties = 0
        created_wards = 0
        created_centres = 0

        for index, (area_name, ward_name) in enumerate(DEMO_AREAS, start=1):
            subcounty, was_created = SubCounty.objects.get_or_create(
                county=county,
                code=f"NDI-DEMO-SC-{index:02}",
                defaults={"name": f"Demo {area_name}"},
            )
            created_subcounties += was_created
            if subcounty.name != f"Demo {area_name}":
                raise CommandError(
                    f"Demo sub-county code {subcounty.code} is already used "
                    f"by {subcounty.name!r}."
                )

            ward, was_created = Ward.objects.get_or_create(
                subcounty=subcounty,
                code=f"NDI-DEMO-WD-{index:02}",
                defaults={"name": ward_name},
            )
            created_wards += was_created
            if ward.name != ward_name:
                raise CommandError(
                    f"Demo ward code {ward.code} is already used by "
                    f"{ward.name!r}."
                )

            for centre_number in (1, 2):
                centre_code = f"NDI-DEMO-{index:02}-{centre_number:02}"
                _, was_created = ECDECentre.objects.get_or_create(
                    ward=ward,
                    code=centre_code,
                    defaults={
                        "name": (
                            f"DEMO - {area_name} ECDE Centre "
                            f"{centre_number:02}"
                        ),
                        "registration_status": "unknown",
                        "ownership": "community",
                        "capacity": 40 + centre_number * 10,
                        "classroom_count": centre_number,
                        "toilet_count": centre_number,
                        "water_source": "unknown",
                        "electricity": "unknown",
                        "kitchen": "unknown",
                        "playground": "yes",
                        "disability_access": "unknown",
                        "facility_condition": "unknown",
                        "address": f"Synthetic demo location in {ward_name}",
                    },
                )
                created_centres += was_created

        self.stdout.write(
            self.style.SUCCESS(
                "Nandi ECDE demo data ready: "
                f"{created_subcounties} sub-counties, "
                f"{created_wards} wards, "
                f"{created_centres} centres created. "
                "Existing demo records were left unchanged."
            )
        )
