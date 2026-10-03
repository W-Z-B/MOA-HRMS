/** Types mirror the API serializers. Keep in step with /api/docs. */

export interface Me {
  id: number;
  username: string;
  name: string;
  roles: string[];
  mfa_required: boolean;
  mfa_verified: boolean;
  employee_id: number | null;
  /** Version of the privacy notice still to read and acknowledge, if any. */
  privacy_notice_due?: number | null;
  /** Who the person is at the School (item 2.30): their post, its unit, units they head, their campus. */
  position?: string | null;
  unit?: string | null;
  heads?: string[];
  campus?: string | null;
  /** Campuses the person works with: the campus switch shows when there is more than one. */
  campuses?: Campus[];
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
  /** Parts held back from use at the person's request, in words (item 1.46); absent on older answers. */
  restricted?: string[];
  nis_no_masked: string | null;
  tin_masked: string | null;
  national_id_masked: string | null;
  email: string;
  phone: string;
  address: string;
  /** The account linked to this record, if one has been opened (set only by opening an account). */
  user: number | null;
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
> & { national_id?: string; nis_no?: string; tin?: string; change_reason?: string };

export interface Position {
  id: number;
  number: string;
  title: string;
  grade: number;
  grade_name: string;
  org_unit: number;
  org_unit_name: string;
  campus_name: string;
  status: "approved" | "frozen" | "abolished";
  status_name: string;
  fte: string;
  is_vacant: boolean;
  /** The substantive holder, for roles that read the staff directory. */
  holder: string | null;
}

export interface OrgUnit {
  id: number;
  code: string;
  name: string;
  unit_type: "department" | "farm" | "unit" | "section";
  unit_type_name: string;
  parent: number | null;
  parent_name: string | null;
  campus: number;
  campus_name: string;
  head: number | null;
  head_name: string | null;
}

/** Counts for a unit and everything under it. Frozen counts frozen posts nobody holds. */
export interface ChartTotals {
  posts: number;
  filled: number;
  vacant: number;
  frozen: number;
}

export interface ChartPost {
  id: number;
  number: string;
  title: string;
  grade_name: string;
  status: "approved" | "frozen";
  status_name: string;
  fte: string;
  filled: boolean;
  vacant: boolean;
  /** Names show to the roles that read the staff directory, on its campuses; otherwise null. */
  holder: string | null;
  acting: string | null;
  has_acting: boolean;
}

export interface ChartUnit {
  id: number;
  code: string;
  name: string;
  unit_type: OrgUnit["unit_type"];
  unit_type_name: string;
  head: string | null;
  totals: ChartTotals;
  posts: ChartPost[];
  units: ChartUnit[];
}

export interface ChartCampus {
  id: number;
  code: string;
  name: string;
  /** Whether this reader sees who holds posts on this campus. */
  names: boolean;
  totals: ChartTotals;
  units: ChartUnit[];
}

export interface OrgChart {
  as_at: string;
  campuses: ChartCampus[];
}

export type Classification = "internal" | "confidential" | "medical";

/** Something a letter template asks of the writer, beyond the staff record. */
export interface LetterAsk {
  key: string;
  label: string;
  type: "text" | "date";
}

/** One version of a letter's wording (item 1.19). A change is saved as the next version. */
export interface LetterTemplate {
  id: number;
  code: string;
  version: number;
  kind: string;
  kind_name: string;
  name: string;
  subject: string;
  body: string;
  asks: LetterAsk[];
  addressed: boolean;
  classification: Classification;
  classification_name: string;
  signatory_name: string;
  signatory_title: string;
  is_active: boolean;
  fields_used: string[];
  created_at: string;
  updated_at: string;
}

export interface LetterFields {
  record: { key: string; label: string; pay: boolean }[];
  ask_types: { value: LetterAsk["type"]; label: string }[];
}

export interface LetterRun {
  text: string;
  bold: boolean;
}

export type LetterBlock = { type: "paragraph"; lines: LetterRun[][] } | { type: "list"; items: LetterRun[][] };

/** What a letter would say, and what it still needs before it can be issued. */
export interface LetterPreview {
  subject: string;
  addressed: boolean;
  blocks: LetterBlock[];
  values: Record<string, string>;
  missing: { key: string; label: string; asked: boolean }[];
  classification: Classification;
}

export interface Letter {
  id: number;
  reference: string;
  employee: number;
  employee_name: string;
  employee_no: string;
  template: number;
  template_name: string;
  template_version: number;
  kind: string;
  issued_on: string;
  issued_by: string | null;
  sha256: string;
  document: number;
  download_url: string;
  /** Printed at the foot of the letter for checking it (item 1.47); none on letters issued before. */
  check_code: string | null;
  times_checked: number;
  last_checked_at: string | null;
}

/** What the public page answers about a letter: whether it is genuine and, if so, only what it says. */
export interface CheckedLetter {
  genuine: boolean;
  detail: string;
  reference: string | null;
  letter: string | null;
  about: string | null;
  issued_on: string | null;
  subject: string | null;
  addressed: boolean | null;
  blocks: LetterBlock[] | null;
  values: Record<string, string> | null;
  sha256: string | null;
}

export interface SalaryScale {
  id: number;
  code: string;
  name: string;
}

export interface Grade {
  id: number;
  scale: number;
  scale_code: string;
  code: string;
  step: number;
  /** Empty for roles that do not see pay. */
  amount: string | null;
  effective_from: string;
}

export interface CampusDetail extends Campus {
  address: string;
  region: string;
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
  /** The grade and step paid on, by name: never the amount. */
  pay_grade_name: string;
  confirmed_on: string | null;
}

export type CareerKind = "transfer" | "promotion" | "increment" | "acting" | "confirmation";

/** A change in someone's career (item 1.11): scheduled, in effect, held up with the reason, or cancelled. */
export interface CareerEvent {
  id: number;
  employee: number;
  kind: CareerKind;
  kind_name: string;
  state: "scheduled" | "applied" | "cancelled" | "blocked";
  state_name: string;
  effective_date: string;
  end_date: string | null;
  from_post: string | null;
  to_position: number | null;
  to_post: string | null;
  from_grade_name: string | null;
  to_grade_name: string | null;
  reason: string;
  problem: string;
  applied_at: string | null;
  recorded_by: string | null;
  created_at: string;
  /** The code of the template its letter is written with. */
  letter_template: string;
  /** What its letter asks, answered from the change: for HR only, otherwise null. */
  letter_answers: Record<string, string> | null;
  letters: { id: number; reference: string; download_url: string }[];
}

export type LeavingReason =
  | "resignation"
  | "retirement"
  | "contract_end"
  | "notice"
  | "redundancy"
  | "dismissal"
  | "mutual"
  | "probation"
  | "death";

/** The notice the law and the contract ask for, and whether the last day leaves enough of it. */
export interface LeavingNotice {
  needed: boolean;
  why?: string;
  given_by?: "employee" | "school";
  given_on?: string;
  rule?: string;
  full_notice_ends?: string;
  short_by_days?: number;
}

/** What is owed on leaving (item 1.14): the statutory minimum, for the roles that see pay. */
export interface Settlement {
  last_day?: string;
  grade?: string;
  monthly?: string;
  weekly?: string;
  daily?: string;
  service_from?: string;
  completed_years?: number;
  lines: { key: "leave" | "notice" | "severance"; label: string; amount: string }[];
  total: string;
  notes: string[];
}

/** Someone leaving the School (item 1.12): leaving until the night after the last day, then left. */
export interface Separation {
  id: number;
  employee: number;
  employee_name: string;
  reason: LeavingReason;
  reason_name: string;
  state: "leaving" | "left" | "withdrawn";
  state_name: string;
  notice_given_on: string | null;
  last_day: string;
  note: string;
  completed_at: string | null;
  withdrawn_reason: string;
  notice: LeavingNotice;
  settlement: Settlement | null;
  recorded_by: string | null;
  created_at: string;
  letter_template: string;
  letter_answers: Record<string, string> | null;
  clearance: { done: number; total: number; open: string[] };
}

export type ItemCondition = "good" | "worn" | "damaged" | "lost";

/** Something the School handed to a member of staff, to be given back when they leave (item 1.17). */
export interface IssuedItem {
  id: number;
  employee: number;
  kind: string;
  kind_name: string;
  description: string;
  tag: string;
  issued_on: string;
  returned_on: string | null;
  condition: ItemCondition | "";
  condition_name: string;
  note: string;
  issued_by: string | null;
}

export interface ClearanceStep {
  id: number;
  code: string;
  label: string;
  who: string;
  state: "open" | "done" | "not_needed";
  state_name: string;
  note: string;
  cleared_at: string | null;
  cleared_by_name: string | null;
}

/** The clearance of someone leaving (item 1.13): each step, and everything issued still out. */
export interface Clearance {
  steps: ClearanceStep[];
  outstanding_items: IssuedItem[];
}

/** What someone leaving said (item 1.13): for HR and the Principal only. */
export interface ExitInterview {
  held_on: string;
  declined: boolean;
  main_reason: string;
  main_reason_name: string;
  would_recommend: string;
  would_recommend_name: string;
  rating_pay: number | null;
  rating_supervision: number | null;
  rating_training: number | null;
  rating_workload: number | null;
  rating_conditions: number | null;
  keep: string;
  change: string;
}

/** The evidence of one signature (item 1.20), kept once and never changed. */
export interface SignatureEvidence {
  signer_name: string;
  signed_at: string;
  statement: string;
  document_title: string;
  document_version: number;
  sha256: string;
  method: string;
  source_ip: string | null;
  device: string;
  /** Whether the document's file still has the fingerprint it had when signed. */
  file_unchanged: boolean;
}

export type SignatureKind = "acknowledge" | "accept";

export interface SignatureRequest {
  id: number;
  document: number;
  document_title: string;
  employee: number;
  employee_name: string;
  kind: SignatureKind;
  kind_name: string;
  statement: string;
  message: string;
  due_by: string | null;
  state: "waiting" | "signed" | "declined" | "withdrawn";
  state_name: string;
  created_at: string;
  decided_at: string | null;
  decline_reason: string;
  requested_by: string | null;
  evidence: SignatureEvidence | null;
  download_url: string;
}

/** Something waiting for my decision, from any module (item 1.33). */
export interface WaitingItem {
  kind: string;
  kind_name: string;
  title: string;
  since: string;
  waited_days: number;
  overdue: boolean;
  link: string;
  for_whom: string;
}

/** A stand-in: while someone is away, a colleague decides what is sent to them (item 1.33). */
export interface Delegation {
  id: number;
  delegator: number;
  delegator_name: string;
  delegate: number;
  delegate_name: string;
  starts: string;
  ends: string;
  reason: string;
  cancelled: boolean;
  in_force: boolean;
  created_at: string;
}

export type CaseKind = "discipline" | "grievance";

/** A discipline or grievance case (item 1.15): seen only by the HR Manager and those named on it. */
export interface CaseRecord {
  id: number;
  reference: string;
  kind: CaseKind;
  kind_name: string;
  employee: number;
  employee_name: string;
  employee_no: string;
  summary: string;
  opened_on: string;
  state: "open" | "decided" | "appeal" | "closed";
  state_name: string;
  outcome: string;
  outcome_name: string;
  outcome_reasons: string;
  decided_on: string | null;
  decided_by_name: string | null;
  lapses_on: string | null;
  appeal_lodged_on: string | null;
  appeal_grounds: string;
  appeal_outcome: string;
  appeal_outcome_name: string;
  appeal_reasons: string;
  appeal_decided_on: string | null;
  appeal_decided_by_name: string | null;
  closed_on: string | null;
  officers: { id: number; user: number; name: string; part: string; named_by_name: string | null; named_at: string }[];
  entries: { id: number; kind: string; kind_name: string; on: string; text: string; by: string | null; created_at: string }[];
  fair_steps: { allegation: boolean; answered: boolean };
}

export const CASE_ROLES = ["hr_officer", "hr_manager", "principal", "supervisor"];
export const CASE_OPEN_ROLES = ["hr_officer", "hr_manager"];

/** Accidents and incidents (item 1.16). Anyone reports one. HR, the Principal, supervisors and the auditor read
 * the register on their campuses; HR keeps it, and only HR reads what an injury was. */
export const INCIDENT_READ_ROLES = ["hr_officer", "hr_manager", "administrator", "principal", "supervisor", "auditor"];
export const INCIDENT_KEEP_ROLES = ["hr_officer", "hr_manager", "administrator"];
export type IncidentKind = "accident" | "near_miss" | "dangerous" | "disease";
export type IncidentState = "reported" | "investigating" | "closed";

export interface IncidentSummary {
  id: number;
  reference: string;
  kind: IncidentKind;
  kind_name: string;
  occurred_at: string;
  campus: number;
  campus_name: string;
  org_unit: number | null;
  org_unit_name: string | null;
  place: string;
  state: IncidentState;
  state_name: string;
  people_hurt: number;
  notices_overdue: boolean;
}

/** The injury, treatment and time off work are null for anyone who does not keep the register. */
export interface IncidentPerson {
  id: number;
  who: "staff" | "student" | "contractor" | "visitor";
  who_name: string;
  employee: number | null;
  name: string;
  injury: string | null;
  treatment: string | null;
  treatment_name: string | null;
  off_work_from: string | null;
  back_at_work_on: string | null;
  days_off: number | null;
  died_on: string | null;
  nis_form_on: string | null;
}

export interface SafetyNotice {
  id: number;
  duty: string;
  duty_name: string;
  recipient: string;
  recipient_name: string;
  person: number | null;
  sent_on: string;
  how: string;
  their_reference: string;
  recorded_by: string | null;
}

/** A notice the Occupational Safety and Health Act requires: by when, to whom, and whether each was sent. */
export interface SafetyDuty {
  duty: string;
  duty_name: string;
  section: string;
  person: number | null;
  person_name: string | null;
  due_on: string;
  overdue: boolean;
  to: { recipient: string; recipient_name: string; sent_on: string | null }[];
}

export interface SafetyAction {
  id: number;
  what: string;
  owner: number;
  owner_name: string;
  due_on: string;
  done_on: string | null;
  done_note: string;
  overdue: boolean;
}

export interface Incident extends IncidentSummary {
  industrial: boolean;
  description: string;
  immediate_action: string;
  reported_by: string | null;
  created_at: string;
  cause: string;
  investigated_on: string | null;
  investigated_by: string | null;
  closed_on: string | null;
  closed_by: string | null;
  people: IncidentPerson[];
  notices: SafetyNotice[];
  duties: SafetyDuty[];
  actions: SafetyAction[];
  outstanding: string[];
}

export interface MyIncident {
  id: number;
  reference: string;
  kind: IncidentKind;
  kind_name: string;
  occurred_at: string;
  campus_name: string;
  place: string;
  description: string;
  state: IncidentState;
  state_name: string;
  reported_by_me: boolean;
  my_injury: {
    injury: string;
    treatment_name: string;
    off_work_from: string | null;
    back_at_work_on: string | null;
    nis_form_on: string | null;
  } | null;
}

export interface MySafetyAction {
  id: number;
  reference: string;
  place: string;
  what: string;
  due_on: string;
  done_on: string | null;
  overdue: boolean;
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

/** One place the person is signed in, from /auth/sessions/. */
export interface SignedInSession {
  id: number;
  device: string;
  ip: string | null;
  created_at: string;
  last_seen_at: string;
  current: boolean;
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
/** Who reads the staff list, and so finds people from search (people.views.STAFF_READ). */
export const STAFF_READ_ROLES = ["hr_officer", "hr_manager", "administrator", "principal", "finance", "supervisor", "auditor"];
/** Who works with accounts (the server enforces the same rules; these only hide what would be refused). */
export const ACCOUNT_ROLES = ["administrator", "hr_manager", "hr_officer", "auditor"];
export const ACCOUNT_WRITE_ROLES = ["administrator", "hr_manager", "hr_officer"];
export const REVIEW_ROLES = ["administrator", "hr_manager", "auditor"];
export const REVIEW_SIGN_ROLES = ["administrator", "hr_manager"];
export const AUDIT_ROLES = ["administrator", "auditor"];
export const CORRECTION_ROLES = ["hr_officer", "hr_manager", "administrator"];
/** Objections and restrictions (item 1.46): the officer decides objections; HR and the officer restrict. */
export const OBJECTION_ROLES = ["data_protection_officer", "hr_manager", "administrator"];
export const OFFICER_ROLES = ["data_protection_officer"];
export const RESTRICTION_WRITE_ROLES = ["hr_officer", "hr_manager", "administrator", "data_protection_officer"];
/** Who sees the Admin section at all: those with a tab in it. */
export const ADMIN_ROLES = ["administrator", "hr_manager", "hr_officer", "auditor", "data_protection_officer"];
export const NOTICE_ROLES = ["administrator", "hr_manager", "auditor"];
export const NOTICE_WRITE_ROLES = ["administrator", "hr_manager"];
export const RETENTION_ROLES = ["administrator", "hr_manager", "auditor"];
export const RETENTION_WRITE_ROLES = ["administrator", "hr_manager"];
/** Holidays and leave types: read by those who work with accounts, kept by the HR Manager and administrators. */
export const SETUP_ROLES = ["administrator", "hr_manager", "hr_officer", "auditor"];
export const SETUP_WRITE_ROLES = ["administrator", "hr_manager"];
export const ORG_WRITE_ROLES = ["administrator", "hr_manager"];
export const GRADE_WRITE_ROLES = ["administrator", "hr_manager", "finance"];
/** Letters: the register and templates are read by those who read confidential documents; HR writes letters,
 * and the HR Manager and administrators keep the templates. */
export const LETTER_ROLES = ["hr_officer", "hr_manager", "administrator", "principal", "auditor"];
export const LETTER_WRITE_ROLES = ["hr_officer", "hr_manager", "administrator"];
export const TEMPLATE_WRITE_ROLES = ["hr_manager", "administrator"];
export const hasAnyRole = (me: Me, roles: readonly string[]) => roles.some((r) => me.roles.includes(r));
/** Staff with work to do in the system beyond their own leave: they see the full navigation. */
export const isOfficeUser = (me: Me) => me.roles.some((r) => r !== "employee");

/** What a person's Home shows (item 2.30), from /home/: figures for their role, on their campuses. */
export type Persona = "hr" | "principal" | "manager" | "office" | "employee";

export interface CampusFigures {
  id: number;
  code: string;
  name: string;
  active: number;
  posts: number;
  filled: number;
  vacant: number;
  frozen: number;
}

export interface HomeSummary {
  persona: Persona;
  as_at: string;
  ending_days: number;
  leave: { mine: number; waiting: number | null };
  staff: { campuses: CampusFigures[]; active: number; posts: number; filled: number; vacant: number; frozen: number } | null;
  units: { id: number; name: string; campus: string; posts: number; filled: number; vacant: number; frozen: number }[] | null;
  ending: { employee: number; name: string; position: string; campus: string; what: "contract" | "probation"; on: string }[] | null;
  no_account: {
    count: number;
    latest: { employee: number; name: string; position: string | null; campus: string; started: string | null }[];
  } | null;
  team:
    | {
        employee: number;
        name: string;
        position: string;
        appointment: string;
        started: string;
        ends: string | null;
        probation_end: string | null;
        is_me: boolean;
      }[]
    | null;
}

export interface ReportRow {
  [key: string]: string | number;
}

export interface ReportResult {
  key: string;
  name: string;
  rows: ReportRow[];
}

export interface Qualification {
  id: number;
  employee: number;
  level: string;
  level_name: string;
  title: string;
  institution: string;
  country: string;
  year_awarded: number | null;
  verified_on: string | null;
  document: number | null;
}

export interface PreviousEmployment {
  id: number;
  employee: number;
  employer: string;
  position: string;
  start_date: string;
  end_date: string | null;
  reason_for_leaving: string;
}

export interface Dependant {
  id: number;
  employee: number;
  name: string;
  relationship: string;
  relationship_name: string;
  date_of_birth: string | null;
}

export interface EmergencyContact {
  id: number;
  employee: number;
  name: string;
  relationship: string;
  phone: string;
  alternate_phone: string;
  priority: number;
}

export interface BankAccount {
  id: number;
  employee: number;
  bank_name: string;
  branch: string;
  account_name: string;
  account_number_masked: string;
  state: "pending" | "active" | "superseded" | "rejected";
  state_name: string;
  effective_from: string | null;
  requested_by: number | null;
  requested_by_name: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string;
  created_at: string;
}

export interface FieldChange {
  field: string;
  before: unknown;
  after: unknown;
}

/** One change to a person's file, from /employees/{id}/history/. */
export interface HistoryEntry {
  id: number;
  at: string;
  actor: string;
  action: string;
  action_name: string;
  record: string;
  record_id: number | null;
  changes: FieldChange[];
  reason: string;
  source_ip: string | null;
}

export interface RecordAsAt {
  date: string;
  current: boolean;
  record: Record<string, unknown>;
}

export interface ReportSummary {
  key: string;
  name: string;
  description: string;
  ministry_pack: boolean;
}

/** A link that chooses a password, from /auth/password/check/ and /auth/password/set/. */
export interface PasswordLink {
  username: string;
  kind: "invitation" | "reset";
}

/** One role an account holds, and where. */
export interface Grant {
  id: number;
  role: string;
  role_name: string;
  campus: number | null;
  where: string;
  given_by: string | null;
  given_at: string;
}

export interface Account {
  id: number;
  username: string;
  name: string;
  email: string;
  is_active: boolean;
  state: "invited" | "active" | "switched_off";
  last_login: string | null;
  date_joined: string;
  authenticator: boolean;
  employee: {
    id: number;
    employee_no: string;
    full_name: string;
    campus: number;
    campus_name: string;
    status: Employee["status"];
  } | null;
  roles: Grant[];
  sessions: number;
  /** Only when the account has just been opened, or its email changed: whether the email went out. */
  emailed?: boolean;
  /** A new sign-in email address waiting for the link sent to it to be followed (item 1.42). */
  pending_email: string | null;
}

/** One scanned paper of a batch: filed into someone's record, or not, and why (item 1.21). */
export interface ScanItem {
  id: number;
  name: string;
  employee: number | null;
  employee_name: string | null;
  employee_no: string | null;
  document: number | null;
  document_title: string | null;
  filed: boolean;
  refused: string;
  at: string;
}

/** A pile of scanned papers filed at one sitting; `items` only when one batch is read. */
export interface ScanBatch {
  id: number;
  doc_type: string;
  doc_type_name: string;
  classification: Classification;
  note: string;
  created_by_name: string | null;
  created_at: string;
  filed: number;
  not_filed: number;
  items?: ScanItem[];
}

/** Where links to choose a password go, and any change to it waiting for its confirmation (item 1.42). */
export interface SignInEmail {
  email: string;
  pending: { new_email: string; expires_at: string } | null;
}

export interface RoleChoice {
  code: string;
  name: string;
  may_give: boolean;
  needs_campus: boolean;
}

export interface LinkSent {
  kind: "invitation" | "reset";
  emailed: boolean;
  email: string;
}

export interface AccessReview {
  id: number;
  reviewed_by_name: string;
  reviewed_at: string;
  accounts: number;
  notes: string;
}

/** One entry of the audit log, from /audit/. */
export interface AuditEntry {
  id: number;
  at: string;
  actor: string;
  actor_username: string | null;
  action: string;
  action_name: string;
  entity: string;
  record: string;
  entity_id: number | null;
  subject: number | null;
  employee_no: string | null;
  reason: string;
  source_ip: string | null;
  changes: FieldChange[];
  before: unknown;
  after: unknown;
  chain: string;
}

/** One walk of the audit chain. */
export interface AuditCheck {
  id: number;
  checked_at: string;
  checked_by: string;
  rows: number;
  intact: boolean;
  last_id: number | null;
  first_broken_id: number | null;
  detail: string;
}

export interface AuditChainState {
  entries: number;
  newest: number | null;
  latest_check: AuditCheck | null;
}

export interface AuditChoices {
  actions: { code: string; name: string }[];
  records: { code: string; name: string }[];
}

/** One version of the privacy notice. */
export interface PrivacyNotice {
  id: number;
  version: number;
  title: string;
  body: string;
  created_at: string;
  published_at: string | null;
  published_by: string | null;
}

export interface CurrentNotice {
  notice: PrivacyNotice | null;
  acknowledged: boolean;
}

export interface CorrectionRequest {
  id: number;
  employee: number;
  employee_name: string;
  employee_no: string;
  subject: string;
  subject_name: string;
  wrong: string;
  should_be: string;
  state: "open" | "corrected" | "declined";
  state_name: string;
  due_by: string;
  overdue: boolean;
  created_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string;
  is_mine: boolean;
  /** That part is held back from use until the request is answered (item 1.46). */
  restricted?: boolean;
}

/** Part of a record held back from use: while contested, on objection, or for a legal reason (item 1.46). */
export interface RecordRestriction {
  id: number;
  employee: number;
  employee_name: string;
  employee_no: string;
  part: string;
  part_name: string;
  ground: "contested" | "unlawful" | "legal_claim" | "objection";
  ground_name: string;
  note: string;
  correction: number | null;
  objection: number | null;
  created_at: string;
  placed_by_name: string | null;
  in_force: boolean;
  lifted_at: string | null;
  lifted_by_name: string | null;
  lifted_reason: string;
}

/** An objection in writing to how part of a record is used, decided by the data protection officer. */
export interface Objection {
  id: number;
  employee: number;
  employee_name: string;
  employee_no: string;
  part: string;
  part_name: string;
  grounds: string;
  state: "open" | "upheld" | "not_upheld";
  state_name: string;
  due_by: string;
  overdue: boolean;
  created_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  reasons: string;
  is_mine: boolean;
}

/** Everything held about the signed-in person, from /privacy/my-record/. */
export interface OwnRecord {
  produced_at: string;
  about: string;
  account: Record<string, unknown> | null;
  staff_record: Record<string, unknown> | null;
}

/** One line of the retention schedule. */
export interface RetentionRule {
  id: number;
  code: string;
  name: string;
  keep_months: number | null;
  counted_from: string;
  action: string;
  action_name: string;
  automatic: boolean;
  confirmed: boolean;
  confirmed_by_name: string | null;
  confirmed_at: string | null;
  note: string;
  open_run: number | null;
}

export interface DisposalItem {
  id: number;
  description: string;
  employee: number | null;
  employee_no: string | null;
  due_since: string;
  keep_reason: string;
  disposed_at: string | null;
}

export interface DisposalRun {
  id: number;
  rule: number;
  rule_name: string;
  state: "proposed" | "done" | "cancelled";
  state_name: string;
  created_at: string;
  proposed_by: string | null;
  approved_by_name: string | null;
  approved_at: string | null;
  proposed_by_me: boolean;
  items: DisposalItem[];
}

export interface Breach {
  id: number;
  reference: string;
  discovered_at: string;
  happened: string;
  summary: string;
  data_affected: string;
  people_affected: number | null;
  risk: "low" | "medium" | "high";
  risk_name: string;
  contained_at: string | null;
  commissioner_told_at: string | null;
  people_told_at: string | null;
  actions: string;
  closed_at: string | null;
  recorded_by: string | null;
  created_at: string;
}

export interface Holiday {
  id: number;
  date: string;
  weekday: string;
  name: string;
}

/** A year checked against Guyana's holidays, from /holidays/calendar/. */
export interface HolidayCalendar {
  year: number;
  expected: { name: string; rule: string; date: string | null; on_file: Holiday | null }[];
  others: Holiday[];
  sundays: Holiday[];
}

/** Every rule of a leave type, as HR keeps them. */
export interface LeaveTypeRules {
  id: number;
  code: string;
  name: string;
  annual_entitlement_days: string;
  accrues_monthly: boolean;
  carry_over_max_days: string;
  max_balance_days: string | null;
  is_paid: boolean;
  requires_evidence: boolean;
  over_balance: "allow" | "refuse" | "evidence";
  evidence_name: string;
  evidence_is_medical: boolean;
  appointment_types: string[];
  term_time_restricted: boolean;
}
