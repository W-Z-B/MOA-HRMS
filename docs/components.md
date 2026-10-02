# Component specification (Release 1)

| Component | App or package | Requirement | Key entities | Interfaces | Notes |
|---|---|---|---|---|---|
| Organisation and establishment | `api/org` | F01 | Campus, OrgUnit, Grade, SalaryScale, Position | `/api/v1/org/*` | Position exclusion constraint: one active non-acting holder per position |
| Employee records | `api/people` | F02 | Employee, Document | `/api/v1/employees`, `/employees/{id}/documents` | Identifiers encrypted; masked in list views; reveal audited |
| Contracts and appointments | `api/people` | F03 | Assignment, Contract | `/assignments`, `/contracts`, `/contracts/mine` | Types: permanent, contract, temporary, sessional, seasonal; expiry alerts by job; contract terms: hours, hourly rate (own, or from grade and hours), notice, other terms; pay shown to HR, Finance, Principal and auditors only |
| Document management | `api/people` | F04 | Document | upload and download endpoints | Versioned; retention date; stored on the file volume |
| Administration and security | `api/iam`, `api/audit` | F05 | UserAccount, Role, RoleScope, AuditLog | `/api/v1/auth/*`, `/api/v1/admin/*` | MFA for privileged roles; audit rows insert-only |
| Leave management | `api/leave` | F06 | LeaveType, LeaveLedger, LeaveRequest, LeaveDecision, Entitlement | `/api/v1/leave/*` | Balance = sum of ledger; accrual job monthly; yearly grant of leave given whole (sick leave); rules checked on every request (see below); receipt on final approval |
| Employee self-service | `web/` PWA | F10 | (uses the above) | consumes `/api/v1` | Installable; phone first; offline queue; low-bandwidth budget under 500 KB; an employee with no other role sees Leave and My contract only |
| Notifications | `api/*` jobs | F11 | Notification | SMTP | Email in Release 1; in-app list; SMS deferred |
| Reporting | `api/reports` (to add in Sprint 6) | F17 | saved report definitions | `/api/v1/reports/{key}` | PDF via WeasyPrint, Excel via openpyxl |

## Leave rules (F06)

Each leave type says what happens to a request for more than the balance (`over_balance`):

| Rule | Meaning | Seeded for |
|---|---|---|
| `refuse` | The request is refused | Annual leave |
| `evidence` | Accepted only with supporting evidence; the ledger is debited to zero and the rest is recorded on the request as days beyond the entitlement | Sick leave (doctor's note) |
| `allow` | No limit: leave granted at discretion | Maternity, study, special, without pay |

- **What is available** on the first day of the leave: the ledger, plus monthly accruals still to come
  by that day (at most a year ahead), less requests awaiting a decision.
- **Checked automatically**, in the form before saving, on saving and again on submission: working days
  (weekends and public holidays excluded), balance, overlap with another request, eligibility by
  appointment type, evidence.
- **Approval**: the request goes to the head of the employee's unit, or the nearest head above who can
  sign in (`people.services.manager_of`); campus supervisors stand in only when there is none. Human
  Resources gives the final approval. Nobody decides their own request. Only a draft can be changed.
- **Evidence** is attached to the request by the employee (photo or PDF, 10 MB). Evidence for sick and
  maternity leave is filed as medical: the employee and HR can open it; the manager is told only that
  it is attached.
- **Receipt**: on final approval the request stores a receipt (leave granted, return date, approvers,
  balances left) and the employee is notified with the same figures. The receipt is a record of that
  day and is not rewritten by later leave.
- **Entitlement**: a contract may carry its own days a year for a leave type (`leave.Entitlement`);
  otherwise the leave type's standard applies.

## Cross-cutting rules

- Every table carries `id`, `created_at`, `updated_at`, `created_by`, `updated_by`.
- Every write to personnel data produces an `audit_log` row in the same transaction.
- Configuration that Finance or HR may change (leave rules, rate tables, holidays, workflow definitions) is stored as effective-dated data, never as code.
- Time zone `America/Guyana`; dates displayed `dd/mm/yyyy`; currency GYD.
- No component may be added unless its licence is MIT, BSD, Apache 2.0, PostgreSQL or PSF (ADR 0001).

## Release 2 components (not built yet)

Attendance (`api/time`), Performance (`api/performance`), Training (`api/training`), Payroll interface and
Statutory (`api/payroll`), Separation (`api/people`), native mobile apps (`mobile/`), desktop installers (`desktop/`).
