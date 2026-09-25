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

export interface LeaveRequest {
  id: number;
  employee: number;
  employee_name: string;
  leave_type_code: string;
  from_date: string;
  to_date: string;
  days: string;
  state: string;
  allowed_actions: string[];
}

export interface ReportRow {
  [key: string]: string | number;
}

export interface ReportResult {
  key: string;
  name: string;
  rows: ReportRow[];
}
