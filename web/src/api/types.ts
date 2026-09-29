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
