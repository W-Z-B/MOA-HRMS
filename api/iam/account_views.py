"""Account administration: open accounts for staff, send password links, give and take roles, switch
accounts off and on, reset an authenticator, and sign off the access review (items 1.25, 1.27, 1.29).

Who may do what to whose account is decided in iam.accounts; every change is audited, most with a reason.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import UNUSABLE_PASSWORD_PREFIX
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record
from core.serializers import ErrorSerializer, InScope
from iam import accounts
from iam.models import AccessReview, Role, RoleScope, TotpDevice
from iam.permissions import RolePermission
from iam.services import campus_limit, has_role, scope_queryset
from org.models import Campus
from people.models import Employee

ACCOUNT_READ = (Role.ADMINISTRATOR, Role.HR_MANAGER, Role.HR_OFFICER, Role.AUDITOR)
ACCOUNT_WRITE = (Role.ADMINISTRATOR, Role.HR_MANAGER, Role.HR_OFFICER)
REVIEW_READ = (Role.ADMINISTRATOR, Role.HR_MANAGER, Role.AUDITOR)
REVIEW_SIGN = (Role.ADMINISTRATOR, Role.HR_MANAGER)
ROLE_ORDER = {code: index for index, (code, _) in enumerate(Role.CODES)}


def _name(user) -> str | None:
    return (user.get_full_name() or user.get_username()) if user else None


class GrantSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="role.code")
    role_name = serializers.CharField(source="role.name")
    where = serializers.SerializerMethodField(help_text="The campus or unit the role covers")
    given_by = serializers.SerializerMethodField()
    given_at = serializers.DateTimeField(source="created_at")

    class Meta:
        model = RoleScope
        fields = ("id", "role", "role_name", "campus", "where", "given_by", "given_at")
        read_only_fields = fields

    def get_where(self, grant) -> str:
        return accounts.where(grant)

    def get_given_by(self, grant) -> str | None:
        return _name(grant.created_by)


class AccountEmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)

    class Meta:
        model = Employee
        fields = ("id", "employee_no", "full_name", "campus", "campus_name", "status")
        read_only_fields = fields


class AccountSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField(
        help_text="invited (no password chosen yet), active, or switched_off"
    )
    authenticator = serializers.SerializerMethodField(help_text="An authenticator app is set up")
    employee = serializers.SerializerMethodField()
    roles = GrantSerializer(source="role_scopes", many=True, read_only=True)
    sessions = serializers.IntegerField(source="session_count", read_only=True)
    emailed = serializers.BooleanField(
        read_only=True, required=False, help_text="On opening an account: whether the invitation was sent"
    )

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "username",
            "name",
            "email",
            "is_active",
            "state",
            "last_login",
            "date_joined",
            "authenticator",
            "employee",
            "roles",
            "sessions",
            "emailed",
        )
        read_only_fields = fields

    def get_name(self, user) -> str:
        return _name(user)

    def get_state(self, user) -> str:
        if not user.is_active:
            return "switched_off"
        return "invited" if accounts.never_used(user) else "active"

    def get_authenticator(self, user) -> bool:
        device = getattr(user, "totp_device", None)
        return bool(device and device.is_confirmed)

    @extend_schema_field(AccountEmployeeSerializer(allow_null=True))
    def get_employee(self, user):
        employee = getattr(user, "employee", None)
        return AccountEmployeeSerializer(employee).data if employee else None


class InviteSerializer(serializers.Serializer):
    employee = InScope(Employee, required=False, help_text="The member of staff the account is for")
    first_name = serializers.CharField(max_length=150, required=False, help_text="Someone not on the staff")
    last_name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False)

    def validate(self, attrs):
        if "employee" not in attrs and not all(attrs.get(f) for f in ("first_name", "last_name", "email")):
            raise serializers.ValidationError(
                {
                    "employee": [
                        "Choose the member of staff, or give the name and email address of someone "
                        "who is not on the staff."
                    ]
                }
            )
        return attrs


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=300,
        help_text="Why; kept in the audit log",
        error_messages={"required": "Say why.", "blank": "Say why."},
    )


class GrantInputSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.CODES)
    campus = serializers.PrimaryKeyRelatedField(
        queryset=Campus.objects.all(), required=False, allow_null=True, help_text="Empty for every campus"
    )


class LinkSentSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=accounts.LINK_KINDS)
    emailed = serializers.BooleanField()
    email = serializers.EmailField()


class RoleChoiceSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    may_give = serializers.BooleanField(help_text="I may give and take away this role")
    needs_campus = serializers.BooleanField(help_text="The role covers one campus, which must be chosen")


class AccessReviewSerializer(serializers.ModelSerializer):
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AccessReview
        fields = ("id", "reviewed_by_name", "reviewed_at", "accounts", "notes")
        read_only_fields = ("id", "reviewed_by_name", "reviewed_at", "accounts")

    def get_reviewed_by_name(self, review) -> str:
        return _name(review.reviewed_by)


def _refused(code: str, detail: str, status_code: int = status.HTTP_409_CONFLICT) -> Response:
    return Response({"code": code, "detail": detail}, status=status_code)


ACCOUNT_FILTERS = [
    OpenApiParameter("q", OpenApiTypes.STR, description="Part of a name, username, email or employee number"),
    OpenApiParameter("state", OpenApiTypes.STR, enum=["invited", "active", "switched_off"]),
    OpenApiParameter("role", OpenApiTypes.STR, description="Accounts holding this role"),
    OpenApiParameter("campus", OpenApiTypes.INT, description="Staff of this campus, or roles on it"),
]


@extend_schema(parameters=ACCOUNT_FILTERS)
class AccountViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    """Accounts of the staff on the caller's campuses (every account for the broad roles)."""

    permission_classes = [RolePermission]
    read_roles = ACCOUNT_READ
    write_roles = ACCOUNT_WRITE
    serializer_class = AccountSerializer
    queryset = get_user_model().objects.none()
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        grants = RoleScope.objects.select_related("role", "campus", "org_unit", "created_by")
        qs = (
            get_user_model()
            .objects.select_related("employee__campus", "totp_device")
            .prefetch_related(Prefetch("role_scopes", queryset=grants.order_by("role_id", "campus_id")))
            .annotate(session_count=Count("user_sessions", distinct=True))
        )
        qs = scope_queryset(self.request.user, qs, campus_field="employee__campus")
        params = self.request.query_params
        text = (params.get("q") or "").strip()
        if text:
            qs = qs.filter(
                Q(username__icontains=text)
                | Q(first_name__icontains=text)
                | Q(last_name__icontains=text)
                | Q(email__icontains=text)
                | Q(employee__employee_no__istartswith=text)
            )
        never_used = Q(last_login__isnull=True, password__startswith=UNUSABLE_PASSWORD_PREFIX)
        state = params.get("state")
        if state == "switched_off":
            qs = qs.filter(is_active=False)
        elif state == "invited":
            qs = qs.filter(never_used, is_active=True)
        elif state == "active":
            qs = qs.filter(is_active=True).exclude(never_used)
        if params.get("role"):
            qs = qs.filter(role_scopes__role__code=params["role"])
        if (params.get("campus") or "").isdigit():
            campus = int(params["campus"])
            qs = qs.filter(Q(employee__campus_id=campus) | Q(role_scopes__campus_id=campus))
        return qs.distinct().order_by("last_name", "first_name", "username")

    def _fresh(self, user):
        return self.get_serializer(self.get_queryset().get(pk=user.pk)).data

    def _changeable(self, request):
        """The account named in the address, if the caller may change it: refused otherwise."""
        user = self.get_object()  # an account outside the caller's campuses reads as not found
        refusal = accounts.refusal(request.user, user)
        if refusal:
            self.permission_denied(request, message=refusal)
        return user

    def _reason(self, request) -> str:
        data = ReasonSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return data.validated_data["reason"]

    @extend_schema(
        request=InviteSerializer,
        responses={201: AccountSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Open an account and email the invitation to choose a password",
    )
    def create(self, request, *args, **kwargs):
        data = InviteSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        employee = data.validated_data.get("employee")
        if employee is None:
            if not has_role(request.user, Role.ADMINISTRATOR):
                self.permission_denied(
                    request, message="Only an administrator opens an account for someone not on the staff."
                )
            email = data.validated_data["email"]
        else:
            refusal = accounts.grant_refusal(request.user, Role.EMPLOYEE, employee.campus)
            if refusal:
                self.permission_denied(request, message=refusal)
            if employee.user_id:
                return _refused("has_account", f"{employee.full_name} already has an account.")
            if employee.status == Employee.Status.SEPARATED:
                return _refused(
                    "separated", f"{employee.full_name} has left GSA.", status.HTTP_400_BAD_REQUEST
                )
            if not employee.email:
                return _refused(
                    "no_email",
                    "Add an email address to the staff record first: the invitation is sent there.",
                    status.HTTP_400_BAD_REQUEST,
                )
            email = employee.email
        if get_user_model().objects.filter(email__iexact=email, is_active=True).exists():
            return _refused("email_in_use", "Another account already uses that email address.")
        with transaction.atomic():
            if employee is not None:
                user = accounts.open_account(employee, granted_by=request.user)
            else:
                user = accounts.open_external_account(
                    first_name=data.validated_data["first_name"],
                    last_name=data.validated_data["last_name"],
                    email=email,
                )
            record(
                request,
                "account_opened",
                user,
                after={"username": user.get_username(), "roles": accounts.describe_roles(user)},
            )
        emailed = accounts.send_invitation(user)
        record(request, "password_link_sent", user, after={"kind": "invitation", "emailed": emailed})
        account = self.get_queryset().get(pk=user.pk)
        account.emailed = emailed
        return Response(self.get_serializer(account).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses={200: LinkSentSerializer, 400: ErrorSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Email the person a link to choose their password (the invitation again, or a reset)",
    )
    @action(detail=True, methods=["post"], url_path="send-link")
    def send_link(self, request, pk=None):
        user = self._changeable(request)
        if not user.is_active:
            return _refused("switched_off", "Switch the account on first.")
        employee = getattr(user, "employee", None)
        if (
            accounts.never_used(user)
            and employee is not None
            and employee.email
            and employee.email != user.email
        ):
            # Until the invitation is used it follows the staff record, so a mistyped address can be mended.
            user.email = employee.email
            user.save(update_fields=["email"])
        if not user.email:
            return _refused(
                "no_email", "This account has no email address to send to.", status.HTTP_400_BAD_REQUEST
            )
        kind = "invitation" if accounts.never_used(user) else "reset"
        emailed = accounts.send_invitation(user) if kind == "invitation" else accounts.send_reset(user)
        record(request, "password_link_sent", user, after={"kind": kind, "emailed": emailed})
        return Response({"kind": kind, "emailed": emailed, "email": user.email})

    @extend_schema(
        request=ReasonSerializer,
        responses={200: AccountSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Switch an account off: it cannot sign in, and every session ends at once",
    )
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self._changeable(request)
        reason = self._reason(request)
        if not user.is_active:
            return _refused("switched_off", "The account is already switched off.")
        with transaction.atomic():
            user.is_active = False
            user.save(update_fields=["is_active"])
            ended = accounts.close_sessions(user)
            record(request, "account_deactivated", user, after={"sessions_ended": ended}, reason=reason)
        return Response(self._fresh(user))

    @extend_schema(
        request=ReasonSerializer,
        responses={200: AccountSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Switch an account back on",
    )
    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None):
        user = self._changeable(request)
        reason = self._reason(request)
        if user.is_active:
            return _refused("active", "The account is already switched on.")
        employee = getattr(user, "employee", None)
        if employee is not None and employee.status == Employee.Status.SEPARATED:
            return _refused("separated", f"{employee.full_name} has left GSA.")
        with transaction.atomic():
            user.is_active = True
            user.save(update_fields=["is_active"])
            record(request, "account_reactivated", user, reason=reason)
        return Response(self._fresh(user))

    @extend_schema(
        request=ReasonSerializer,
        responses={200: AccountSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Remove a lost authenticator, so the person sets up a new one at their next sign-in",
    )
    @action(detail=True, methods=["post"], url_path="reset-authenticator")
    def reset_authenticator(self, request, pk=None):
        if not has_role(request.user, Role.ADMINISTRATOR):
            self.permission_denied(request, message="Only an administrator resets an authenticator.")
        user = self._changeable(request)
        reason = self._reason(request)
        with transaction.atomic():
            deleted, _ = TotpDevice.objects.filter(user=user).delete()
            if not deleted:
                return _refused("no_authenticator", "This account has no authenticator to reset.")
            ended = accounts.close_sessions(user)
            record(request, "authenticator_reset", user, after={"sessions_ended": ended}, reason=reason)
        return Response(self._fresh(user))

    @extend_schema(
        request=GrantInputSerializer,
        responses={201: AccountSerializer, 403: ErrorSerializer, 409: ErrorSerializer},
        summary="Give a role on a campus; the person is signed out so it applies from their next sign-in",
    )
    @action(detail=True, methods=["post"], url_path="roles")
    def grant(self, request, pk=None):
        user = self._changeable(request)
        data = GrantInputSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        role = Role.objects.get(code=data.validated_data["role"])
        campus = data.validated_data.get("campus")
        refusal = accounts.grant_refusal(request.user, role.code, campus)
        if refusal:
            self.permission_denied(request, message=refusal)
        if not user.is_active:
            return _refused("switched_off", "Switch the account on first.")
        if RoleScope.objects.filter(user=user, role=role, campus=campus, org_unit__isnull=True).exists():
            return _refused("already_held", "They already hold that role there.")
        with transaction.atomic():
            before = accounts.describe_roles(user)
            RoleScope.objects.create(
                user=user, role=role, campus=campus, created_by=request.user, updated_by=request.user
            )
            accounts.close_sessions(user)
            record(
                request,
                "role_granted",
                user,
                before={"roles": before},
                after={"roles": accounts.describe_roles(user)},
            )
        return Response(self._fresh(user), status=status.HTTP_201_CREATED)

    @extend_schema(
        request=None,
        responses={200: AccountSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 409: ErrorSerializer},
        summary="Take a role away; the person is signed out so it applies at once",
    )
    @action(detail=True, methods=["delete"], url_path=r"roles/(?P<grant_id>\d+)")
    def revoke(self, request, pk=None, grant_id=None):
        user = self._changeable(request)
        grant = RoleScope.objects.filter(user=user, pk=grant_id).select_related("role").first()
        if grant is None:
            return _refused("not_found", "No such role on this account.", status.HTTP_404_NOT_FOUND)
        limit = campus_limit(request.user)
        if grant.role.code not in accounts.gives(request.user) or (
            limit is not None and grant.campus_id not in limit
        ):
            self.permission_denied(request, message="Only an administrator takes that role away.")
        with transaction.atomic():
            before = accounts.describe_roles(user)
            grant.delete()
            accounts.close_sessions(user)
            record(
                request,
                "role_removed",
                user,
                before={"roles": before},
                after={"roles": accounts.describe_roles(user)},
            )
        return Response(self._fresh(user))

    @extend_schema(responses=RoleChoiceSerializer(many=True), summary="Every role, and which I may give")
    @action(detail=False, methods=["get"])
    def roles(self, request):
        mine = accounts.gives(request.user)
        rows = [
            {
                "code": role.code,
                "name": role.name,
                "may_give": role.code in mine,
                "needs_campus": role.code in accounts.CAMPUS_ROLES,
            }
            for role in sorted(Role.objects.all(), key=lambda r: ROLE_ORDER.get(r.code, 99))
        ]
        return Response(RoleChoiceSerializer(rows, many=True).data)


class AccessReviewViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Sign-offs of the access review (item 1.27): the list of who can see what, read every three months."""

    permission_classes = [RolePermission]
    read_roles = REVIEW_READ
    write_roles = REVIEW_SIGN
    serializer_class = AccessReviewSerializer
    queryset = AccessReview.objects.select_related("reviewed_by")

    @transaction.atomic
    def perform_create(self, serializer):
        count = get_user_model().objects.filter(is_active=True).count()
        review = serializer.save(reviewed_by=self.request.user, accounts=count)
        record(self.request, "access_review_signed", review, after={"accounts": count, "notes": review.notes})
