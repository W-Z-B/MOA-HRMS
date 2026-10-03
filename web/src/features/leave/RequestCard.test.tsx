import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { LeaveRequest } from "../../api/types";
import { RequestCard } from "./RequestCard";

const request = (over: Partial<LeaveRequest> = {}): LeaveRequest => ({
  id: 21,
  employee: 7,
  employee_name: "Devon Charles",
  is_mine: false,
  leave_type: 2,
  leave_type_code: "SIC",
  leave_type_name: "Sick leave",
  from_date: "2026-09-21",
  to_date: "2026-09-22",
  days: "2.00",
  days_beyond: "0.00",
  reason: "Medical certificate to follow",
  state: "supervisor_approved",
  evidence_name: "Doctor's note",
  evidence_required: false,
  has_evidence: false,
  manager_name: "Natasha Khan",
  decision_comment: "",
  decisions: [{ step: "manager", step_name: "Manager", outcome: "approved", actor_name: "Natasha Khan", comment: "", decided_at: "2026-09-21T09:12:00Z" }],
  allowed_actions: ["approve", "reject"],
  balance_after: "12.00",
  receipt: null,
  ...over,
});

function card(r: LeaveRequest, view: "mine" | "decide" = "decide") {
  const onAction = vi.fn(async () => undefined);
  const onReceipt = vi.fn();
  render(
    <RequestCard
      request={r}
      view={view}
      canOpenNote
      highlighted={false}
      onAction={onAction}
      onAttach={vi.fn(async () => undefined)}
      onReceipt={onReceipt}
    />,
  );
  return { onAction, onReceipt };
}

describe("a request to decide", () => {
  it("is approved in one step, and shows where it is and what it leaves", async () => {
    const { onAction } = card(request());
    const article = screen.getByRole("article");
    expect(article).toHaveTextContent("Devon CharlesSick leave");
    expect(article).toHaveTextContent("With Human Resources");
    expect(within(article).getByRole("list")).toHaveTextContent(/Manager.*Natasha Khan/);
    expect(article).toHaveTextContent("Leaves 12 days of sick leave.");
    await userEvent.setup().click(screen.getByRole("button", { name: "Approve" }));
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ id: 21 }), "approve", "");
  });

  it("asks for the reason the employee will see only when Reject is chosen, and can go back", async () => {
    const { onAction } = card(request());
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    const form = screen.getByRole("form", { name: "Reject sick leave for Devon Charles" });
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
    expect(within(form).getByRole("button", { name: "Reject request" })).toBeDisabled();
    await user.click(within(form).getByRole("button", { name: "Back" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reject" }));
    await user.type(screen.getByLabelText("Reason for rejecting. Devon will see it."), "  Cover is needed that week  ");
    await user.click(screen.getByRole("button", { name: "Reject request" }));
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ id: 21 }), "reject", "Cover is needed that week");
  });
});

describe("one's own request", () => {
  it("is sent or cancelled, and an approved one opens its receipt", async () => {
    const { onAction } = card(request({ is_mine: true, state: "draft", decisions: [], allowed_actions: ["submit", "cancel"] }), "mine");
    expect(screen.getByRole("article")).toHaveTextContent("Draft, not sent");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Cancel request" }));
    expect(onAction).toHaveBeenCalledWith(expect.objectContaining({ id: 21 }), "cancel", "");
  });

  it("says why it was rejected", () => {
    card(request({ is_mine: true, state: "rejected", decision_comment: "Cover is needed", allowed_actions: [] }), "mine");
    expect(screen.getByText(/Reason given:/).parentElement).toHaveTextContent("Reason given: Cover is needed");
  });
});
