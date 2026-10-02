"""Who stands in for whom on a day (item 1.33)."""

from datetime import date

from django.utils import timezone

from approvals.models import Delegation


def active(on: date | None = None):
    on = on or timezone.localdate()
    return Delegation.objects.filter(cancelled=False, starts__lte=on, ends__gte=on)


def delegates_of(employee, on: date | None = None) -> list:
    """The colleagues standing in for someone today, so they are told what is sent to them."""
    if employee is None:
        return []
    held = active(on).filter(delegator=employee).select_related("delegate", "delegate__user")
    return [delegation.delegate for delegation in held]


def delegator_ids(employee, on: date | None = None) -> list[int]:
    """Everyone the person stands in for today."""
    if employee is None:
        return []
    return list(active(on).filter(delegate=employee).values_list("delegator_id", flat=True))


def acts_for(employee, manager_id: int | None, on: date | None = None) -> bool:
    """Whether the person may decide, today, what was sent to the manager."""
    if employee is None or manager_id is None:
        return False
    return active(on).filter(delegate=employee, delegator_id=manager_id).exists()


def users_of(employees) -> list:
    """The accounts of those who can sign in, to tell them."""
    return [e.user for e in employees if e is not None and e.user is not None and e.user.is_active]
