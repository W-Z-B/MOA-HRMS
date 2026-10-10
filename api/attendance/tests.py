from datetime import date, time

import pytest
from rest_framework.test import APIClient

from attendance import services
from attendance.models import AttendanceRecord, EmployeeShift, ShiftPattern

WEDNESDAY = date(2026, 11, 4)  # an ordinary working day, no public holiday
SATURDAY = date(2026, 11, 7)
CHRISTMAS = date(2026, 12, 25)  # seeded as a Guyana public holiday


@pytest.mark.django_db
def test_schedule_defaults_to_the_school_hours_when_no_shift_is_assigned(employee):
    schedule = services.schedule_for(employee, WEDNESDAY)
    assert schedule.shift is None
    assert schedule.starts == time(8, 0)
    assert schedule.is_working_day is True


@pytest.mark.django_db
def test_schedule_is_not_a_working_day_on_a_default_weekend(employee):
    assert services.schedule_for(employee, SATURDAY).is_working_day is False


@pytest.mark.django_db
def test_an_assigned_shift_overrides_the_default_hours(employee):
    shift = ShiftPattern.objects.create(
        code="EARLY", name="Early shift", starts=time(6, 0), ends=time(14, 0), working_days=[1, 2, 3, 4, 5, 6]
    )
    EmployeeShift.objects.create(employee=employee, shift=shift, effective_from=date(2026, 1, 1))
    schedule = services.schedule_for(employee, SATURDAY)
    assert schedule.shift == shift
    assert schedule.starts == time(6, 0)
    assert schedule.is_working_day is True  # the shift works Saturdays; the default week does not


@pytest.mark.django_db
def test_no_check_in_on_a_working_day_is_absent(employee):
    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY)
    services.evaluate(record)
    assert record.status == AttendanceRecord.Status.ABSENT
    assert record.hours == 0


@pytest.mark.django_db
def test_on_time_check_in_and_out_is_present(employee):
    record = AttendanceRecord.objects.create(
        employee=employee, date=WEDNESDAY, time_in=time(8, 2), time_out=time(16, 30)
    )
    services.evaluate(record)
    assert record.status == AttendanceRecord.Status.PRESENT
    assert record.hours == 8.47


@pytest.mark.django_db
def test_check_in_past_the_grace_period_is_late(employee):
    record = AttendanceRecord.objects.create(
        employee=employee, date=WEDNESDAY, time_in=time(8, 25), time_out=time(16, 30)
    )
    services.evaluate(record)
    assert record.status == AttendanceRecord.Status.LATE


@pytest.mark.django_db
def test_check_in_with_no_check_out_is_a_missing_checkout(employee):
    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY, time_in=time(8, 0))
    services.evaluate(record)
    assert record.status == AttendanceRecord.Status.MISSING_CHECKOUT


@pytest.mark.django_db
def test_approved_leave_is_never_absent_even_with_no_check_in(employee, campus):
    from leave.models import LeaveRequest, LeaveType

    leave_type = LeaveType.objects.create(code="TST", name="Test leave", annual_entitlement_days=10)
    leave_request = LeaveRequest.objects.create(
        employee=employee,
        leave_type=leave_type,
        from_date=WEDNESDAY,
        to_date=WEDNESDAY,
        days=1,
        state=LeaveRequest.State.APPROVED,
    )
    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY)
    services.evaluate(record)
    assert record.status == AttendanceRecord.Status.ON_LEAVE
    assert record.leave_request_id == leave_request.id


@pytest.mark.django_db
def test_a_public_holiday_is_never_absent(employee):
    record = AttendanceRecord.objects.create(employee=employee, date=CHRISTMAS)
    services.evaluate(record)
    assert record.status == AttendanceRecord.Status.HOLIDAY


@pytest.mark.django_db
def test_check_in_then_check_out_through_the_service(employee):
    services.check_in(employee, at=_at(WEDNESDAY, 8, 1))
    with pytest.raises(services.AttendanceError, match="already checked in"):
        services.check_in(employee, at=_at(WEDNESDAY, 9, 0))
    record = services.check_out(employee, at=_at(WEDNESDAY, 16, 45))
    assert record.status == AttendanceRecord.Status.PRESENT
    with pytest.raises(services.AttendanceError, match="already checked out"):
        services.check_out(employee, at=_at(WEDNESDAY, 17, 0))


@pytest.mark.django_db
def test_check_out_without_a_check_in_is_refused(employee):
    with pytest.raises(services.AttendanceError, match="not checked in"):
        services.check_out(employee, at=_at(WEDNESDAY, 16, 45))


@pytest.mark.django_db
def test_hr_correction_with_the_real_time_out_resolves_a_missing_checkout(employee):
    """HR supplies the time actually worked out: the day is recomputed on the true facts (present or late),
    not forced into a generic "corrected" status, but is still marked resolved so the sweep leaves it."""
    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY, time_in=time(8, 0))
    services.evaluate(record)
    record.save()
    assert record.status == AttendanceRecord.Status.MISSING_CHECKOUT

    corrected = services.correct(
        record, time_out=time(16, 30), note="Forgot to check out; confirmed with HOD"
    )
    assert corrected.status == AttendanceRecord.Status.PRESENT
    assert corrected.resolved is True
    assert corrected.source == AttendanceRecord.Source.CORRECTION

    counts = services.sweep(WEDNESDAY)
    corrected.refresh_from_db()
    assert corrected.status == AttendanceRecord.Status.PRESENT  # untouched: resolved records are skipped
    assert counts["flagged"] == 0


@pytest.mark.django_db
def test_hr_can_certify_a_day_with_no_times_at_all(employee):
    """Without a time to recompute from (the clock itself failed, say), HR's word still closes the day out
    rather than leaving it absent, and the sweep will not reopen it."""
    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY)
    services.evaluate(record)
    record.save()
    assert record.status == AttendanceRecord.Status.ABSENT

    corrected = services.correct(record, note="The clock was broken; the supervisor confirms she worked.")
    assert corrected.status == AttendanceRecord.Status.CORRECTED
    assert corrected.resolved is True

    services.sweep(WEDNESDAY)
    corrected.refresh_from_db()
    assert corrected.status == AttendanceRecord.Status.CORRECTED


@pytest.mark.django_db
def test_nightly_sweep_creates_absent_records_for_employees_with_no_check_in(employee):
    counts = services.sweep(WEDNESDAY)
    assert counts["created"] == 1
    assert counts["flagged"] == 1
    record = AttendanceRecord.objects.get(employee=employee, date=WEDNESDAY)
    assert record.status == AttendanceRecord.Status.ABSENT


def _at(day: date, hour: int, minute: int):
    from datetime import datetime

    from django.utils import timezone

    return timezone.make_aware(datetime(day.year, day.month, day.day, hour, minute))


@pytest.mark.django_db
def test_employee_can_check_in_and_out_through_the_api(employee, make_user, campus):
    user = make_user("checker", "employee", campus=campus)
    employee.user = user
    employee.save()
    # A shift working every day of the week, so the test passes whatever day it is actually run on.
    every_day = ShiftPattern.objects.create(
        code="ALL", name="Every day", starts=time(0, 0), ends=time(23, 59), working_days=[1, 2, 3, 4, 5, 6, 7]
    )
    EmployeeShift.objects.create(employee=employee, shift=every_day, effective_from=date(2020, 1, 1))
    client = APIClient()
    client.force_login(user)

    checked_in = client.post("/api/v1/attendance/records/check_in/")
    assert checked_in.status_code == 201, checked_in.content

    again = client.post("/api/v1/attendance/records/check_in/")
    assert again.status_code == 409
    assert again.json()["code"] == "already_checked_in"

    checked_out = client.post("/api/v1/attendance/records/check_out/")
    assert checked_out.status_code == 200, checked_out.content

    mine = client.get("/api/v1/attendance/records/mine/")
    assert mine.status_code == 200
    assert mine.json()["status"] in ("present", "late")


@pytest.mark.django_db
def test_an_employee_cannot_see_someone_elses_attendance(employee, make_user, campus):
    from people.models import Employee

    other = Employee.objects.create(
        employee_no="E0099",
        first_name="Other",
        last_name="Person",
        date_of_birth=date(1991, 1, 1),
        campus=campus,
    )
    AttendanceRecord.objects.create(employee=other, date=WEDNESDAY, time_in=time(8, 0), time_out=time(16, 30))
    user = make_user("plain", "employee", campus=campus)
    employee.user = user
    employee.save()
    client = APIClient()
    client.force_login(user)
    response = client.get(f"/api/v1/attendance/records/?employee={other.id}")
    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.django_db
def test_hr_can_correct_an_exception_with_a_reason(employee, hr_officer):
    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY, time_in=time(8, 0))
    services.evaluate(record)
    record.save()
    client = APIClient()
    client.force_login(hr_officer)

    missing_note = client.post(f"/api/v1/attendance/records/{record.id}/correct/", {})
    assert missing_note.status_code == 400  # a note is required, so every correction explains itself

    response = client.post(
        f"/api/v1/attendance/records/{record.id}/correct/",
        {"time_out": "16:30", "note": "Confirmed with supervisor"},
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "present"
    assert body["resolved"] is True


@pytest.mark.django_db
def test_a_supervisor_outside_the_campus_cannot_correct(employee, make_user):
    from org.models import Campus

    other_campus = Campus.objects.create(code="OTH", name="Other Campus")
    outsider = make_user("outside.hr", "hr_officer", campus=other_campus)
    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY, time_in=time(8, 0))
    services.evaluate(record)
    record.save()
    client = APIClient()
    client.force_login(outsider)
    response = client.post(
        f"/api/v1/attendance/records/{record.id}/correct/",
        {"time_out": "16:30", "note": "Should be refused"},
        format="json",
    )
    assert response.status_code in (403, 404)


@pytest.mark.django_db
def test_generic_create_and_destroy_are_not_offered(employee, hr_officer):
    client = APIClient()
    client.force_login(hr_officer)
    response = client.post(
        "/api/v1/attendance/records/",
        {"employee": employee.id, "date": str(WEDNESDAY)},
        format="json",
    )
    assert response.status_code == 405

    record = AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY, time_in=time(8, 0))
    assert client.patch(f"/api/v1/attendance/records/{record.id}/", {}, format="json").status_code == 405
    assert client.delete(f"/api/v1/attendance/records/{record.id}/").status_code == 405


@pytest.mark.django_db
def test_an_account_with_no_employee_record_cannot_check_in(make_user, seeded):
    user = make_user("noemployee", "employee")
    client = APIClient()
    client.force_login(user)
    assert client.post("/api/v1/attendance/records/check_in/").status_code == 404
    assert client.post("/api/v1/attendance/records/check_out/").status_code == 404
    assert client.get("/api/v1/attendance/records/mine/").status_code == 404


@pytest.mark.django_db
def test_mine_reads_null_when_nothing_is_recorded_today(employee, make_user, campus):
    user = make_user("nocheckin", "employee", campus=campus)
    employee.user = user
    employee.save()
    client = APIClient()
    client.force_login(user)
    response = client.get("/api/v1/attendance/records/mine/")
    assert response.status_code == 204


@pytest.mark.django_db
def test_nightly_task_notifies_hr_and_supervisors_of_open_exceptions(employee, hr_officer):
    from attendance.tasks import notify_exceptions

    AttendanceRecord.objects.create(employee=employee, date=WEDNESDAY, status=AttendanceRecord.Status.ABSENT)
    sent = notify_exceptions(WEDNESDAY)
    assert sent >= 1


@pytest.mark.django_db
def test_nightly_task_notifies_nobody_when_nothing_is_open(seeded):
    from attendance.tasks import notify_exceptions

    assert notify_exceptions(WEDNESDAY) == 0
