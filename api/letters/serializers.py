"""Letters API shapes (item 1.19)."""

from rest_framework import serializers

from core.serializers import InScope, TimeStampedSerializer
from letters import markup
from letters.fields import ASK_TYPES, PAY_FIELDS, RECORD_FIELDS
from letters.models import Letter, LetterTemplate
from people.models import Document, Employee


class AskSerializer(serializers.Serializer):
    key = serializers.RegexField(r"^[a-z][a-z0-9_]{0,39}$", help_text="Used in the wording as {{key}}")
    label = serializers.CharField(max_length=120)
    type = serializers.ChoiceField(choices=list(ASK_TYPES.items()))


def _braced(keys) -> str:
    return ", ".join("{{" + key + "}}" for key in keys)


class LetterTemplateSerializer(TimeStampedSerializer):
    asks = serializers.ListField(child=AskSerializer(), required=False)
    kind_name = serializers.CharField(source="get_kind_display", read_only=True)
    classification_name = serializers.CharField(source="get_classification_display", read_only=True)
    fields_used = serializers.SerializerMethodField()

    class Meta(TimeStampedSerializer.Meta):
        model = LetterTemplate
        fields = (
            "id",
            "code",
            "version",
            "kind",
            "kind_name",
            "name",
            "subject",
            "body",
            "asks",
            "addressed",
            "classification",
            "classification_name",
            "signatory_name",
            "signatory_title",
            "is_active",
            "fields_used",
            "created_at",
            "updated_at",
        )
        read_only_fields = (*TimeStampedSerializer.Meta.read_only_fields, "version", "is_active")
        # The view numbers versions itself, under a lock; a new code is checked in validate_code.
        validators = []

    def get_fields_used(self, template) -> list[str]:
        return markup.fields_in(template.subject, template.body)

    def validate_code(self, code):
        if not self.context.get("revising") and LetterTemplate.objects.filter(code=code).exists():
            raise serializers.ValidationError(
                "A template already has that code. Change it to make a new version."
            )
        return code

    def validate(self, attrs):
        subject, body = attrs.get("subject", ""), attrs.get("body", "")
        asks = [dict(ask) for ask in attrs.get("asks", [])]
        keys = [ask["key"] for ask in asks]
        errors: dict[str, list[str]] = {}
        clash = [key for key in keys if key in RECORD_FIELDS]
        doubled = sorted({key for key in keys if keys.count(key) > 1})
        if clash or doubled:
            errors["asks"] = [
                f"{_braced(clash or doubled)} {'comes from the staff record' if clash else 'is asked twice'}:"
                " choose another name."
            ]
        for name, text in (("subject", subject), ("body", body)):
            if markup.unclosed(text):
                errors[name] = [
                    "A field is written {{like_this}}: two braces each side, small letters, no spaces."
                ]
        used = markup.fields_in(subject, body)
        unknown = [key for key in used if key not in RECORD_FIELDS and key not in keys]
        if unknown:
            errors.setdefault("body", []).append(
                f"{_braced(unknown)}: not a field from the staff record. Use one listed, or ask for it."
            )
        unused = [ask["label"] for ask in asks if ask["key"] not in used]
        if unused and "asks" not in errors:
            errors["asks"] = [f"Asked but not used in the letter: {', '.join(unused)}."]
        classification = attrs.get("classification", Document.Classification.CONFIDENTIAL)
        if PAY_FIELDS & set(used) and classification == Document.Classification.INTERNAL:
            errors["classification"] = ["A letter that states pay is filed as Confidential or Medical."]
        if errors:
            raise serializers.ValidationError(errors)
        attrs["asks"] = asks
        return attrs


class RecordFieldSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    pay = serializers.BooleanField(
        help_text="States pay: the letter is then filed as Confidential at the least"
    )


class AskTypeSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class FieldsSerializer(serializers.Serializer):
    record = RecordFieldSerializer(many=True)
    ask_types = AskTypeSerializer(many=True)


class InUseSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class LetterSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_no = serializers.CharField(source="employee.employee_no", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    template_version = serializers.IntegerField(source="template.version", read_only=True)
    kind = serializers.CharField(source="template.kind", read_only=True)
    issued_by = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Letter
        fields = (
            "id",
            "reference",
            "employee",
            "employee_name",
            "employee_no",
            "template",
            "template_name",
            "template_version",
            "kind",
            "issued_on",
            "issued_by",
            "sha256",
            "document",
            "download_url",
        )
        read_only_fields = fields

    def get_issued_by(self, letter) -> str | None:
        user = letter.created_by
        return (user.get_full_name() or user.get_username()) if user else None

    def get_download_url(self, letter) -> str:
        if self.context.get("own"):
            return f"/api/v1/letters/mine/{letter.pk}/download/"
        return f"/api/v1/letters/{letter.pk}/download/"


class WriteLetterSerializer(serializers.Serializer):
    employee = InScope(Employee, help_text="An employee on a campus you work with")
    template = serializers.PrimaryKeyRelatedField(queryset=LetterTemplate.objects.all())
    answers = serializers.DictField(
        child=serializers.CharField(allow_blank=True), required=False, help_text="What the template asks"
    )


class MissingSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    asked = serializers.BooleanField(
        help_text="Asked of the writer; otherwise it comes from the staff record"
    )


class PreviewSerializer(serializers.Serializer):
    subject = serializers.CharField()
    addressed = serializers.BooleanField()
    blocks = serializers.ListField(
        child=serializers.DictField(),
        help_text='{"type": "paragraph", "lines": [[run]]} or {"type": "list", "items": [[run]]}; '
        'a run is {"text": ..., "bold": ...}',
    )
    values = serializers.DictField(child=serializers.CharField(allow_blank=True))
    missing = MissingSerializer(many=True)
    classification = serializers.CharField()
