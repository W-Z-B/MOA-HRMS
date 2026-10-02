"""Item 1.19: letter templates, and the letters issued from them into the staff file."""

import hashlib
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from letters import markup


def _signed_in(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


@pytest.fixture
def placed(employee, unit, make_user, campus):
    """Asha in post LIV-001 since 2019, with a contract, an address, and an account of her own."""
    from org.models import Position
    from people.models import Assignment, Contract

    employee.address = "Lot 5, Mon Repos,\nEast Coast Demerara"
    employee.user = make_user("asha.persaud", "employee", campus=campus)
    employee.save()
    assignment = Assignment.objects.create(
        employee=employee,
        position=Position.objects.get(number="LIV-001"),
        appointment_type="permanent",
        start_date=date(2019, 9, 2),
        probation_end=date(2020, 3, 1),
    )
    Contract.objects.create(
        assignment=assignment, contract_type="open_ended", hours_per_week=Decimal("40"), notice_period_days=30
    )
    return employee


def _template(code):
    from letters.models import LetterTemplate

    return LetterTemplate.objects.filter(code=code).order_by("-version").first()


def _issue(client, employee, code="job_letter", answers=None):
    body = {"employee": employee.id, "template": _template(code).id, "answers": answers or {}}
    return client.post("/api/v1/letters/", body, format="json")


def test_the_wording_is_parsed_before_any_value_goes_in():
    blocks = markup.parse("Dear {{first_name}},\n\nYou hold **{{post_title}}**.\n\n- one {{x}}\n- two")
    values = {"first_name": "<b>Asha</b>", "post_title": "**Lecturer**", "x": "\n\n- three"}
    page = markup.to_html(markup.merge(blocks, values))
    assert "Dear &lt;b&gt;Asha&lt;/b&gt;," in page and "<strong>**Lecturer**</strong>" in page
    assert page.count("<p>") == 2 and page.count("<li>") == 2  # a value adds no paragraph and no item
    assert markup.fields_in("{{a}} {{ b }} {{a}}") == ["a", "b"]
    assert markup.unclosed("{{a} or {b}}") and not markup.unclosed("{{a}} and {{b}}")


@pytest.mark.django_db
def test_the_record_gives_every_field_in_words(placed):
    from letters.fields import RECORD_FIELDS, record_values

    values = record_values(placed, date(2026, 10, 1))
    assert set(values) | {"reference"} == set(RECORD_FIELDS)
    assert values["today"] == "1 October 2026" and values["first_appointed"] == "2 September 2019"
    assert values["monthly_salary"] == "G$250,000.00" and values["grade"] == "GS GS5, step 1"
    assert (values["notice_period"], values["hours_per_week"]) == ("30 days", "40")
    assert values["appointment_type"] == "permanent" and values["probation_end"] == "1 March 2020"
    assert values["address"] == "Lot 5, Mon Repos, East Coast Demerara"  # one line, whatever was typed


@pytest.mark.django_db
def test_a_revised_scale_amount_applies_from_its_date(placed, monkeypatch):
    from letters.fields import record_values
    from org.models import Grade
    from people import services

    grade = Grade.objects.get(code="GS5")
    Grade.objects.create(
        scale=grade.scale, code="GS5", step=1, amount=Decimal("275000"), effective_from=date(2027, 1, 1)
    )
    assert grade.amount_on(date(2026, 12, 31)) == Decimal("250000.00")
    assert grade.amount_on(date(2027, 1, 1)) == Decimal("275000")
    assert record_values(placed, date(2027, 2, 1))["monthly_salary"] == "G$275,000.00"
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2027, 2, 1))
    contract = services.current_contract(placed)
    assert services.hourly_rate(contract) == Decimal("1586.54")  # 275,000 x 12 / (52 x 40)


@pytest.mark.django_db
def test_a_template_checks_its_fields_before_it_is_saved(hr_manager):
    client = _signed_in(hr_manager)
    body = {
        "code": "reference_check",
        "kind": "other",
        "name": "Reference check",
        "subject": "About {{full_name}}",
        "body": "Dear {{first_nme}},\n\n{{oops}",
        "signatory_title": "Human Resources Manager",
        "classification": "internal",
        "asks": [{"key": "unused", "label": "Never used", "type": "text"}],
    }
    refused = client.post("/api/v1/letters/templates/", body, format="json")
    assert refused.status_code == 400
    errors = refused.json()
    assert errors["body"][0].startswith("A field is written {{like_this}}")
    assert errors["body"][1].startswith("{{first_nme}}: not a field from the staff record")
    assert errors["asks"] == ["Asked but not used in the letter: Never used."]
    pay = {**body, "body": "Your salary is {{monthly_salary}}.", "asks": []}
    assert client.post("/api/v1/letters/templates/", pay, format="json").json()["classification"] == [
        "A letter that states pay is filed as Confidential or Medical."
    ]
    clash = {**body, "body": "{{full_name}}", "asks": [{"key": "full_name", "label": "Name", "type": "text"}]}
    clashed = client.post("/api/v1/letters/templates/", clash, format="json").json()
    assert "comes from the staff record" in clashed["asks"][0]
    taken = {**body, "code": "job_letter", "body": "Dear {{first_name}},", "asks": []}
    assert (
        "already has that code"
        in client.post("/api/v1/letters/templates/", taken, format="json").json()["code"][0]
    )


@pytest.mark.django_db
def test_a_change_to_a_template_is_its_next_version(hr_manager, api, make_user):
    manager = _signed_in(hr_manager)
    body = {
        "code": "reference_check",
        "kind": "other",
        "name": "Reference check",
        "subject": "About {{full_name}}",
        "body": "Dear {{first_name}},\n\nWe write about {{matter}}.",
        "signatory_title": "Human Resources Manager",
        "asks": [{"key": "matter", "label": "What it is about", "type": "text"}],
    }
    assert api.post("/api/v1/letters/templates/", body, format="json").status_code == 403  # an HR officer
    first = manager.post("/api/v1/letters/templates/", body, format="json")
    assert first.status_code == 201, first.content
    assert first.json()["version"] == 1 and first.json()["classification"] == "confidential"
    changed = {**body, "body": "Dear {{first_name}} {{last_name}},\n\nWe write about {{matter}}."}
    second = manager.post(f"/api/v1/letters/templates/{first.json()['id']}/revise/", changed, format="json")
    assert second.status_code == 201 and second.json()["version"] == 2
    newest = api.get("/api/v1/letters/templates/", {"code": "reference_check"}).json()["results"]
    assert [t["version"] for t in newest] == [2]
    every = api.get("/api/v1/letters/templates/", {"code": "reference_check", "versions": "all"}).json()
    assert [t["version"] for t in every["results"]] == [2, 1]
    retired = manager.post(f"/api/v1/letters/templates/{second.json()['id']}/in-use/", {"is_active": False})
    assert retired.json()["is_active"] is False
    assert AuditLog.objects.filter(entity="letters.lettertemplate", action="template_revised").exists()
    assert AuditLog.objects.filter(entity="letters.lettertemplate", action="template_retired").exists()
    principal = _signed_in(make_user("the.principal", "principal"))
    assert principal.get("/api/v1/letters/templates/fields/").json()["record"][0]["key"] == "today"


@pytest.mark.django_db
def test_hr_reads_the_letter_then_issues_it_into_the_file(api, placed):
    from letters.models import Letter
    from notifications.models import Notification

    preview = api.post(
        "/api/v1/letters/preview/",
        {"employee": placed.id, "template": _template("job_letter").id, "answers": {}},
        format="json",
    ).json()
    assert preview["subject"] == "Confirmation of employment: Asha Persaud" and preview["addressed"] is False
    assert preview["missing"] == [{"key": "purpose", "label": "What the letter is for", "asked": True}]
    assert preview["blocks"][1]["lines"][0][1] == {"text": "Asha Persaud", "bold": True}

    refused = _issue(api, placed)
    assert refused.status_code == 400 and refused.json() == {
        "code": "missing",
        "detail": "The letter cannot be issued yet: still to answer: what the letter is for.",
    }
    issued = _issue(api, placed, answers={"purpose": "a loan application at a bank"})
    assert issued.status_code == 201, issued.content
    year = timezone.localdate().year
    assert issued.json()["reference"] == f"GSA/HR/{year}/0001"
    letter = Letter.objects.get(pk=issued.json()["id"])
    content = letter.document.file.read()
    assert content.startswith(b"%PDF") and hashlib.sha256(content).hexdigest() == letter.sha256
    assert (letter.document.doc_type, letter.document.classification) == ("letter", "internal")
    assert letter.document.title == f"Job letter, GSA/HR/{year}/0001"
    assert letter.values["purpose"] == "a loan application at a bank"
    assert AuditLog.objects.filter(
        entity="letters.letter", entity_id=letter.pk, action="letter_issued"
    ).exists()
    told = Notification.objects.get(recipient=placed.user)
    assert told.title == "A letter for you: Job letter" and told.link == "/me"
    again = _issue(api, placed, "job_letter_salary", {"purpose": "a visa application"})
    assert again.json()["reference"] == f"GSA/HR/{year}/0002"
    assert Letter.objects.get(pk=again.json()["id"]).document.classification == "confidential"


@pytest.mark.django_db
def test_letters_are_kept_to_hr_and_the_person_they_are_for(api, placed, make_user, campus):
    from org.models import Campus

    issued = _issue(api, placed, answers={"purpose": "a loan application"}).json()
    supervisor = _signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert supervisor.get("/api/v1/letters/").status_code == 403
    elsewhere = _signed_in(make_user("esq.officer", "hr_officer", campus=Campus.objects.get(code="ESQ")))
    assert elsewhere.get("/api/v1/letters/").json()["count"] == 0
    assert elsewhere.get(issued["download_url"]).status_code == 404
    written = _issue(elsewhere, placed, answers={"purpose": "x"})
    assert written.status_code == 400 and "employee" in written.json()  # Asha is not on their campus

    principal = _signed_in(make_user("the.principal", "principal"))
    assert principal.get("/api/v1/letters/", {"q": "persaud"}).json()["count"] == 1
    download = api.get(issued["download_url"])
    assert download.status_code == 200 and b"".join(download.streaming_content).startswith(b"%PDF")
    assert AuditLog.objects.filter(entity="people.document", action="download").exists()

    asha = _signed_in(placed.user)
    mine = asha.get("/api/v1/letters/mine/").json()["results"]
    assert [m["reference"] for m in mine] == [issued["reference"]]
    assert mine[0]["download_url"] == f"/api/v1/letters/mine/{issued['id']}/download/"
    assert asha.get(mine[0]["download_url"]).status_code == 200
    assert asha.get(issued["download_url"]).status_code == 403  # the register is not hers to read
    someone = _signed_in(make_user("someone", "employee", campus=campus))
    assert someone.get("/api/v1/letters/mine/").json()["count"] == 0
    assert someone.get(mine[0]["download_url"]).status_code == 404


@pytest.mark.django_db
def test_a_letter_is_refused_once_its_template_changes_or_goes_out_of_use(api, hr_manager, placed):
    manager = _signed_in(hr_manager)
    old = _template("job_letter")
    body = {
        "kind": old.kind,
        "name": old.name,
        "subject": old.subject,
        "body": old.body.replace("To whom it may concern,", "To whom it may concern:"),
        "asks": old.asks,
        "addressed": old.addressed,
        "classification": old.classification,
        "signatory_title": old.signatory_title,
    }
    newer = manager.post(f"/api/v1/letters/templates/{old.id}/revise/", body, format="json").json()
    stale = api.post(
        "/api/v1/letters/",
        {"employee": placed.id, "template": old.id, "answers": {"purpose": "x"}},
        format="json",
    )
    assert stale.status_code == 409 and stale.json()["code"] == "changed"
    manager.post(f"/api/v1/letters/templates/{newer['id']}/in-use/", {"is_active": False})
    retired = _issue(api, placed, answers={"purpose": "x"})
    assert retired.status_code == 409 and retired.json()["code"] == "retired"


@pytest.mark.django_db
def test_the_first_templates_pass_their_own_checks(seeded):
    from letters.defaults import TEMPLATES, seed_templates
    from letters.models import LetterTemplate
    from letters.serializers import LetterTemplateSerializer

    assert seed_templates() == 0  # added once, by the seed
    for spec in TEMPLATES:
        checked = LetterTemplateSerializer(data=spec, context={"revising": True})
        assert checked.is_valid(), (spec["code"], checked.errors)
    assert LetterTemplate.objects.count() == len(TEMPLATES)
