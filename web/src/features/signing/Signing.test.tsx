import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee, EmployeeDocument, LetterPreview, LetterTemplate, Me, SignatureRequest } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { WriteLetter } from "../letters/WriteLetter";
import { MySignatures } from "./MySignatures";
import { SigningPanel } from "./SigningPanel";

const person = (roles: string[]): Me => ({
  id: 3,
  username: "someone",
  name: "Someone",
  roles,
  mfa_required: false,
  mfa_verified: true,
  employee_id: null,
});
const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const asha = { id: 1, campus: 1, first_name: "Asha", full_name: "Asha Persaud", status: "active" } as Employee;

const waiting: SignatureRequest = {
  id: 11,
  document: 90,
  document_title: "Letter of appointment, GSA/HR/2026/0003",
  employee: 1,
  employee_name: "Asha Persaud",
  kind: "accept",
  kind_name: "Accept it",
  statement: "I have read this document and I accept it.",
  message: "Please reply before Monday",
  due_by: "2026-10-12",
  state: "waiting",
  state_name: "Waiting",
  created_at: "2026-10-01T10:00:00Z",
  decided_at: null,
  decline_reason: "",
  requested_by: "Natasha Khan",
  evidence: null,
  download_url: "/api/v1/signing/mine/11/document/",
};
const signed: SignatureRequest = {
  ...waiting,
  id: 12,
  state: "signed",
  state_name: "Signed",
  download_url: "/api/v1/documents/90/download/",
  evidence: {
    signer_name: "Asha Persaud",
    signed_at: "2026-10-02T14:05:00Z",
    statement: "I have read this document and I accept it.",
    document_title: "Letter of appointment, GSA/HR/2026/0003",
    document_version: 1,
    sha256: "3f2a".padEnd(64, "0"),
    method: "password confirmed while signed in",
    source_ip: "10.0.0.5",
    device: "Android phone",
    file_unchanged: true,
  },
};

describe("my signatures", () => {
  it("signs once the sentence is ticked and the password confirms it, after a wrong one", async () => {
    const server = fakeServer({
      "GET /signing/mine/": [page([waiting]), page([{ ...signed, download_url: "/api/v1/signing/mine/12/document/" }])],
      "POST /signing/mine/11/sign/": [
        { status: 400, body: { code: "wrong_password", detail: "That password is not right." } },
        { body: { ...waiting, state: "signed" } },
      ],
    });
    render(<MySignatures />);
    const list = await screen.findByRole("list", { name: "Waiting for your signature" });
    expect(within(list).getByRole("link", { name: "Letter of appointment, GSA/HR/2026/0003" })).toHaveAttribute("href", waiting.download_url);
    expect(within(list).getByText(/by 12\/10\/2026: Please reply before Monday/)).toBeInTheDocument();
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Sign Letter of appointment, GSA/HR/2026/0003" });
    expect(within(form).getByRole("button", { name: "Sign" })).toBeDisabled(); // not until the sentence is ticked
    await user.click(within(form).getByLabelText("I have read this document and I accept it."));
    await user.type(within(form).getByLabelText(/Your password/), "wrong");
    await user.click(within(form).getByRole("button", { name: "Sign" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That password is not right.");
    expect(within(form).getByLabelText(/Your password/)).toHaveValue(""); // cleared after a refusal
    await user.type(within(form).getByLabelText(/Your password/), "the-right-one");
    await user.click(within(form).getByRole("button", { name: "Sign" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Signed: Letter of appointment, GSA/HR/2026/0003.");
    expect(server.calls.filter((c) => c.method === "POST").at(-1)?.body).toEqual({ password: "the-right-one", agree: true });
    expect(await screen.findByRole("list", { name: "Signed or declined" })).toHaveTextContent(/signed 02\/10\/2026/);
  });

  it("declines with a reason, and shows nothing when nothing was ever asked", async () => {
    const server = fakeServer({
      "GET /signing/mine/": [page([waiting]), page([{ ...waiting, state: "declined", state_name: "Declined", decline_reason: "The dates are wrong" }])],
      "POST /signing/mine/11/decline/": { body: { ...waiting, state: "declined" } },
    });
    const { unmount } = render(<MySignatures />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Decline" }));
    await user.type(screen.getByLabelText("Why you do not agree"), "The dates are wrong");
    await user.click(screen.getByRole("button", { name: "Decline to sign" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Human Resources is told why.");
    expect(server.calls.find((c) => c.method === "POST")?.body).toEqual({ reason: "The dates are wrong" });
    unmount();
    fakeServer({ "GET /signing/mine/": page([]) });
    const { container } = render(<MySignatures />);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(container).toBeEmptyDOMElement();
  });
});

const documents = [
  { id: 90, title: "Letter of appointment, GSA/HR/2026/0003", classification: "confidential" },
  { id: 91, title: "Doctor's note", classification: "medical" },
] as EmployeeDocument[];

describe("signatures in the staff file", () => {
  it("shows the evidence, asks for a signature and withdraws one still waiting", async () => {
    const server = fakeServer({
      "GET /signing/requests/": page([signed, { ...signed, id: 13, evidence: { ...signed.evidence!, file_unchanged: false } }, { ...waiting, download_url: "/api/v1/documents/90/download/" }]),
      "POST /signing/requests/": { status: 201, body: waiting },
      "POST /signing/requests/11/withdraw/": { body: { ...waiting, state: "withdrawn" } },
    });
    render(<SigningPanel employee={asha} documents={documents} me={person(["hr_officer"])} version={0} />);
    const list = await screen.findByRole("list", { name: "Signature requests" });
    const [first, second] = within(list).getAllByLabelText("Evidence of the signature");
    expect(first).toHaveTextContent("“I have read this document and I accept it.”");
    expect(first).toHaveTextContent("password confirmed while signed in, on Android phone from 10.0.0.5");
    expect(within(first).getByText("The file still matches")).toBeInTheDocument();
    expect(within(second).getByText("The file has changed since it was signed")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Ask Asha to sign a document" }));
    const form = screen.getByRole("form", { name: "Ask to sign" });
    expect(within(form).queryByRole("option", { name: "Doctor's note" })).not.toBeInTheDocument(); // medical: never
    await user.selectOptions(within(form).getByLabelText("Document"), "90");
    await user.selectOptions(within(form).getByLabelText("Ask them to"), "accept");
    await user.type(within(form).getByLabelText("Note to them (optional)"), "Please reply before Monday");
    await user.click(within(form).getByRole("button", { name: "Send the request" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha is asked to sign, and is told.");
    expect(server.calls.find((c) => c.path === "/signing/requests/" && c.method === "POST")?.body).toEqual({
      document: 90,
      kind: "accept",
      message: "Please reply before Monday",
      due_by: null,
    });

    await user.click(screen.getByRole("button", { name: "Withdraw the request" }));
    const withdraw = screen.getByRole("form", { name: "Withdraw the request for Letter of appointment, GSA/HR/2026/0003" });
    await user.type(within(withdraw).getByLabelText("Why"), "Sent in error");
    await user.click(within(withdraw).getByRole("button", { name: "Withdraw it" }));
    expect(await screen.findByText("The request for Letter of appointment, GSA/HR/2026/0003 is withdrawn.")).toBeInTheDocument();
  });

  it("is hidden from supervisors, and says so when nobody was asked", async () => {
    fakeServer({ "GET /signing/requests/": page([]) });
    const { container, unmount } = render(<SigningPanel employee={asha} documents={documents} me={person(["supervisor"])} version={0} />);
    expect(container).toBeEmptyDOMElement();
    unmount();
    render(<SigningPanel employee={asha} documents={documents} me={person(["principal"])} version={0} />);
    expect(await screen.findByText("Nobody has been asked to sign anything here.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ask Asha to sign/ })).not.toBeInTheDocument();
  });
});

describe("a letter that asks to be signed", () => {
  it("sends the choice with the letter", async () => {
    const template = { id: 7, code: "appointment", name: "Letter of appointment", is_active: true, asks: [] } as unknown as LetterTemplate;
    const preview: LetterPreview = { subject: "Appointment", addressed: true, blocks: [], values: {}, missing: [], classification: "confidential" };
    const server = fakeServer({
      "GET /letters/templates/": page([template]),
      "POST /letters/preview/": { body: preview },
      "POST /letters/": { status: 201, body: { id: 1, reference: "GSA/HR/2026/0003", template_name: "Letter of appointment", download_url: "/x" } },
    });
    render(<WriteLetter employee={asha} onIssued={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Write a letter" }));
    await user.selectOptions(await screen.findByLabelText("Letter"), "7");
    await user.click(screen.getByRole("button", { name: "Read the letter" }));
    await user.selectOptions(await screen.findByLabelText(/Once it is issued, ask Asha to/), "accept");
    await user.click(screen.getByRole("button", { name: "Issue the letter" }));
    expect(await screen.findByRole("status")).toHaveTextContent("is issued");
    expect(server.calls.find((c) => c.path === "/letters/")?.body).toEqual({ employee: 1, template: 7, answers: {}, ask: "accept" });
  });
});
