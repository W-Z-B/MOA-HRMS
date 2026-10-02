import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee, Letter, LetterPreview, LetterTemplate, Me } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { LettersScreen } from "./LettersScreen";
import { MyLetters } from "./MyLetters";
import { WriteLetter } from "./WriteLetter";

const person = (roles: string[]): Me => ({
  id: 3,
  username: "hr.person",
  name: "HR Person",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const asha = { id: 1, first_name: "Asha", full_name: "Asha Persaud" } as Employee;

const jobLetter: LetterTemplate = {
  id: 7,
  code: "job_letter",
  version: 1,
  kind: "job_letter",
  kind_name: "Job letter",
  name: "Job letter",
  subject: "Confirmation of employment: {{full_name}}",
  body: "To whom it may concern,\n\nThis is to confirm that **{{full_name}}** works here, for {{purpose}}.",
  asks: [{ key: "purpose", label: "What the letter is for", type: "text" }],
  addressed: false,
  classification: "internal",
  classification_name: "Internal",
  signatory_name: "",
  signatory_title: "Human Resources Manager",
  is_active: true,
  fields_used: ["full_name", "purpose"],
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
};
const transfer: LetterTemplate = {
  ...jobLetter,
  id: 8,
  code: "transfer",
  kind: "transfer",
  kind_name: "Transfer",
  name: "Transfer",
  addressed: true,
  classification: "confidential",
  classification_name: "Confidential",
  asks: [{ key: "effective_date", label: "Takes effect on", type: "date" }],
  is_active: false,
};

const draft = (purpose: string): LetterPreview => ({
  subject: "Confirmation of employment: Asha Persaud",
  addressed: false,
  blocks: [
    { type: "paragraph", lines: [[{ text: "To whom it may concern,", bold: false }]] },
    {
      type: "paragraph",
      lines: [
        [
          { text: "This is to confirm that ", bold: false },
          { text: "Asha Persaud", bold: true },
          { text: ` works here, for ${purpose}.`, bold: false },
        ],
      ],
    },
    { type: "list", items: [[{ text: "Lecturer", bold: false }]] },
  ],
  values: { full_name: "Asha Persaud", purpose },
  missing: purpose ? [] : [{ key: "purpose", label: "What the letter is for", asked: true }],
  classification: "internal",
});

const issued: Letter = {
  id: 40,
  reference: "GSA/HR/2026/0001",
  employee: 1,
  employee_name: "Asha Persaud",
  employee_no: "E0001",
  template: 7,
  template_name: "Job letter",
  template_version: 1,
  kind: "job_letter",
  issued_on: "2026-10-01",
  issued_by: "Natasha Khan",
  sha256: "ab".repeat(32),
  document: 90,
  download_url: "/api/v1/letters/40/download/",
  check_code: "K0Q1-9XMB-4T3V",
  times_checked: 0,
  last_checked_at: null,
};

describe("writing a letter", () => {
  it("reads the letter, says what it lacks, and issues it once nothing is missing", async () => {
    const server = fakeServer({
      "GET /letters/templates/": page([jobLetter, transfer]),
      "POST /letters/preview/": [{ body: draft("") }, { body: draft("a bank loan") }],
      "POST /letters/": { status: 201, body: issued },
    });
    const onIssued = vi.fn();
    render(<WriteLetter employee={asha} onIssued={onIssued} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Write a letter" }));
    const letter = await screen.findByLabelText("Letter");
    expect(within(letter).queryByRole("option", { name: "Transfer" })).not.toBeInTheDocument(); // out of use
    await user.selectOptions(letter, "7");
    await user.click(screen.getByRole("button", { name: "Read the letter" }));
    expect(await screen.findByText("Answer: What the letter is for")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Issue the letter" })).toBeDisabled();

    await user.type(screen.getByLabelText("What the letter is for"), "a bank loan");
    expect(screen.queryByRole("article", { name: "The letter" })).not.toBeInTheDocument(); // read it again
    await user.click(screen.getByRole("button", { name: "Read the letter" }));
    const paper = await screen.findByRole("article", { name: "The letter" });
    expect(within(paper).getByText("Asha Persaud", { selector: "strong" })).toBeInTheDocument();
    expect(within(paper).getByRole("listitem")).toHaveTextContent("Lecturer");
    expect(screen.getByText(/filed as Internal with the documents, and Asha can read it/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Issue the letter" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Job letter GSA/HR/2026/0001 is issued");
    expect(screen.getByRole("link", { name: "Download it" })).toHaveAttribute("href", issued.download_url);
    expect(onIssued).toHaveBeenCalled();
    expect(server.calls.find((c) => c.path === "/letters/")?.body).toEqual({ employee: 1, template: 7, answers: { purpose: "a bank loan" } });
  });

  it("says why a letter was not issued, and closes", async () => {
    fakeServer({
      "GET /letters/templates/": page([{ ...transfer, is_active: true }]),
      "POST /letters/preview/": { body: { ...draft("x"), addressed: true, values: { full_name: "Asha Persaud", post_title: "Lecturer", unit: "Livestock Unit", campus: "Mon Repos Campus" } } },
      "POST /letters/": { status: 409, body: { code: "changed", detail: "The template was changed since the letter was begun. Look at the letter again." } },
    });
    render(<WriteLetter employee={asha} onIssued={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Write a letter" }));
    await user.selectOptions(await screen.findByLabelText("Letter"), "8");
    expect(screen.getByLabelText("Takes effect on")).toHaveAttribute("type", "date");
    await user.click(screen.getByRole("button", { name: "Read the letter" }));
    expect(await screen.findByRole("article", { name: "The letter" })).toHaveTextContent("Asha PersaudLecturerLivestock Unit, Mon Repos Campus");
    await user.click(screen.getByRole("button", { name: "Issue the letter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Look at the letter again.");
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.getByRole("button", { name: "Write a letter" })).toBeInTheDocument();
  });
});

describe("the letters screen", () => {
  it("lists the letters issued and finds one", async () => {
    const checked = { ...issued, id: 41, reference: "GSA/HR/2026/0002", times_checked: 2, last_checked_at: "2026-10-02T09:00:00-04:00" };
    const older = { ...issued, id: 39, reference: "GSA/HR/2026/0000", check_code: null };
    const server = fakeServer({ "GET /letters/": page([checked, issued, older]), "GET /letters/?q=E0001": page([issued]) });
    render(<LettersScreen me={person(["hr_officer"])} path="/letters" onNavigate={vi.fn()} />);
    const table = await screen.findByRole("table", { name: "Letters issued" });
    expect(within(table).getByRole("link", { name: "GSA/HR/2026/0001" })).toHaveAttribute("href", issued.download_url);
    expect(within(table).getAllByText(/by Natasha Khan/)).toHaveLength(3);
    const rows = within(table).getAllByRole("row");
    expect(rows[1]).toHaveTextContent("K0Q1-9XMB-4T3V checked 2 times, last 02/10/2026");
    expect(rows[2]).toHaveTextContent("K0Q1-9XMB-4T3V not checked yet");
    expect(rows[3]).toHaveTextContent("No code: issued before letters carried one");
    await userEvent.setup().type(screen.getByRole("searchbox", { name: "Find a letter" }), "E0001");
    await vi.waitFor(() => expect(server.calls.some((c) => c.path === "/letters/?q=E0001")).toBe(true));
  });

  it("says when no letter has been issued, and opens the templates", async () => {
    fakeServer({ "GET /letters/": page([]) });
    const onNavigate = vi.fn();
    render(<LettersScreen me={person(["principal"])} path="/letters" onNavigate={onNavigate} />);
    expect(await screen.findByText("No letters have been issued yet.")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Templates" }));
    expect(onNavigate).toHaveBeenCalledWith("/letters/templates");
  });

  it("shows HR the templates to read, without changing them", async () => {
    fakeServer({ "GET /letters/templates/": page([jobLetter, transfer]) });
    render(<LettersScreen me={person(["hr_officer"])} path="/letters/templates" onNavigate={vi.fn()} />);
    const list = await screen.findByRole("list", { name: "Letter templates" });
    expect(within(list).getByText("Out of use")).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Read the wording of Job letter" }));
    expect(screen.getByText(/This is to confirm that/)).toBeInTheDocument();
    expect(screen.getByText("Asks for: What the letter is for.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change Job letter" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add a template" })).not.toBeInTheDocument();
  });

  it("lets the HR Manager add a template, hearing every problem, then change one and put it out of use", async () => {
    const server = fakeServer({
      "GET /letters/templates/": page([jobLetter]),
      "GET /letters/templates/fields/": {
        body: { record: [{ key: "monthly_salary", label: "Monthly salary", pay: true }], ask_types: [{ value: "text", label: "Words" }] },
      },
      "POST /letters/templates/": [
        { status: 400, body: { body: ["{{x}}: not a field from the staff record."], asks: ["Asked but not used in the letter: Why."] } },
        { status: 201, body: { ...jobLetter, id: 9, code: "study_leave", name: "Study leave", version: 1 } },
      ],
      "POST /letters/templates/7/revise/": { status: 201, body: { ...jobLetter, version: 2 } },
      "POST /letters/templates/7/in-use/": { body: { ...jobLetter, is_active: false } },
    });
    render(<LettersScreen me={person(["hr_manager"])} path="/letters/templates" onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Add a template" }));
    const form = screen.getByRole("form", { name: "New letter template" });
    await user.type(within(form).getByLabelText("Name"), "Study leave");
    await user.type(within(form).getByLabelText("Code"), "study_leave");
    await user.type(within(form).getByLabelText("Subject"), "Study leave");
    await user.type(within(form).getByLabelText("Wording"), "Dear {{{{first_name}},");
    await user.click(within(form).getByRole("button", { name: "Add a question" }));
    await user.type(within(form).getByLabelText("Field"), "why");
    await user.type(within(form).getByLabelText("Question"), "Why");
    await user.selectOptions(within(form).getByLabelText("Answer"), "date");
    await user.click(within(form).getByText("Fields from the staff record"));
    expect(within(form).getByText(/pay: file the letter as Confidential/)).toBeInTheDocument();
    await user.click(within(form).getByRole("button", { name: "Save the template" }));
    const problems = await screen.findByRole("alert");
    expect(problems).toHaveTextContent("body: {{x}}: not a field from the staff record.");
    expect(problems).toHaveTextContent("asks: Asked but not used in the letter: Why.");
    await user.click(within(form).getByRole("button", { name: "Remove this question" }));
    await user.click(within(form).getByRole("button", { name: "Save the template" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Study leave saved as version 1.");
    const sent = server.calls.filter((c) => c.path === "/letters/templates/" && c.method === "POST");
    expect(sent[0].body).toMatchObject({ code: "study_leave", body: "Dear {{first_name}},", asks: [{ key: "why", label: "Why", type: "date" }] });
    expect(sent[1].body).toMatchObject({ asks: [] });

    await user.click(screen.getByRole("button", { name: "Change Job letter" }));
    const change = screen.getByRole("form", { name: "Change Job letter" });
    expect(within(change).getByText("Change Job letter: it becomes version 2")).toBeInTheDocument();
    expect(within(change).queryByLabelText("Code")).not.toBeInTheDocument();
    await user.click(within(change).getByRole("button", { name: "Save the template" }));
    expect(await screen.findByText("Job letter saved as version 2.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Take Job letter out of use" }));
    expect(await screen.findByText("Job letter is out of use: no new letter is written from it.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.path === "/letters/templates/7/in-use/")?.body).toEqual({ is_active: false });
  });
});

describe("my letters", () => {
  it("lists the letters issued to me, or says there are none", async () => {
    fakeServer({ "GET /letters/mine/": [page([{ ...issued, download_url: "/api/v1/letters/mine/40/download/" }]), page([])] });
    const { unmount } = render(<MyLetters />);
    const mine = await screen.findByRole("list", { name: "My letters" });
    expect(within(mine).getByRole("link", { name: "Job letter" })).toHaveAttribute("href", "/api/v1/letters/mine/40/download/");
    expect(within(mine).getByText("GSA/HR/2026/0001 · 01/10/2026")).toBeInTheDocument();
    unmount();
    render(<MyLetters />);
    expect(await screen.findByText("No letters have been issued to you yet.")).toBeInTheDocument();
  });
});
