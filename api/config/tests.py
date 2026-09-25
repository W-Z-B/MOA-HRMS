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


def test_openapi_schema_is_served():
    response = Client().get("/api/schema/")
    assert response.status_code == 200
