/** Types mirror the API serializers. Keep in step with /api/docs. */

export interface Me {
  id: number;
  username: string;
  name: string;
  roles: string[];
  mfa_required: boolean;
  mfa_verified: boolean;
  employee_id: number | null;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Campus {
  id: number;
  code: string;
  name: string;
}

export interface Employee {
  id: number;
  employee_no: string;
  full_name: string;
  first_name: string;
  last_name: string;
  other_names: string;
  date_of_birth: string;
  gender: "F" | "M" | "X";
  campus: number;
  campus_name: string;
  status: "active" | "on_leave" | "suspended" | "separated";
  position_title: string | null;
  nis_no_masked: string | null;
  tin_masked: string | null;
  national_id_masked: string | null;
  email: string;
  phone: string;
  address: string;
  next_of_kin_name: string;
  next_of_kin_phone: string;
}

/** Fields accepted on create and update; identifiers are write-only and optional. */
export type EmployeeInput = Pick<
  Employee,
  | "employee_no"
  | "first_name"
  | "last_name"
  | "other_names"
  | "date_of_birth"
  | "gender"
  | "campus"
  | "status"
  | "email"
  | "phone"
  | "address"
  | "next_of_kin_name"
  | "next_of_kin_phone"
> & { national_id?: string; nis_no?: string; tin?: string };

export interface Position {
  id: number;
  number: string;
  title: string;
  org_unit: number;
  org_unit_name: string;
  status: string;
  is_vacant: boolean;
}

export interface Assignment {
  id: number;
  employee: number;
  position: number;
  position_title: string;
  appointment_type: string;
  start_date: string;
  end_date: string | null;
  probation_end: string | null;
  is_acting: boolean;
  status: string;
}

export interface EmployeeDocument {
  id: number;
  doc_type: string;
  title: string;
  filename: string | null;
  download_url: string;
  version: number;
  classification: string;
  retention_date: string | null;
  created_at: string;
}

export interface Reveal {
  id: number;
  employee_no: string;
  national_id: string | null;
  nis_no: string | null;
  tin: string | null;
}

export interface LeaveType {
  id: number;
  code: string;
  name: string;
  requires_evidence: boolean;
  over_balance: "allow" | "refuse" | "evidence";
  evidence_name: string;
  is_paid: boolean;
}

/** Figures worked out by the server arrive as numbers; stored ones as strings such as "2.00". */
export type Days = number | string;

export interface LeaveBalance {
  leave_type: number;
  code: string;
  name: string;
  balance: Days;
  entitlement: Days;
  pending: Days;
  available: Days;
  limited: boolean;
}

export interface LeaveDecision {
  step: "manager" | "hr";
  step_name: string;
  outcome: "approved" | "rejected";
  actor_name: string;
  comment: string;
  decided_at: string;
}

export interface LeaveReceipt {
  number: string;
  issued_at: string;
  employee_no: string;
  employee_name: string;
  position: string;
  campus: string;
  leave_type: string;
  paid: boolean;
  from_date: string;
  to_date: string;
  return_date: string;
  days: string;
  days_beyond: string;
  evidence: string;
  approvals: { step: string; name: string; decided_at: string }[];
  balances: { code: string; name: string; remaining: string; pending: string }[];
}

export interface LeaveRequest {
  id: number;
  employee: number;
  employee_name: string;
  is_mine: boolean;
  leave_type: number;
  leave_type_code: string;
  leave_type_name: string;
  from_date: string;
  to_date: string;
  days: string;
  days_beyond: string;
  reason: string;
  state: string;
  evidence_name: string;
  evidence_required: boolean;
  has_evidence: boolean;
  manager_name: string | null;
  decision_comment: string;
  decisions: LeaveDecision[];
  allowed_actions: string[];
  balance_after: Days | null;
  receipt: LeaveReceipt | null;
}

/** Answer to "what would happen if I asked for these dates?", before anything is saved. */
export interface LeaveCheck {
  days: Days;
  available: Days;
  remaining: Days;
  beyond: Days;
  evidence_required: boolean;
  evidence_name: string;
  problems: { code: string; field: string; detail: string }[];
}

export interface Contract {
  id: number;
  assignment: number;
  employee: number;
  contract_type: "fixed_term" | "open_ended" | "sessional";
  term_months: number | null;
  signed_on: string | null;
  hours_per_week: string | null;
  hourly_rate: string | null;
  hourly_rate_effective: string | null;
  notice_period_days: number | null;
  other_terms: string;
}

export interface Entitlement {
  id: number;
  contract: number;
  leave_type: number;
  leave_type_code: string;
  leave_type_name: string;
  annual_days: string;
}

/** The signed-in employee's own appointment and contract, from /contracts/mine/. */
export interface MyTerms {
  employee_no: string;
  name: string;
  campus: string;
  position: string | null;
  unit: string | null;
  manager: string | null;
  appointment_type: string | null;
  start_date: string | null;
  end_date: string | null;
  probation_end: string | null;
  contract: {
    contract_type: string;
    term_months: number | null;
    signed_on: string | null;
    hours_per_week: number | null;
    hourly_rate: number | null;
    hourly_rate_is_set: boolean;
    notice_period_days: number | null;
    other_terms: string;
  } | null;
  entitlements: { code: string; name: string; annual_days: number; from_contract: boolean }[];
}

export interface Notification {
  id: number;
  kind: "info" | "approval" | "alert";
  title: string;
  body: string;
  link: string;
  created_at: string;
  read_at: string | null;
}

export const HR_ROLES = ["hr_officer", "hr_manager", "administrator"];
export const hasAnyRole = (me: Me, roles: string[]) => roles.some((r) => me.roles.includes(r));
/** Staff with work to do in the system beyond their own leave: they see the full navigation. */
export const isOfficeUser = (me: Me) => me.roles.some((r) => r !== "employee");

export interface ReportRow {
  [key: string]: string | number;
}

export interface ReportResult {
  key: string;
  name: string;
  rows: ReportRow[];
}
