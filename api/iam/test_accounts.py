"""Accounts: invitations and password links (item 1.29), administration by role (1.25), and the access
review (1.27)."""

import re
from datetime import UTC, date, datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from audit.models import AuditLog
from iam import accounts
from iam.models import AccessReview, LoginAttempt, Role, RoleScope, TotpDevice, UserSession
from iam.tasks import remind_access_review
from notifications.models import Notification

PASSWORD = "Str0ng-Passw0rd-123"
NEW_PASSWORD = "Guava-Season-Starts-2026"
LINK = re.compile(r"/#/set-password/([^/\s]+)/([^/\s]+)")


def signed_in(user) -> APIClient:
    """A client signed in as the user, with the authenticator step done where the role needs it."""
    client = APIClient()
    client.force_login(user)
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client


def sign_in(username: str, password: str = PASSWORD, address: str = "190.80.1.2"):
    client = APIClient(HTTP_X_REAL_IP=address)
    response = client.post("/api/v1/auth/login/", {"username": username, "password": password}, format="json")
    return client, response


def link_in(message) -> dict:
    uid, token = LINK.search(message.body).groups()
    return {"uid": uid, "token": token}


def reset_link(user) -> dict:
    user.refresh_from_db()  # the token is signed over the last sign-in, so read the latest
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": accounts.reset_tokens().make_token(user),
    }


def staff(campus, number: str, user=None, **names):
    from people.models import Employee

    return Employee.objects.create(
        employee_no=number,
        first_name=names.get("first_name", "Test"),
        last_name=names.get("last_name", number),
        date_of_birth=date(1985, 5, 5),
        email=names.get("email", ""),
        campus=campus,
        user=user,
    )


@pytest.fixture
def essequibo(seeded):
    from org.models import Campus

    return Campus.objects.get(code="ESQ")


@pytest.fixture
def staff_member(employee):
    employee.email = "asha.persaud@gsa.example"
    employee.save()
    return employee


@pytest.fixture
def administrator(make_user, seeded):
    return make_user("sys.admin", "administrator")


# ---------------------------------------------------------------------------------------------- links


@pytest.mark.django_db
def test_an_invited_employee_chooses_their_own_password(api, staff_member):
    opened = api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    assert opened.status_code == 201, opened.content
    account = opened.json()
    assert account["username"] == "asha.persaud" and account["state"] == "invited" and account["emailed"]
    assert [grant["role"] for grant in account["roles"]] == ["employee"]
    assert account["employee"]["employee_no"] == "E0001"

    (invitation,) = mail.outbox
    assert invitation.to == ["asha.persaud@gsa.example"] and "asha.persaud" in invitation.body
    link = link_in(invitation)
    checked = APIClient().post("/api/v1/auth/password/check/", link, format="json")
    assert checked.json() == {"username": "asha.persaud", "kind": "invitation"}

    weak = APIClient().post("/api/v1/auth/password/set/", {**link, "password": "password"}, format="json")
    assert weak.status_code == 400 and weak.json()["password"]
    chosen = APIClient().post("/api/v1/auth/password/set/", {**link, "password": NEW_PASSWORD}, format="json")
    assert chosen.status_code == 200 and chosen.json()["username"] == "asha.persaud"

    _, signed = sign_in("asha.persaud", NEW_PASSWORD)
    assert signed.status_code == 200 and signed.json()["employee_id"] == staff_member.id
    again = {**link, "password": "Another-Choice-2026"}
    used = APIClient().post("/api/v1/auth/password/set/", again, format="json")
    assert used.status_code == 400 and used.json()["code"] == "invalid_link"

    # HR sees the account opened in the person's history; the password is the person's own business.
    history = api.get(f"/api/v1/employees/{staff_member.id}/history/").json()
    assert ("Account", "Opened") in {(row["record"], row["action_name"]) for row in history}
    assert not {"password_set", "password_link_sent"} & {row["action"] for row in history}
    assert AuditLog.objects.filter(action="password_set", subject=staff_member.id).exists()


@pytest.mark.django_db
def test_asking_for_a_link_never_tells_whether_an_account_exists(hr_officer):
    hr_officer.email = "natasha.khan@gsa.example"
    hr_officer.save()
    anyone = APIClient(HTTP_X_REAL_IP="190.80.4.4")
    answers = [
        anyone.post("/api/v1/auth/password/forgot/", {"login": login}, format="json")
        for login in ("nobody.here", "hr.officer", "NATASHA.KHAN@gsa.example")
    ]
    assert {a.status_code for a in answers} == {200}
    assert len({a.content for a in answers}) == 1
    assert len(mail.outbox) == 2 and all(m.to == ["natasha.khan@gsa.example"] for m in mail.outbox)
    assert "hr.officer" in mail.outbox[0].body

    reset = link_in(mail.outbox[0])
    assert APIClient().post("/api/v1/auth/password/check/", reset, format="json").json()["kind"] == "reset"
    nobody = {"uid": urlsafe_base64_encode(b"12345"), "token": "x-y"}
    assert (
        APIClient().post("/api/v1/auth/password/check/", nobody, format="json").json()["code"]
        == "invalid_link"
    )


@pytest.mark.django_db
def test_a_reset_link_works_for_an_hour_and_an_invitation_for_a_week(hr_officer, monkeypatch, settings):
    settings.PASSWORD_RESET_MINUTES = 60
    settings.INVITATION_DAYS = 7
    reset_token = accounts.reset_tokens().make_token(hr_officer)
    invitation_token = accounts.invitation_tokens().make_token(hr_officer)
    later = datetime.now() + timedelta(minutes=61)
    monkeypatch.setattr(accounts.LinkTokens, "_now", lambda self: later)
    assert accounts.link_kind(hr_officer, reset_token) is None
    assert accounts.link_kind(hr_officer, invitation_token) == "invitation"
    week_later = datetime.now() + timedelta(days=7, minutes=1)
    monkeypatch.setattr(accounts.LinkTokens, "_now", lambda self: week_later)
    assert accounts.link_kind(hr_officer, invitation_token) is None
    assert accounts.link_kind(hr_officer, "not-a-token") is None
    assert accounts.link_kind(hr_officer, "zz!-abc") is None
    assert accounts.link_kind(None, invitation_token) is None
    assert accounts.user_from_link("%%%") is None


@pytest.mark.django_db
def test_asking_again_and_again_is_limited(hr_officer, settings):
    settings.PASSWORD_RESETS_PER_ADDRESS = 5
    settings.PASSWORD_RESETS_PER_ACCOUNT = 3
    hr_officer.email = "hr.officer@gsa.example"
    hr_officer.save()
    asker = APIClient(HTTP_X_REAL_IP="203.0.113.9")
    for _ in range(5):
        assert (
            asker.post("/api/v1/auth/password/forgot/", {"login": "hr.officer"}, format="json").status_code
            == 200
        )
    assert len(mail.outbox) == 3  # the person's inbox is not flooded
    held = asker.post("/api/v1/auth/password/forgot/", {"login": "hr.officer"}, format="json")
    assert held.status_code == 429 and held.json()["code"] == "too_many_attempts"
    elsewhere = APIClient(HTTP_X_REAL_IP="190.80.1.2")
    assert (
        elsewhere.post("/api/v1/auth/password/forgot/", {"login": "someone"}, format="json").status_code
        == 200
    )


@pytest.mark.django_db
def test_choosing_a_password_signs_out_everywhere_and_lifts_a_lockout(hr_officer, settings):
    settings.LOGIN_MAX_FAILURES = 3
    phone, _ = sign_in("hr.officer")
    for _ in range(3):
        sign_in("hr.officer", "wrong-guess")
    _, locked = sign_in("hr.officer")
    assert locked.status_code == 423

    chosen = APIClient().post(
        "/api/v1/auth/password/set/", {**reset_link(hr_officer), "password": NEW_PASSWORD}, format="json"
    )
    assert chosen.status_code == 200 and chosen.json()["kind"] == "reset"
    assert phone.get("/api/v1/auth/me/").status_code == 403
    assert not UserSession.objects.filter(user=hr_officer).exists()
    _, again = sign_in("hr.officer", NEW_PASSWORD)
    assert again.status_code == 200
    assert LoginAttempt.objects.filter(username="hr.officer", success=True).count() == 3


@pytest.mark.django_db
def test_changing_my_password_keeps_me_signed_in_here_only(hr_officer):
    laptop, _ = sign_in("hr.officer")
    phone, _ = sign_in("hr.officer", address="190.80.9.9")
    change = "/api/v1/auth/password/change/"
    wrong = laptop.post(change, {"current_password": "not-it", "new_password": NEW_PASSWORD}, format="json")
    assert wrong.status_code == 400 and wrong.json()["code"] == "wrong_password"
    weak = laptop.post(change, {"current_password": PASSWORD, "new_password": "12345678"}, format="json")
    assert weak.status_code == 400 and weak.json()["new_password"]

    changed = laptop.post(change, {"current_password": PASSWORD, "new_password": NEW_PASSWORD}, format="json")
    assert changed.json() == {"ended": 1}
    assert laptop.get("/api/v1/auth/me/").status_code == 200
    assert phone.get("/api/v1/auth/me/").status_code == 403
    rows = laptop.get("/api/v1/auth/sessions/").json()
    assert len(rows) == 1 and rows[0]["current"] is True
    assert AuditLog.objects.filter(action="password_change_failed").count() == 1


@pytest.mark.django_db
def test_a_role_given_later_still_asks_for_the_authenticator(make_user, campus):
    """A session is never verified just because the roles it signed in with needed no code."""
    person = make_user("rising.star", "employee", campus=campus)
    client, signed = sign_in("rising.star")
    assert signed.json()["mfa_verified"] is False
    RoleScope.objects.create(
        user=person, role=Role.objects.get(code=Role.HR_MANAGER)
    )  # as the admin site would
    refused = client.get("/api/v1/employees/")
    assert refused.status_code == 403 and refused.json()["code"] == "mfa_required"


# ---------------------------------------------------------------------------------------------- invitations


@pytest.mark.django_db
def test_opening_an_account_is_refused_where_it_should_be(api, staff_member, essequibo, administrator):
    from people.models import Employee

    elsewhere = staff(
        essequibo, "E0300", first_name="Ravi", last_name="Singh", email="ravi.singh@gsa.example"
    )
    unknown = api.post("/api/v1/accounts/", {"employee": elsewhere.id}, format="json")
    assert unknown.status_code == 400 and "Ravi" not in unknown.content.decode()

    staff_member.email = ""
    staff_member.save()
    no_email = api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    assert no_email.status_code == 400 and no_email.json()["code"] == "no_email"

    staff_member.email = "shared@gsa.example"
    staff_member.save()
    get_user_model().objects.create_user("someone.else", email="Shared@gsa.example")
    in_use = api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    assert in_use.status_code == 409 and in_use.json()["code"] == "email_in_use"

    staff_member.email = "asha.persaud@gsa.example"
    staff_member.status = Employee.Status.SEPARATED
    staff_member.save()
    left = api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    assert left.status_code == 400 and left.json()["code"] == "separated"

    staff_member.status = Employee.Status.ACTIVE
    staff_member.save()
    assert api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json").status_code == 201
    twice = api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    assert twice.status_code == 409 and twice.json()["code"] == "has_account"

    outsider = {"first_name": "Audit", "last_name": "Visitor", "email": "auditor@audit.example"}
    assert api.post("/api/v1/accounts/", outsider, format="json").status_code == 403
    opened = signed_in(administrator).post("/api/v1/accounts/", outsider, format="json")
    assert opened.status_code == 201 and opened.json()["roles"] == [] and opened.json()["employee"] is None
    assert opened.json()["username"] == "audit.visitor"
    assert signed_in(administrator).post("/api/v1/accounts/", {}, format="json").status_code == 400


@pytest.mark.django_db
def test_a_new_link_follows_the_staff_record_until_the_invitation_is_used(api, staff_member):
    api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    account = get_user_model().objects.get(username="asha.persaud")
    staff_member.refresh_from_db()  # now linked to the account
    staff_member.email = "asha.p@gsa.example"  # the first address was mistyped
    staff_member.save()
    sent = api.post(f"/api/v1/accounts/{account.id}/send-link/")
    assert sent.json() == {"kind": "invitation", "emailed": True, "email": "asha.p@gsa.example"}
    assert mail.outbox[-1].to == ["asha.p@gsa.example"]

    chosen = {**link_in(mail.outbox[-1]), "password": NEW_PASSWORD}
    assert APIClient().post("/api/v1/auth/password/set/", chosen, format="json").status_code == 200
    staff_member.email = "elsewhere@gsa.example"
    staff_member.save()
    sent = api.post(f"/api/v1/accounts/{account.id}/send-link/")
    assert sent.json() == {"kind": "reset", "emailed": True, "email": "asha.p@gsa.example"}


@pytest.mark.django_db
def test_suggested_usernames_are_plain_and_never_taken(db):
    get_user_model().objects.create_user("andre.oneil")
    assert accounts.suggest_username("André", "O'Neil") == "andre.oneil2"
    assert accounts.suggest_username("", "") == "staff"


# ---------------------------------------------------------------------------------------------- roles


@pytest.mark.django_db
def test_roles_are_given_only_by_those_who_may_give_them(api, hr_manager, staff_member, essequibo, campus):
    api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    account = get_user_model().objects.get(username="asha.persaud")
    url = f"/api/v1/accounts/{account.id}/roles/"

    given = api.post(url, {"role": "supervisor", "campus": campus.id}, format="json")
    assert given.status_code == 201
    assert {g["role"] for g in given.json()["roles"]} == {"employee", "supervisor"}
    assert (
        api.post(url, {"role": "supervisor", "campus": campus.id}, format="json").json()["code"]
        == "already_held"
    )
    assert api.post(url, {"role": "hr_officer", "campus": campus.id}, format="json").status_code == 403
    assert api.post(url, {"role": "supervisor", "campus": essequibo.id}, format="json").status_code == 403
    assert api.post(url, {"role": "supervisor"}, format="json").status_code == 403

    manager = signed_in(hr_manager)
    assert (
        manager.post(url, {"role": "hr_officer"}, format="json")
        .json()["detail"]
        .startswith("Choose the campus")
    )
    assert manager.post(url, {"role": "hr_officer", "campus": campus.id}, format="json").status_code == 201
    assert manager.post(url, {"role": "finance"}, format="json").status_code == 403
    # Now that Asha is an HR officer too, a fellow HR officer may no longer change her account.
    assert api.post(f"/api/v1/accounts/{account.id}/send-link/").status_code == 403
    mine = manager.post(
        f"/api/v1/accounts/{hr_manager.id}/roles/", {"role": "supervisor", "campus": campus.id}
    )
    assert mine.status_code == 403 and "your own account" in mine.json()["detail"]

    supervisor = RoleScope.objects.get(user=account, role__code="supervisor")
    taken = manager.delete(f"{url}{supervisor.id}/")
    assert taken.status_code == 200 and "supervisor" not in {g["role"] for g in taken.json()["roles"]}
    assert manager.delete(f"{url}{supervisor.id}/").status_code == 404
    change = AuditLog.objects.filter(action="role_removed").latest("at")
    assert "Supervisor" in change.before["roles"] and "Supervisor" not in change.after["roles"]

    history = api.get(f"/api/v1/employees/{staff_member.id}/history/").json()
    given_entry = next(row for row in history if row["action"] == "role_granted")
    assert given_entry["action_name"] == "Role given"
    assert [c["field"] for c in given_entry["changes"]] == ["Roles"]


@pytest.mark.django_db
def test_a_role_change_signs_the_person_out(api, make_user, campus):
    person = make_user("farm.hand", "employee", campus=campus)
    staff(campus, "E0400", user=person)
    phone, _ = sign_in("farm.hand")
    api.post(
        f"/api/v1/accounts/{person.id}/roles/", {"role": "supervisor", "campus": campus.id}, format="json"
    )
    assert phone.get("/api/v1/auth/me/").status_code == 403


@pytest.mark.django_db
def test_the_roles_i_may_give(api, hr_manager, administrator):
    def giveable(client):
        return {r["code"] for r in client.get("/api/v1/accounts/roles/").json() if r["may_give"]}

    assert giveable(api) == {"employee", "supervisor"}
    assert giveable(signed_in(hr_manager)) == {"employee", "supervisor", "hr_officer"}
    assert giveable(signed_in(administrator)) == {code for code, _ in Role.CODES}
    assert accounts.PRIVILEGED == {
        "administrator",
        "hr_manager",
        "finance",
        "principal",
        "auditor",
        "ministry_liaison",
    }


@pytest.mark.django_db
def test_an_administrator_is_changed_only_by_another_so_one_always_remains(administrator, make_user):
    me = signed_in(administrator)
    own = me.post(f"/api/v1/accounts/{administrator.id}/deactivate/", {"reason": "x"}, format="json")
    assert own.status_code == 403
    grant = RoleScope.objects.get(user=administrator, role__code="administrator")
    assert me.delete(f"/api/v1/accounts/{administrator.id}/roles/{grant.id}/").status_code == 403

    manager = signed_in(make_user("hr.boss", "hr_manager"))
    held = manager.post(f"/api/v1/accounts/{administrator.id}/deactivate/", {"reason": "x"}, format="json")
    assert held.status_code == 403 and "only an administrator" in held.json()["detail"]
    root = make_user("root", superuser=True)
    system = manager.post(f"/api/v1/accounts/{root.id}/deactivate/", {"reason": "x"}, format="json")
    assert system.status_code == 403 and "system account" in system.json()["detail"]

    second = signed_in(make_user("second.admin", "administrator"))
    assert second.delete(f"/api/v1/accounts/{administrator.id}/roles/{grant.id}/").status_code == 200


# ---------------------------------------------------------------------------------------------- switching off


@pytest.mark.django_db
def test_switching_an_account_off_ends_every_session_at_once(api, make_user, campus):
    person = make_user("leaving.soon", "employee", campus=campus)
    staff(campus, "E0500", user=person)
    phone, _ = sign_in("leaving.soon")
    url = f"/api/v1/accounts/{person.id}/"
    assert api.post(f"{url}deactivate/", {}, format="json").json()["reason"] == ["Say why."]
    off = api.post(f"{url}deactivate/", {"reason": "Left GSA on 30 September"}, format="json")
    assert off.status_code == 200 and off.json()["state"] == "switched_off"
    assert phone.get("/api/v1/auth/me/").status_code == 403
    _, refused = sign_in("leaving.soon")
    assert refused.status_code == 401
    assert AuditLog.objects.get(action="account_deactivated").reason == "Left GSA on 30 September"
    assert api.post(f"{url}deactivate/", {"reason": "again"}, format="json").status_code == 409
    assert api.post(f"{url}send-link/").json()["code"] == "switched_off"
    give = api.post(f"{url}roles/", {"role": "supervisor", "campus": campus.id}, format="json")
    assert give.json()["code"] == "switched_off"

    on = api.post(f"{url}reactivate/", {"reason": "Rehired"}, format="json")
    assert on.status_code == 200 and on.json()["state"] == "active"
    assert api.post(f"{url}reactivate/", {"reason": "again"}, format="json").status_code == 409


@pytest.mark.django_db
def test_an_account_of_someone_who_has_left_stays_off(api, make_user, campus):
    from people.models import Employee

    person = make_user("long.gone", "employee", campus=campus)
    record = staff(campus, "E0700", user=person)
    api.post(f"/api/v1/accounts/{person.id}/deactivate/", {"reason": "Left"}, format="json")
    record.status = Employee.Status.SEPARATED
    record.save()
    refused = api.post(f"/api/v1/accounts/{person.id}/reactivate/", {"reason": "Mistake"}, format="json")
    assert refused.status_code == 409 and refused.json()["code"] == "separated"


@pytest.mark.django_db
def test_only_an_administrator_resets_an_authenticator(administrator, hr_manager, make_user):
    TotpDevice.objects.create(
        user=hr_manager, secret="JBSWY3DPEHPK3PXP", confirmed_at=datetime(2026, 9, 1, tzinfo=UTC)
    )
    url = f"/api/v1/accounts/{hr_manager.id}/reset-authenticator/"
    other_manager = signed_in(make_user("hr.manager.two", "hr_manager"))
    assert other_manager.post(url, {"reason": "Lost phone"}, format="json").status_code == 403
    reset = signed_in(administrator).post(url, {"reason": "Lost phone"}, format="json")
    assert reset.status_code == 200 and reset.json()["authenticator"] is False
    assert not TotpDevice.objects.filter(user=hr_manager).exists()
    again = signed_in(administrator).post(url, {"reason": "Lost phone"}, format="json")
    assert again.status_code == 409 and again.json()["code"] == "no_authenticator"


# ---------------------------------------------------------------------------------------------- lists


@pytest.mark.django_db
def test_hr_sees_the_accounts_of_their_own_campus_and_the_auditor_reads_only(
    api, staff_member, essequibo, campus, make_user
):
    api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    far = make_user("far.away", "employee", campus=essequibo)
    staff(essequibo, "E0600", user=far)
    names = {row["username"] for row in api.get("/api/v1/accounts/").json()["results"]}
    assert "asha.persaud" in names and "far.away" not in names
    assert api.get(f"/api/v1/accounts/{far.id}/").status_code == 404
    invited = api.get("/api/v1/accounts/", {"state": "invited"}).json()["results"]
    assert {row["username"] for row in invited} == {"asha.persaud"}
    assert api.get("/api/v1/accounts/", {"state": "active"}).json()["count"] == 0
    assert api.get("/api/v1/accounts/", {"q": "E0001"}).json()["count"] == 1
    assert api.get("/api/v1/accounts/", {"role": "supervisor"}).json()["count"] == 0

    auditor = signed_in(make_user("the.auditor", "auditor"))
    everyone = {row["username"] for row in auditor.get("/api/v1/accounts/").json()["results"]}
    assert {"asha.persaud", "far.away", "hr.officer"} <= everyone
    on_essequibo = auditor.get("/api/v1/accounts/", {"campus": essequibo.id}).json()["results"]
    assert {row["username"] for row in on_essequibo} == {"far.away"}
    assert (
        auditor.post(f"/api/v1/accounts/{far.id}/deactivate/", {"reason": "x"}, format="json").status_code
        == 403
    )
    assert auditor.get("/api/v1/accounts/", {"state": "switched_off"}).json()["count"] == 0
    supervisor = signed_in(make_user("unit.head", "supervisor", campus=campus))
    assert supervisor.get("/api/v1/accounts/").status_code == 403


@pytest.mark.django_db
def test_the_staff_record_no_longer_links_an_account(api, staff_member, hr_officer):
    changed = api.patch(
        f"/api/v1/employees/{staff_member.id}/",
        {"user": hr_officer.id, "change_reason": "Link"},
        format="json",
    )
    assert changed.status_code == 200 and changed.json()["user"] is None
    staff_member.refresh_from_db()
    assert staff_member.user is None
    without = api.get("/api/v1/employees/", {"has_account": "0"}).json()["results"]
    assert [e["employee_no"] for e in without] == ["E0001"]
    assert api.get("/api/v1/employees/", {"has_account": "1"}).json()["count"] == 0


# ---------------------------------------------------------------------------------------------- access review


@pytest.mark.django_db
def test_the_access_review_lists_who_can_see_what_and_is_signed_off(api, hr_manager, staff_member, make_user):
    api.post("/api/v1/accounts/", {"employee": staff_member.id}, format="json")
    manager = signed_in(hr_manager)
    rows = manager.get("/api/v1/reports/access-review/").json()["rows"]
    asha = next(row for row in rows if row["username"] == "asha.persaud")
    assert (asha["role"], asha["where"], asha["given_by"]) == ("Employee", "Mon Repos Campus", "hr.officer")
    assert asha["to_check"] == "Never signed in" and asha["employee_no"] == "E0001"
    boss = next(row for row in rows if row["username"] == "hr.manager")
    assert "Needs an authenticator and has none" in boss["to_check"] and boss["where"] == "All campuses"
    make_user("no.role")
    nothing = next(
        row
        for row in manager.get("/api/v1/reports/access-review/").json()["rows"]
        if row["username"] == "no.role"
    )
    assert nothing["role"] == "No role" and "No role" in nothing["to_check"]
    assert api.get("/api/v1/reports/access-review/").status_code == 403

    notes = {"notes": "Took away a supervisor role no longer needed"}
    signed = manager.post("/api/v1/access-reviews/", notes, format="json")
    assert signed.status_code == 201
    assert signed.json()["accounts"] == get_user_model().objects.filter(is_active=True).count()
    assert AuditLog.objects.filter(action="access_review_signed").exists()
    auditor = signed_in(make_user("the.auditor", "auditor"))
    assert auditor.get("/api/v1/access-reviews/").json()["count"] == 1
    assert auditor.post("/api/v1/access-reviews/", {"notes": ""}, format="json").status_code == 403


@pytest.mark.django_db
def test_an_account_left_unused_shows_in_the_review(make_user, seeded):
    from reports.queries import access_review

    person = make_user("quiet.one", "employee")
    get_user_model().objects.filter(pk=person.pk).update(last_login=datetime(2026, 5, 1, 12, tzinfo=UTC))
    row = next(r for r in access_review(today=date(2026, 10, 1)) if r["username"] == "quiet.one")
    assert row["to_check"] == "No sign-in for 90 days" and row["last_signed_in"] == "01/05/2026"


@pytest.mark.django_db
def test_the_access_review_is_due_every_three_months(hr_manager, administrator):
    hr_manager.email = "hr.manager@gsa.example"
    hr_manager.save()
    assert remind_access_review(date(2026, 10, 5)) == 2
    assert remind_access_review(date(2026, 10, 12)) == 0  # once a quarter
    note = Notification.objects.get(recipient=hr_manager)
    assert note.title == "Access review due" and note.link == "/admin/review" and note.emailed

    review = AccessReview.objects.create(reviewed_by=hr_manager, accounts=3)
    AccessReview.objects.filter(pk=review.pk).update(reviewed_at=datetime(2026, 10, 15, 12, tzinfo=UTC))
    assert remind_access_review(date(2027, 1, 4)) == 0  # signed off 81 days before
    assert remind_access_review(date(2027, 1, 18)) == 2  # 95 days: due again, in a new quarter
    assert "15/10/2026" in Notification.objects.filter(recipient=hr_manager).latest("created_at").body
