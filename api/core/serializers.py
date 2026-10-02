"""Serializer base classes shared by the modules."""

from rest_framework import serializers


class InScope(serializers.PrimaryKeyRelatedField):
    """A related record the requesting user may see. Any other id reads as "does not exist".

    Writes name their employee (or appointment, contract, document) by id. Limiting the choices to the
    caller's campuses here, before any other validation runs, means a refusal can never describe a record
    on another campus, for example its leave balance. The views check scope again before saving.
    """

    def __init__(self, model, campus_field: str = "campus", **kwargs):
        self.model = model
        self.campus_field = campus_field
        super().__init__(**kwargs)

    def get_queryset(self):
        from iam.services import scope_queryset

        request = self.context.get("request")
        if request is None:
            return self.model.objects.none()
        queryset = scope_queryset(request.user, self.model.objects.all(), campus_field=self.campus_field)
        if self.model._meta.label_lower == "people.employee":
            # A person may always name themselves (their own leave), whatever roles they hold.
            own = getattr(request.user, "employee", None)
            if own is not None:
                queryset = queryset | self.model.objects.filter(pk=own.pk)
        return queryset


class ErrorSerializer(serializers.Serializer):
    """The body of every refusal the API writes itself: a stable code for programs, a sentence for people."""

    code = serializers.CharField()
    detail = serializers.CharField()


class TimeStampedSerializer(serializers.ModelSerializer):
    """Exposes audit stamps read-only; the view sets the acting user."""

    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        read_only_fields = ("id", "created_at", "updated_at")
