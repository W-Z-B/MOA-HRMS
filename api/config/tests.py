import pytest
from django.conf import settings
from django.test import Client

requires_postgres = pytest.mark.skipif(
    "postgresql" not in settings.DATABASES["default"]["ENGINE"],
    reason="job-queue migrations need PostgreSQL; run tests in the Compose stack or CI",
)


@requires_postgres
@pytest.mark.django_db
def test_health_endpoint_reports_ok():
    response = Client().get("/api/health/")
    assert response.status_code == 200
    assert response.json()["database"] is True


@pytest.mark.django_db
def test_api_documentation_is_for_signed_in_people_unless_made_public(settings, hr_officer):
    settings.API_DOCS_PUBLIC = False
    refused = Client().get("/api/schema/")
    assert refused.status_code == 403 and b"not_authenticated" in refused.content  # rendered as OpenAPI
    signed_in = Client()
    signed_in.force_login(hr_officer)
    assert signed_in.get("/api/schema/").status_code == 200
    assert signed_in.get("/api/docs/").status_code == 200

    settings.API_DOCS_PUBLIC = True  # development default
    assert Client().get("/api/schema/").status_code == 200


@pytest.mark.django_db
def test_every_refusal_carries_a_code(hr_manager, make_user, campus):
    """The framework's own refusals carry a code as well as a sentence (core.exceptions)."""
    anonymous = Client().get("/api/v1/employees/")
    assert anonymous.status_code == 403 and anonymous.json()["code"] == "not_authenticated"

    privileged = Client()
    privileged.force_login(hr_manager)  # no authenticator code yet
    assert privileged.get("/api/v1/org/campuses/").json()["code"] == "mfa_required"

    plain = Client()
    plain.force_login(make_user("plain.employee", "employee", campus=campus))
    refused = plain.get("/api/v1/employees/")
    assert refused.status_code == 403 and refused.json()["code"] == "permission_denied"

    missing = Client()
    missing.force_login(hr_manager)
    session = missing.session
    session["mfa_verified"] = True
    session.save()
    assert missing.get("/api/v1/employees/999999/").json()["code"] == "not_found"
