# Data protection impact assessment

**Draft 0.3, 1 October 2026,** prepared by the development team for GSA's data protection officer.
Draft 0.2 records the privacy rights built in pull request 20: the notice and its acknowledgement, a
person's own record, and correction requests. Draft 0.3 records the retention schedule, reviewed disposal
and the breach register built in pull request 21.
GSA is the data controller and owns this assessment; the development team keeps it current as the
system changes. It is signed in section 9 before any real staff record is loaded (checklist item 7.03).

## 1. Legal position

The Data Protection Act No. 18 of 2023 received assent on 16 August 2023. Press reports up to
September 2026 say no commencement order has been issued. The HRMS is built to the Act now, so that
nothing has to change on the day it commences.

The requirements below follow the summary of the Act by Jack A. Alli, Sons & Co.
(jackalli.com, "Data Protection Act 2023: Summary of Main Requirements"), which does not give section
numbers. **GSA's legal adviser should map each point to the Act's sections and confirm it.**

## 2. Why an assessment is needed

The Act requires an assessment before processing that is likely to result in a high risk to people's
rights and freedoms. The HRMS processes, for every member of staff:

- health records (doctor's notes) and financial records (pay terms, later pay and bank details), both
  sensitive personal data under the Act;
- national identifiers (national ID, NIS number, TIN), which the Act allows regulations to protect
  further;
- possibly trade union membership (union dues deductions, Release 2) and biometric data (if fingerprint
  or face readers are bought), both sensitive; ADR 0006 keeps biometric templates out of the HRMS.

## 3. The processing

**Controller:** Guyana School of Agriculture. **Data protection officer:** to be designated; the Act
requires one for a public body. **Processors:** the managed-service provider, if contracted to host and
support the system, and the production hosting provider (in Guyana, item 7.04). The Act requires
processors to be registered and bound by a written contract stating the subject-matter and duration,
the nature and purpose, the types of data and categories of people, and the controller's obligations
and rights (item 7.18). Staging on Railway (United States) holds fictional data only and is not used for
personal data.

| People | Data | Source | Purpose | Lawful basis (as summarised) |
|---|---|---|---|---|
| Staff (permanent, contract, temporary, sessional, seasonal) | Name, date of birth, gender, contacts, campus, post, appointment, contract terms | HR, the employee | Employment administration | Performance of the employment contract; functions of a public body |
| Staff | National ID, NIS number, TIN | The employee | NIS and GRA returns, identity | Legal obligation |
| Staff | Leave requests, balances, decisions, receipts | The employee, managers, HR | Leave under the Leave with Pay Act and GSA rules | Contract; legal obligation (register of holidays) |
| Staff | Doctor's notes | The employee | Sick leave beyond the allotment | Contract; legal obligation; health data handled under the Act's conditions |
| Staff | Hourly rate, grade amount; later pay, deductions, bank details | HR, Finance | Pay and statutory returns | Contract; legal obligation |
| Staff | Career history: transfers, promotions, increments, acting appointments and confirmations, each with its reason and dates | HR | Employment administration; pay on the right grade and step | Contract; functions of a public body |
| Staff who leave | Why and when they left, the notice given, and the figures owed (leave not taken, pay in lieu of notice, severance) | HR | Ending employment lawfully; paying what is owed under the Termination of Employment and Severance Pay Act 1997 and the Leave with Pay Act | Legal obligation; contract |
| Staff | Letters issued to them (appointment, confirmation, transfer, job letters, certificates of service), the values each drew from the record, and a fingerprint of each PDF | HR | Employment administration; proof of employment at the employee's request | Contract; functions of a public body |
| Next of kin, dependants | Name, phone | The employee | Emergencies; tax deductions for children (Release 2) | Contract; vital interests |
| Applicants (Release 3) | Application, assessments | The applicant | Recruitment | Steps towards a contract at the applicant's request |
| Staff | Training records | HR, the LMS | Development, certificates | Contract |
| Everyone with an account | Username, email address, roles and who gave them, sign-ins, devices signed in, network addresses of sign-ins and of requests for a password link (what was typed is not kept) | The system, HR | Keeping the system secure; showing who can see what in the access review | Functions of a public body; the Act's security duty |
| Everyone with an account | Which version of the privacy notice they read and when; their correction requests, HR's answers and reasons | The person, HR | Showing that people were told, and that their requests were answered | The Act's duties to inform and to correct |

**Recipients:** GSA HR, the employee's own manager, Finance, the Principal and auditors (each limited by
role and campus); the Ministry of Agriculture (totals, not individuals); NIS and GRA (statutory returns);
banks (pay files, if pay is calculated here); the SRMS and LMS (staff directory without identifiers,
dates of birth or addresses).

**Transfers outside Guyana:** none planned for real data. Two points to confirm: where GSA's email service
is hosted (notices name people and dates; item 2.26 limits email to a link), and where off-site backups
are kept (item 7.09).

**Retention** (proposals for GSA to confirm). The schedule is now data in the system (pull request 21): the
Admin screen's Retention tab shows each period, whether GSA has agreed it, and who confirmed it. Doctor's
notes, other leave evidence and documents given a date are destroyed only when one person lists what is due
and a second approves; anything can be kept back with a reason (a legal hold). Sign-in records and
notifications already read are removed every night without review. Each destruction is written to the
audit log with the rule that required it. Periods for records whose end the system cannot yet tell, such
as a leaver's file, wait for the leaving process (item 1.12).

| Records | Proposal |
|---|---|
| Personnel file and appointments | Employment plus the period required by Government records and pension rules |
| Leave register and decisions | As the Leave with Pay Act and Labour Officer inspections require |
| Doctor's notes | Two years after the leave they support (in the schedule; GSA to confirm) |
| Audit log | Seven years (Planning Pack requirement) |
| Access review sign-offs | Seven years, with the audit log |
| Sign-in records, devices, requests for a password link | Twelve months; a device record ends with its session |
| Privacy notice acknowledgements, correction requests | As long as the staff record, then with it |
| Unsuccessful applicants | Six months after the post is filled |
| Fictional demonstration data | Never on a database with real records |

**Record of processing activities:** the Act requires the controller to keep one (purposes, categories
of people and data, recipients, transfers, erasure time limits, security measures). This section is its
starting point for the HRMS.

## 4. Necessity and proportionality

Choices already made to collect and show less:

- Identifiers are masked everywhere; the full value needs an audited reveal by HR.
- The integration API gives sibling systems names and posts only.
- Pay terms are hidden from roles that do not need them.
- No monitoring software; no equal opportunity questionnaire unless GSA asks, and then voluntary and in
  totals only (ADR 0008).
- Attendance location is checked once per tap and stored as on or off campus (ADR 0006).
- No decision about a person is made by the system alone, and no staff data goes to an outside AI
  service (ADR 0007).
- Fictional data only outside production.

## 5. Rights of the people concerned

| Right (as summarised) | How the system supports it | Status |
|---|---|---|
| To be told what is processed and why (controller, data protection officer, purposes, recipients, legal authority, whether compulsory, retention) | **Built (pull request 20):** a versioned notice that HR publishes; each person reads and acknowledges each version once, after sign-in, and the acknowledgement is recorded; a report shows who has not yet read it. A starting draft for GSA to complete is `docs/privacy/privacy-notice-draft.md` | Item 1.31; GSA to approve the text |
| To be told whether data is processed, and to receive its purposes, categories, recipients and retention | **Built (pull request 20):** My record shows everything held about the person, to read, print or download as a file, with the history of changes and who made them; HR can produce the same for a request made on paper. Every viewing is recorded. The file leaves out full bank account numbers | Item 1.31 |
| Rectification | **Built (pull request 20):** a correction request names what is wrong and what it should say; HR on the person's campus answers within `PRIVACY_RESPONSE_DAYS` (30 by default, GSA's own standard until regulations set one), corrected or not changed with the reason, and the person is told. Nobody answers a request about themselves. Changing details directly from self-service, with HR's approval, comes later | Items 1.31 and 2.18 |
| Erasure without undue delay | **Built (pull request 21):** disposal runs under the retention schedule, approved by a second person, each destruction recorded; logs removed nightly. Leavers' files follow once leaving is recorded | Items 1.32 and 1.12 |
| Restriction while accuracy is contested or on objection | A restriction flag on a record, honoured by every module | Item 1.46 |
| Objection in writing | Logged and decided by the data protection officer | Item 1.46 |
| Complaint to the Data Protection Commissioner | Stated in the privacy notice | Item 1.31 |

**Breaches** (pull request 21): every personal data breach is recorded in the register on the Admin
screen: when it was found, what happened, whose data, how many people, the risk, when it was
contained, when the Data Protection Commissioner and the people affected were told, and what was done.
Recording one alerts the administrators at once; a breach is closed only after it is contained.

## 6. Risks and measures

Likelihood and severity before the planned measures; residual risk once they are in place.

| Risk to people | Likelihood | Severity | Measures | Residual |
|---|---|---|---|---|
| Identity fraud after identifiers leak | Possible | Severe | Encryption, masking, audited reveal, authenticator code for all who can reveal (1.34) | Low |
| Health information seen by the wrong person | Possible | Severe | Medical class, access by the employee and HR only, audited downloads, 1.34 | Low |
| Pay or bank details disclosed | Possible | Significant | Pay fields restricted, bank details encrypted with second approval (1.07), confidential documents and letters for HR, the Principal and the auditor only (pull request 25), separation of duties in pay (4.15) | Low |
| Wrong records leading to wrong leave or pay | Possible | Significant | Validation, ledger-based balances, receipts, self-service view, rectification (2.18), parallel pay runs (4.26) | Low |
| Records kept too long | Likely until built | Moderate | Retention schedule and disposal run (1.32) | Low once built |
| Misuse by someone with access | Possible | Significant | Campus scoping, least privilege, access reviews (1.27), audit viewer with tamper evidence (1.26) | Low once built |
| Records lost or unavailable | Possible | Significant | Encrypted backups, off-site copy, timed restore drill (7.09); hosting in Guyana (7.04) | Low once built |
| Data leaves Guyana | Possible | Moderate | Hosting in Guyana; email carries links only (2.26); staging fictional | Low |
| A lost or shared phone shows someone's data | Possible | Moderate | Only one's own data is cached; sign-out; idle time-out (1.28) | Low once built |
| A breach goes unnoticed | Possible | Significant | Monitoring and alerts (7.10), audit log, breach register (1.32) | Low once built |
| Unfair automated decisions | Unlikely | Significant | None made by the system (ADR 0007) | Low |
| Discrimination in recruitment | Possible | Significant | One question bank and score sheet, recorded reasons, conflict declarations (ADR 0008) | Low |

## 7. Consultation

To consult before sign-off: GSA's data protection officer; the HR Manager; the IT Officer; staff
representatives and any recognised union (Planning Pack question Q5). The summary consulted does not
describe a duty to consult the Commissioner before processing; the legal adviser should confirm whether
one applies if a high residual risk remains.

## 8. Open questions for GSA

1. Who is the data protection officer?
2. Will GSA register as a data controller when the Act commences, and the service provider as a
   processor? Who signs the processing contract (item 7.18)?
3. The retention periods in section 3.
4. Where are GSA's email service and off-site backups hosted?
5. Do staff representatives or a union need to be consulted?

## 9. Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| Prepared by (development team) | | Draft 0.1 | 1 October 2026 |
| Data protection officer | | | |
| Approved for GSA (Principal or Board) | | | |
| Next review | | Before each release and on any new processing | |
