## Summary

<!-- What changes and why, in a few sentences. -->

## Checklist items

<!-- The Gold Standard Plan items this delivers, for example 1.06, 1.07. Name any decision record. -->

## How it was checked

<!-- What you ran and saw: tests, the browser journey, a phone screenshot. -->

## Definition of done

- [ ] Acceptance points met and shown working on a phone and on a desktop
- [ ] Rules and permissions tested, including what must be refused; new endpoints added to the permission-matrix test
- [ ] Every change and every view of a sensitive item writes an audit row
- [ ] Accessible (keyboard, labels, contrast) and fits a 360px phone without sideways scrolling
- [ ] User guide, administrator note and API documentation updated
- [ ] Every CI gate green; no secrets, real personal data or real employee records in code, fixtures or screenshots
- [ ] New dependency: licence allowed by ADR 0002 (or a named exception with its reason), lock files updated
- [ ] Checklist item marked done in the Gold Standard Plan
