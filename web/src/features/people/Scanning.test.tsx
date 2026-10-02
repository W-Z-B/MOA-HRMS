import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { Employee, ScanBatch, ScanItem } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { ScanningScreen } from "./ScanningScreen";

const page = <T,>(results: T[]) => ({ body: { count: results.length, next: null, previous: null, results } });
const batch: ScanBatch = {
  id: 3,
  doc_type: "contract",
  doc_type_name: "Contract",
  classification: "confidential",
  note: "Cabinet 2",
  created_by_name: "Natasha Khan",
  created_at: "2026-10-02T10:00:00-04:00",
  filed: 0,
  not_filed: 0,
};
const filed: ScanItem = {
  id: 1,
  name: "E0001 Appointment 2014.pdf",
  employee: 1,
  employee_name: "Asha Persaud",
  employee_no: "E0001",
  document: 50,
  document_title: "Appointment 2014",
  filed: true,
  refused: "",
  at: "2026-10-02T10:01:00-04:00",
};
const unplaced: ScanItem = {
  ...filed,
  id: 2,
  name: "scan_0042.pdf",
  employee: null,
  employee_name: null,
  employee_no: null,
  document: null,
  document_title: null,
  filed: false,
  refused: "The name does not start with an employee number. Choose whose file it is.",
};
const staff = [{ id: 1, full_name: "Asha Persaud", employee_no: "E0001" }] as Employee[];
const pdf = (name: string) => new File(["%PDF-1.4"], name, { type: "application/pdf" });

describe("filing scanned papers", () => {
  it("files a pile into the records its names give, and lets HR place the rest", async () => {
    const server = fakeServer({
      "GET /scan-batches/": [page([]), page([{ ...batch, filed: 1, not_filed: 1 }])],
      "GET /employees/": page(staff),
      "POST /scan-batches/": [{ status: 400, body: { classification: ["A contract is filed as Confidential or Medical."] } }, { status: 201, body: batch }],
      "POST /scan-batches/3/files/": [{ body: filed }, { body: unplaced }, { body: { ...unplaced, id: 3, employee: 1, employee_name: "Asha Persaud", employee_no: "E0001", document: 51, document_title: "scan 0042", filed: true, refused: "" } }],
    });
    const onNavigate = vi.fn();
    render(<ScanningScreen onNavigate={onNavigate} />);
    const user = userEvent.setup();
    const form = screen.getByRole("form", { name: "Begin a batch" });
    await user.selectOptions(within(form).getByLabelText("The papers are"), "medical");
    expect(within(form).getByLabelText("Classification")).toHaveValue("medical");
    expect(within(within(form).getByLabelText("Classification")).queryByRole("option", { name: "Internal" })).not.toBeInTheDocument();
    await user.selectOptions(within(form).getByLabelText("The papers are"), "contract");
    await user.type(within(form).getByLabelText(/Note/), "Cabinet 2");
    await user.click(within(form).getByRole("button", { name: "Begin" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A contract is filed as Confidential or Medical.");
    await user.click(within(form).getByRole("button", { name: "Begin" }));
    expect(await screen.findByRole("heading", { name: "Contract, confidential: Cabinet 2" })).toBeInTheDocument();
    expect(server.calls.filter((c) => c.path === "/scan-batches/" && c.method === "POST").at(-1)?.body).toEqual({
      doc_type: "contract",
      classification: "confidential",
      note: "Cabinet 2",
    });

    await user.upload(screen.getByLabelText(/Choose the scanned files/), [pdf("E0001 Appointment 2014.pdf"), pdf("scan_0042.pdf")]);
    expect(await screen.findByText("1 of 2 filed.")).toBeInTheDocument();
    const files = screen.getByRole("list", { name: "Files in this batch" });
    expect(files).toHaveTextContent("filed in the record of Asha Persaud (E0001) as “Appointment 2014”");
    expect(files).toHaveTextContent("The name does not start with an employee number.");
    const place = screen.getByRole("form", { name: "Choose whose file scan_0042.pdf belongs in" });
    await within(place).findByRole("option", { name: "Asha Persaud (E0001)" });
    await user.selectOptions(within(place).getByLabelText("Whose file"), "1");
    await user.click(within(place).getByRole("button", { name: "File it there" }));
    expect(await screen.findByText("2 of 2 filed.")).toBeInTheDocument();
    const sent = server.calls.filter((c) => c.path === "/scan-batches/3/files/");
    expect(sent).toHaveLength(3);
    expect((sent[2].body as FormData).get("employee")).toBe("1");
    expect(((sent[2].body as FormData).get("file") as File).name).toBe("scan_0042.pdf");
    expect(await screen.findByRole("table", { name: "Batches filed" })).toHaveTextContent("Cabinet 2");

    await user.click(screen.getByRole("button", { name: "Finish this batch" }));
    expect(screen.getByRole("form", { name: "Begin a batch" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to People" }));
    expect(onNavigate).toHaveBeenCalledWith("/people");
  });

  it("says when a file could not be sent at all, or placing one is refused", async () => {
    fakeServer({
      "GET /scan-batches/": page([]),
      "GET /employees/": page(staff),
      "POST /scan-batches/": { status: 201, body: batch },
      "POST /scan-batches/3/files/": [
        { body: unplaced },
        { status: 413, body: { detail: "The file is too large." } },
        { body: { ...unplaced, refused: "Already filed as “Appointment 2014” on 02/10/2026." } },
      ],
    });
    render(<ScanningScreen onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Begin" }));
    await user.upload(await screen.findByLabelText(/Choose the scanned files/), [pdf("scan_0042.pdf"), pdf("huge.pdf")]);
    expect(await screen.findByText("0 of 2 filed.")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Files in this batch" })).toHaveTextContent("The file is too large.");
    const place = screen.getByRole("form", { name: "Choose whose file scan_0042.pdf belongs in" });
    await within(place).findByRole("option", { name: "Asha Persaud (E0001)" });
    await user.selectOptions(within(place).getByLabelText("Whose file"), "1");
    await user.click(within(place).getByRole("button", { name: "File it there" }));
    expect(await within(place).findByRole("alert")).toHaveTextContent("Already filed as “Appointment 2014”");
  });
});
