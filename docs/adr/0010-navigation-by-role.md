# ADR 0010: Navigation by role: a Home for each role, search for everything, and To do

**Status:** proposed. Implemented by pull request 37 (item 2.30); merging it accepts this decision.
**Date:** 2 October 2026.

## Context

By the end of Phase 1 the side menu listed sixteen pages, the same list in the same order for every office
role, with the Release 2 placeholders among them. On a phone it became a strip of links to scroll sideways.
The first page was a dashboard of four counts for office staff and the leave page for everyone else. Roles
showed as system codes ("employee, supervisor, hr_officer").

Three ways to navigate were drawn on the same pages, roles and demonstration data:

| Option | What it is | For | Against |
|---|---|---|---|
| 1a. Grouped sidebar | Every page down the left, in groups that fold | Occasional users find pages by reading the list | Takes 256px from wide tables; a long list for HR |
| 1b. Section menus with sub-tabs | Four sections across the header, a tab bar for the current one | Full width; menus say what each page is for | Most pages a click deeper; the structure hidden on phones |
| 1c. A Home for each role, and a command bar | No permanent menu: Home shows each role its work and shortcuts; any page, person or action is a search away | Least chrome, fastest for daily users, search first on phones | Pages not on a role's Home are found only by searching |

The owner chose 1c, and all nine screens were then drawn on it (desktop and phone).

## Decision

1. **Home for each role.** HR, the Principal, a head of unit, other office roles, and an employee each get
   their own Home. Each one shows:
   - shortcuts to the pages that role uses;
   - figures counted on the campuses the person works with;
   - the decisions they can take on the spot. Leave is approved there, or rejected with a reason the
     employee sees.
   The figures come from one request (`/home/`), counted by the same scoping rules as the lists they lead
   to.
2. **Search for everything.** The bar in the header, or Ctrl K, finds people, pages and actions. Each
   person finds only what they may open. The Release 2 placeholders are not offered.
3. **To do** in the header, with its count. Leave is decided in place there too.
4. **A breadcrumb** on every page but Home leads back.
5. **Phones** get four tabs at the bottom (Home, To do, Search, Me), sheets in place of drop-downs, and
   touch targets of 44px or more.
6. **Roles as job titles.** For example "HR Officer · Head of Administration" or "Lecturer, Crop Science",
   never system codes. The campus switch appears only for people who work with more than one campus.
7. **The crest's colours.** A thin yellow band (#fcf303) above a deep green header (#06331f), with GSA
   green (#066938) for actions. Every pairing of text and ground meets WCAG AA. The crest is served from
   the app itself.
8. **Type.** The design names Public Sans. Loading it from Google's servers would send every visitor's
   address to a third party and break the Content-Security-Policy, so the app asks for Public Sans by name
   and falls back to the system's own sans-serif. Shipping the font itself (SIL Open Font Licence 1.1)
   needs a named exception under ADR 0002, and is left for the owner to decide.

## Consequences

- Occasional users rely on Home's shortcuts and on search. Search lists every page a person may open, and
  the journeys open every page through it. Item 2.20, the help centre, adds guides by task.
- Pages not yet redrawn keep their layout inside the new frame. The people list and the employee file (as a
  full page), leave, organisation, reports and admin follow in the next pull requests.
- A superuser made with `createsuperuser` now gets every role in the web app, as the server already allowed.
  Before, the web app showed such an account only an employee's pages.
- The demonstration data gains a fictional Principal account, `principal.office`.
