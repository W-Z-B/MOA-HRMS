import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { DocumentUpload } from "./DocumentUpload";

const employee = { id: 1 } as Employee;
const pdf = () => new File(["%PDF-1.7"], "scan.pdf", { type: "application/pdf" });

describe("filing a document", () => {
  it("raises the classification to what the type needs, and files it as chosen", async () => {
    const server = fakeServer({ "POST /documents/": { status: 201, body: {} } });
    const onSaved = vi.fn();
    render(<DocumentUpload employee={employee} onSaved={onSaved} />);
    const user = userEvent.setup();
    const classification = screen.getByLabelText("Classification");
    await user.selectOptions(screen.getByLabelText("Type"), "contract");
    expect(classification).toHaveValue("confidential");
    expect(screen.getByRole("option", { name: "Internal: anyone who reads staff files" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Type"), "medical");
    expect(classification).toHaveValue("medical");
    expect(screen.getByRole("option", { name: "Confidential: HR, the Principal and the auditor" })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Type"), "certificate");
    expect(classification).toHaveValue("medical"); // never lowered by itself
    await user.selectOptions(classification, "internal");
    await user.type(screen.getByLabelText("Title"), "BSc certificate");
    await user.upload(screen.getByLabelText("File"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(onSaved).toHaveBeenCalled();
    const sent = server.calls[0].body as FormData;
    expect([sent.get("doc_type"), sent.get("classification"), sent.get("title")]).toEqual(["certificate", "internal", "BSc certificate"]);
  });

  it("says why an upload was refused", async () => {
    fakeServer({ "POST /documents/": { status: 400, body: { classification: ["A contract is filed as Confidential or Medical."] } } });
    render(<DocumentUpload employee={employee} onSaved={vi.fn()} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Title"), "Contract");
    await user.upload(screen.getByLabelText("File"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Confidential or Medical");
  });
});
