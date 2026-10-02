"""Item 1.33: stand-ins. While someone is away, a colleague decides what is sent to them."""

from django.db import models
from django.db.models import F, Q

from core.models import TimeStampedModel
from people.models import Employee


class Delegation(TimeStampedModel):
    """From one day to another, the delegate may decide whatever is sent to the delegator, as they could."""

    delegator = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="delegations_given")
    delegate = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="delegations_held")
    starts = models.DateField()
    ends = models.DateField()
    reason = models.CharField(max_length=160, blank=True, help_text="Such as annual leave, or a course")
    cancelled = models.BooleanField(default=False)

    class Meta:
        ordering = ["-starts", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(ends__gte=F("starts")), name="delegation_ends_after_it_starts"
            ),
            models.CheckConstraint(condition=~Q(delegate=F("delegator")), name="delegation_to_someone_else"),
        ]

    def __str__(self) -> str:
        return f"{self.delegate} for {self.delegator}, {self.starts:%d/%m/%Y} to {self.ends:%d/%m/%Y}"
