# ADR 0006: Attendance is captured by phone, kiosk and supervisor first

**Status:** proposed (decision D3).
**Date:** 1 October 2026.

## Context

Feature 8 lists PINs, card readers, fingerprints and face recognition. GSA's devices on site are not
known (Planning Pack question Q2). Farm crews, security and kitchen staff may not have phones or email.
Biometric data is sensitive personal data under the Data Protection Act 2023, and readers are a purchase
outside the current scope.

## Decision (recommended)

1. **Phone:** staff clock in and out in the web app. The campus is confirmed by location at that moment
   only; the app does not track location at any other time. Works offline and keeps the time of the
   tap (item 3.06).
2. **Shared kiosk:** a tablet at each campus gate with a personal PIN (item 3.07).
3. **Crew register:** a supervisor marks field staff without phones (item 3.08).
4. **Import:** spreadsheet import now; device import when GSA owns devices (item 3.09).
5. Every correction to a recorded time needs a supervisor's approval and is audited (item 3.10).

## Consequences

- Attendance works on day one with no hardware purchase.
- If fingerprint or face readers are bought later, the HRMS stores only the punches (who, when, which
  device). Biometric templates stay on the device and never enter the HRMS, which keeps sensitive
  biometric data out of its database and its backups.
- Location is collected once per tap and stored as "on campus" or "not on campus", not as coordinates.
