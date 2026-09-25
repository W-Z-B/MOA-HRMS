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
  campus: number;
  campus_name: string;
  status: "active" | "on_leave" | "suspended" | "separated";
  position_title: string | null;
  nis_no_masked: string | null;
  tin_masked: string | null;
  national_id_masked: string | null;
  email: string;
  phone: string;
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
  file: string;
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
  is_paid: boolean;
}

export interface LeaveBalance {
  leave_type: number;
  code: string;
  name: string;
  balance: string;
}

export interface LeaveRequest {
  id: number;
  employee: number;
  employee_name: string;
  leave_type: number;
  leave_type_code: string;
  from_date: string;
  to_date: string;
  days: string;
  reason: string;
  state: string;
  decision_comment: string;
  allowed_actions: string[];
  balance_after: string | null;
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

export interface ReportRow {
  [key: string]: string | number;
}

export interface ReportResult {
  key: string;
  name: string;
  rows: ReportRow[];
}
