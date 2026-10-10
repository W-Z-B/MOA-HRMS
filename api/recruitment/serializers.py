"""H-W01 serializers: vacancies, candidates and their applications, interviews, and hires.

``Candidate.national_id`` follows ``people.Employee``'s own rule for the same kind of number (item 1.46's
encryption at rest): the API never shows it in the clear, only masked, whoever is asking. That is the
"restricted-visibility pattern" decision for candidate PII asked for in this phase's build: nobody reads an
unredacted national ID back from this API; only HR roles may write one in, on `write_roles`.
"""

from rest_framework import serializers

from core.crypto import mask
from core.serializers import InScope, TimeStampedSerializer
from core.uploads import DOCUMENT, validate_upload
from org.models import Position
from recruitment.models import Application, Candidate, Hire, Interview, Vacancy
from recruitment.workflow import APPLICATION


class VacancySerializer(TimeStampedSerializer):
    position = InScope(Position, campus_field="org_unit__campus")
    grade_label = serializers.CharField(source="position.grade.__str__", read_only=True)
    campus_name = serializers.CharField(source="position.org_unit.campus.name", read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Vacancy
        fields = (
            "id",
            "position",
            "grade_label",
            "campus_name",
            "title",
            "description",
            "opens_on",
            "closes_on",
            "state",
            "is_open",
        )

    def validate(self, attrs):
        opens_on = attrs.get("opens_on", getattr(self.instance, "opens_on", None))
        closes_on = attrs.get("closes_on", getattr(self.instance, "closes_on", None))
        if opens_on and closes_on and closes_on < opens_on:
            raise serializers.ValidationError(
                {"closes_on": "Closing date cannot be before the opening date."}
            )
        return attrs


class CandidateSerializer(TimeStampedSerializer):
    national_id = serializers.CharField(write_only=True, required=False, allow_null=True, allow_blank=True)
    national_id_masked = serializers.SerializerMethodField()
    full_name = serializers.CharField(read_only=True)
    cv = serializers.FileField(write_only=True, required=False, allow_null=True)
    cv_filename = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Candidate
        fields = (
            "id",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "phone",
            "address",
            "national_id",
            "national_id_masked",
            "cv",
            "cv_filename",
        )

    def get_national_id_masked(self, obj) -> str | None:
        return mask(obj.national_id)

    def get_cv_filename(self, obj) -> str | None:
        return obj.cv_download_name or None

    def validate_cv(self, value):
        return validate_upload(value, DOCUMENT)


class TransitionSerializer(serializers.Serializer):  # used by ApplicationViewSet.transition
    action = serializers.CharField()
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class ApplicationSerializer(TimeStampedSerializer):
    candidate = CandidateSerializer()
    vacancy = InScope(Vacancy, campus_field="position__org_unit__campus")
    vacancy_title = serializers.CharField(source="vacancy.title", read_only=True)
    allowed_actions = serializers.SerializerMethodField()
    has_interview = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = Application
        fields = (
            "id",
            "vacancy",
            "vacancy_title",
            "candidate",
            "source",
            "state",
            "decision_comment",
            "notes",
            "reference",
            "allowed_actions",
            "has_interview",
        )
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + (
            "state",
            "decision_comment",
            "reference",
        )

    def get_allowed_actions(self, instance) -> list[str]:
        request = self.context.get("request")
        if request is None:
            return []
        return APPLICATION.allowed_actions(instance, request.user)

    def get_has_interview(self, instance) -> bool:
        return Interview.objects.filter(application=instance).exists()

    def validate_vacancy(self, value):
        if self.instance is None and not value.is_open:
            raise serializers.ValidationError("This vacancy is not open for applications.")
        return value

    def create(self, validated_data):
        candidate_data = validated_data.pop("candidate")
        candidate = Candidate.objects.create(
            created_by=self.context["request"].user, updated_by=self.context["request"].user, **candidate_data
        )
        return Application.objects.create(candidate=candidate, **validated_data)

    def update(self, instance, validated_data):
        # The candidate and the vacancy an application belongs to are set once, at creation; corrections to
        # a candidate's own details go through CandidateViewSet instead, and an application is never moved
        # to a different vacancy. Anything else sent here (notes, source) is a plain field update.
        validated_data.pop("candidate", None)
        validated_data.pop("vacancy", None)
        return super().update(instance, validated_data)


class InterviewSerializer(TimeStampedSerializer):
    application = InScope(Application, campus_field="vacancy__position__org_unit__campus")
    interviewer_name = serializers.CharField(source="interviewer.full_name", read_only=True)
    candidate_name = serializers.CharField(source="application.candidate.full_name", read_only=True)
    # Left out: defaults to RECRUITMENT_DEFAULT_INTERVIEW_MINUTES after `starts_at` (see validate()).
    ends_at = serializers.DateTimeField(required=False)

    class Meta(TimeStampedSerializer.Meta):
        model = Interview
        fields = (
            "id",
            "application",
            "candidate_name",
            "interviewer",
            "interviewer_name",
            "starts_at",
            "ends_at",
            "location",
            "state",
        )
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + ("state",)

    def validate(self, attrs):
        starts_at = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends_at = attrs.get("ends_at")
        if ends_at is None and starts_at is not None:
            attrs["ends_at"] = Interview.default_ends_at(starts_at)
        elif ends_at is not None and starts_at is not None and ends_at <= starts_at:
            raise serializers.ValidationError({"ends_at": "The interview must end after it starts."})
        return attrs


class HireSerializer(TimeStampedSerializer):
    candidate_name = serializers.CharField(source="candidate.full_name", read_only=True)
    vacancy_title = serializers.CharField(source="vacancy.title", read_only=True)

    class Meta(TimeStampedSerializer.Meta):
        model = Hire
        fields = (
            "id",
            "application",
            "vacancy",
            "vacancy_title",
            "candidate",
            "candidate_name",
            "start_date",
            "employee",
            "notes",
        )
        read_only_fields = TimeStampedSerializer.Meta.read_only_fields + (
            "application",
            "vacancy",
            "candidate",
            "employee",
        )


class ApplicationCheckSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=40)
    code = serializers.CharField(max_length=40)


class CheckedApplicationSerializer(serializers.Serializer):
    found = serializers.BooleanField()
    detail = serializers.CharField()
    reference = serializers.CharField(allow_null=True)
    vacancy = serializers.CharField(allow_null=True)
    state = serializers.CharField(allow_null=True)
    state_label = serializers.CharField(allow_null=True)
    submitted_at = serializers.DateTimeField(allow_null=True)
