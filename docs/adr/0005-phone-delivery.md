# ADR 0005: Phones use the installable web app, with push notices

**Status:** proposed (decision D2).
**Date:** 1 October 2026.

## Context

Feature 3 asks for access on the go and accepts it "at least from the website". The web app already
installs to the home screen, queues leave requests made without signal, and is laid out for phones
first; every browser journey now runs at 360 pixels wide in CI. Store apps for Android and iPhone would
need Apple and Google developer accounts in GSA's name, yearly fees, store review, and a second code
base to maintain.

Push notices to an installed web app work on Android browsers and, since iOS 16.4, on iPhones when the
app is added to the home screen.

## Decision (recommended)

1. Phones use the installable web app. No store apps in the current scope (item 2.29 stays a "could").
2. Add Web Push for approvals, decisions and reminders (item 2.23), with VAPID keys held as server
   secrets. Staff choose which notices they receive (item 2.26).
3. Add offline reading of a person's own balances, requests and receipts (item 2.24). Personnel data
   cached on a phone is limited to that person's own records and cleared on sign-out.

## Consequences

- One code base serves desktop and phone.
- Push needs a library to sign and encrypt messages. pywebpush (MPL-2.0) and its helpers would ship, so
  each needs a named exception under ADR 0002 when added. The alternative, hand-written message
  encryption on the `cryptography` package, is the riskier choice.
- If GSA later wants store apps (for example for kiosk lock-down), the web app can be wrapped without a
  rewrite; that would be a new decision with its own cost.
