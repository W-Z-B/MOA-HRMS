"""What the LMS needs from the HRMS: who supervises whom (LMS decision D13) and required training by post
(item 5.24, LMS ADR 0019)."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from audit.models import AuditLog
from integration.models import ServiceClient

STAFF = "/api/v1/integration/staff/"
REQUIREMENTS = "/api/v1/integration/training-requirements/"
SENSITIVE = {"nis_no", "tin", "national_id", "date_of_birth", "address"}


def _service(*scopes: str, name: str = "lms") -> APIClient:
    _, key = ServiceClient.issue(name, list(scopes))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Api-Key {key}")
    return client


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def chart(campus, unit):
    """Agriculture (headed by E0002) above Livestock (no head); E0001 holds a Livestock post."""
    from org.models import OrgUnit, Position
    from people.models import Assignment, Employee

    agriculture = OrgUnit.objects.create(code="AGR", name="Department of Agriculture", campus=campus)
    unit.parent = agriculture
    unit.save()
    head_post = Position.objects.create(
        number="AGR-001",
        title="Head of Department",
        grade=Position.objects.first().grade,
        org_unit=agriculture,
    )

    def person(number, first, post):
        staff = Employee.objects.create(
            employee_no=number,
            first_name=first,
            last_name="Demo",
            date_of_birth=date(1985, 1, 1),
            campus=campus,
        )
        Assignment.objects.create(
            employee=staff, position=post, appointment_type="permanent", start_date=date(2026, 1, 1)
        )
        return staff

    staff = {
        "E0001": person("E0001", "Asha", Position.objects.get(number="LIV-001")),
        "E0002": person("E0002", "Michael", head_post),
        "E0003": person("E0003", "Ravi", Position.objects.get(number="LIV-002")),
    }
    agriculture.head = staff["E0002"]
    agriculture.save()
    return {"agriculture": agriculture, "livestock": unit, **staff}


def _supervisors(client) -> dict[str, str | None]:
    rows = client.get(STAFF).json()["results"]
    for row in rows:
        assert not SENSITIVE & set(row)
    return {row["employee_no"]: row["supervisor_employee_no"] for row in rows}


@pytest.mark.django_db
def test_the_directory_names_each_persons_supervisor_from_the_unit_heads(chart):
    from people.models import Employee

    lms = _service("staff:read")
    # Livestock has no head, so its staff report to the head of Agriculture above; nobody has an account,
    # and that does not matter to the other systems. The head of Agriculture has nobody above.
    assert _supervisors(lms) == {"E0001": "E0002", "E0002": None, "E0003": "E0002"}

    # A head of their own unit reports to the head above; the others to them.
    chart["livestock"].head = chart["E0003"]
    chart["livestock"].save()
    assert _supervisors(lms) == {"E0001": "E0003", "E0002": None, "E0003": "E0002"}

    # A head who has left is passed over.
    Employee.objects.filter(pk=chart["E0003"].pk).update(status=Employee.Status.SEPARATED)
    assert _supervisors(lms)["E0001"] == "E0002"


@pytest.mark.django_db
def test_a_restricted_appointment_holds_back_the_reporting_line(chart):
    from privacy.models import Restriction

    Restriction.objects.create(employee=chart["E0001"], part="appointment", ground="contested")
    row = next(r for r in _service("staff:read").get(STAFF).json()["results"] if r["employee_no"] == "E0001")
    assert row["supervisor_employee_no"] is None and row["unit_code"] is None
    assert "appointment" in row["restricted"]


@pytest.mark.django_db
def test_the_directory_reads_the_chart_once_per_page(chart, campus):
    """Finding each supervisor walks the chart in memory: more staff cost only the queries each row
    already needed for its post and unit (assignment, post, unit), not one more per step up the chart."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from org.models import Position
    from people.models import Assignment, Employee

    lms = _service("staff:read")

    def queries() -> int:
        with CaptureQueriesContext(connection) as captured:
            assert lms.get(STAFF).status_code == 200
        return len(captured)

    before = queries()
    for number in ("E0004", "E0005"):
        extra = Employee.objects.create(
            employee_no=number,
            first_name="Extra",
            last_name="Demo",
            date_of_birth=date(1990, 1, 1),
            campus=campus,
        )
        Assignment.objects.create(
            employee=extra,
            position=Position.objects.create(
                number=f"LIV-{number}",
                title="Farm Hand",
                grade=Position.objects.first().grade,
                org_unit=chart["livestock"],
            ),
            appointment_type="permanent",
            start_date=date(2026, 1, 1),
        )
    assert queries() - before <= 2 * 3


@pytest.fixture
def requirements(chart, campus):
    from training.models import TrainingRequirement

    first_aid = TrainingRequirement.objects.create(
        course_code="SD-FA-01", title="First aid at work", campus=campus, due_days=60, renewal_months=24
    )
    TrainingRequirement.objects.create(
        title="Animal handling", post_title="Livestock Instructor", org_unit=chart["livestock"]
    )
    TrainingRequirement.objects.create(title="Retired course", is_active=False)
    return first_aid


@pytest.mark.django_db
def test_the_lms_reads_the_required_training(requirements):
    page = _service("training:read").get(REQUIREMENTS).json()
    assert page["count"] == 2
    first, second = page["results"]
    assert {k: v for k, v in first.items() if k != "updated_at"} == {
        "id": requirements.id,
        "course_code": "SD-FA-01",
        "title": "First aid at work",
        "post_title": None,
        "unit_code": None,
        "campus_code": "MRP",
        "due_days": 60,
        "renewal_months": 24,
    }
    assert (second["post_title"], second["unit_code"], second["course_code"]) == (
        "Livestock Instructor",
        "LIV",
        None,
    )
    assert second["renewal_months"] is None and second["due_days"] == 30
    assert AuditLog.objects.filter(action="integration:training_requirements.read").exists()


@pytest.mark.django_db
def test_required_training_refuses_other_keys_and_people(requirements, hr_manager):
    assert APIClient().get(REQUIREMENTS).status_code in (401, 403)
    assert _service("training:write", "staff:read").get(REQUIREMENTS).status_code == 403
    assert _signed_in(hr_manager).get(REQUIREMENTS).status_code in (401, 403)


@pytest.mark.django_db
def test_the_hr_manager_keeps_the_required_training(chart, hr_manager, hr_officer, campus):
    from training.models import TrainingRequirement

    manager = _signed_in(hr_manager)
    body = {"title": "Safe use of tractors", "post_title": "farm hand", "org_unit": chart["livestock"].id}
    created = manager.post("/api/v1/training/requirements/", body, format="json")
    assert created.status_code == 201, created.content
    assert created.json()["applies_to"] == "post farm hand, unit LIV"
    requirement = TrainingRequirement.objects.get(title="Safe use of tractors")
    assert AuditLog.objects.filter(entity="training.trainingrequirement", action="create").exists()

    # A title that names no post, a unit on another campus and a renewal of nothing are refused.
    from org.models import Campus

    esq = Campus.objects.get(code="ESQ")
    for wrong in (
        {**body, "post_title": "Astronaut"},
        {**body, "campus": esq.id},
        {**body, "renewal_months": 0},
    ):
        assert manager.post("/api/v1/training/requirements/", wrong, format="json").status_code == 400

    # Retired by switching it off; never deleted.
    url = f"/api/v1/training/requirements/{requirement.id}/"
    assert manager.patch(url, {"is_active": False}, format="json").status_code == 200
    assert manager.delete(url).status_code == 405
    assert _signed_in(hr_manager).get("/api/v1/training/requirements/", {"active": "1"}).json()["count"] == 0

    # HR officers read the list but do not change it.
    officer = _signed_in(hr_officer)
    assert officer.get("/api/v1/training/requirements/").status_code == 200
    assert officer.post("/api/v1/training/requirements/", body, format="json").status_code == 403
    assert TrainingRequirement.objects.count() == 1


def test_training_read_is_a_known_scope():
    from integration.management.commands.create_service_client import KNOWN_SCOPES

    assert {"training:read", "training:write"} <= KNOWN_SCOPES
