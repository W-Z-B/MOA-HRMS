# Component specification (Release 1)

| Component | App or package | Requirement | Key entities | Interfaces | Notes |
|---|---|---|---|---|---|
| Organisation and establishment | `api/org` | F01 | Campus, OrgUnit, Grade, SalaryScale, Position | `/api/v1/org/*` | Position exclusion constraint: one active non-acting holder per position |
| Employee records | `api/people` | F02 | Employee, Document | `/api/v1/employees`, `/employees/{id}/documents` | Identifiers encrypted; masked in list views; reveal audited |
| Contracts and appointments | `api/people` | F03 | Assignment, Contract | `/employees/{id}/assignments` | Types: permanent, contract, temporary, sessional, seasonal; expiry alerts by job |
| Document management | `api/people` | F04 | Document | upload and download endpoints | Versioned; retention date; stored on the file volume |
| Administration and security | `api/iam`, `api/audit` | F05 | UserAccount, Role, RoleScope, AuditLog | `/api/v1/auth/*`, `/api/v1/admin/*` | MFA for privileged roles; audit rows insert-only |
| Leave management | `api/leave` | F06 | LeaveType, LeaveLedger, LeaveRequest, WorkflowInstance | `/api/v1/leave/*` | Balance = sum of ledger; accrual job monthly; term-time restriction rule |
| Employee self-service | `web/` PWA | F10 | (uses the above) | consumes `/api/v1` | Installable; offline queue; low-bandwidth budget under 500 KB |
| Notifications | `api/*` jobs | F11 | Notification | SMTP | Email in Release 1; in-app list; SMS deferred |
| Reporting | `api/reports` (to add in Sprint 6) | F17 | saved report definitions | `/api/v1/reports/{key}` | PDF via WeasyPrint, Excel via openpyxl |

## Cross-cutting rules

- Every table carries `id`, `created_at`, `updated_at`, `created_by`, `updated_by`.
- Every write to personnel data produces an `audit_log` row in the same transaction.
- Configuration that Finance or HR may change (leave rules, rate tables, holidays, workflow definitions) is stored as effective-dated data, never as code.
- Time zone `America/Guyana`; dates displayed `dd/mm/yyyy`; currency GYD.
- No component may be added unless its licence is MIT, BSD, Apache 2.0, PostgreSQL or PSF (ADR 0001).

## Release 2 components (not built yet)

Attendance (`api/time`), Performance (`api/performance`), Training (`api/training`), Payroll interface and
Statutory (`api/payroll`), Separation (`api/people`), native mobile apps (`mobile/`), desktop installers (`desktop/`).
