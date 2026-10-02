import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CheckedLetter } from "../../api/types";
import { fakeServer } from "../../test/fetch";
import { CheckLetterScreen } from "./CheckLetterScreen";

const genuine: CheckedLetter = {
  genuine: true,
  detail: "This letter is genuine. Compare its words with the letter you hold.",
  reference: "GSA/HR/2026/0001",
  letter: "Job letter",
  about: "Asha Persaud",
  issued_on: "2026-10-02",
  subject: "Confirmation of employment: Asha Persaud",
  addressed: false,
  blocks: [{ type: "paragraph", lines: [[{ text: "Asha Persaud is employed as a Lecturer.", bold: false }]] }],
  values: {},
  sha256: "ab".repeat(32),
};
const nothing: CheckedLetter = {
  genuine: false,
  detail: "No letter matches that reference and code.",
  reference: null,
  letter: null,
  about: null,
  issued_on: null,
  subject: null,
  addressed: null,
  blocks: null,
  values: null,
  sha256: null,
};

/** The browser's SHA-256, giving back bytes of one value: 0xab makes the letter's own fingerprint. */
const digestOf = (byte: number) =>
  vi.stubGlobal("crypto", { subtle: { digest: vi.fn(async () => new Uint8Array(32).fill(byte).buffer) } });

async function fill(reference: string, code: string) {
  const user = userEvent.setup();
  const form = screen.getByRole("form", { name: "Check a letter" });
  await user.type(within(form).getByLabelText("Reference"), reference);
  await user.type(within(form).getByLabelText("Code"), code);
  await user.click(within(form).getByRole("button", { name: "Check the letter" }));
  return user;
}

describe("checking a letter", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows a genuine letter as issued, and tells whether a PDF file is the very one", async () => {
    const server = fakeServer({ "POST /letters/check/": { body: genuine } });
    const onBack = vi.fn();
    render(<CheckLetterScreen onBack={onBack} />);
    const user = await fill("GSA/HR/2026/0001", "K0Q1-9XMB-4T3V");
    expect(await screen.findByText(/Genuine: Job letter GSA\/HR\/2026\/0001, about Asha Persaud, issued on 02\/10\/2026\./)).toBeInTheDocument();
    expect(server.calls[0].body).toEqual({ reference: "GSA/HR/2026/0001", code: "K0Q1-9XMB-4T3V" });
    const letter = screen.getByRole("article", { name: "The letter" });
    expect(letter).toHaveTextContent("Confirmation of employment: Asha Persaud");
    expect(letter).toHaveTextContent("Asha Persaud is employed as a Lecturer.");

    const choose = screen.getByLabelText(/Choose it to check it is the very file issued/);
    digestOf(0xab);
    await user.upload(choose, new File(["%PDF-1.7"], "letter.pdf", { type: "application/pdf" }));
    expect(await screen.findByText("This file is exactly the one the School issued.")).toBeInTheDocument();
    digestOf(0xcd);
    await user.upload(choose, new File(["%PDF-1.7 changed"], "changed.pdf", { type: "application/pdf" }));
    expect(await screen.findByText(/This file is not the one the School issued/)).toBeInTheDocument();
    vi.stubGlobal("crypto", { subtle: { digest: vi.fn(async () => Promise.reject(new Error("no"))) } });
    await user.upload(choose, new File(["?"], "odd.pdf", { type: "application/pdf" }));
    expect(await screen.findByText("That file could not be read here. Compare the words instead.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Go to the sign-in page" }));
    expect(onBack).toHaveBeenCalled();
  });

  it("says when no letter matches, when too many codes were tried, and when the server is out of reach", async () => {
    fakeServer({
      "POST /letters/check/": [
        { body: nothing },
        { status: 429, body: { code: "too_many_attempts", detail: "Too many wrong codes have been tried. Try again in 15 minutes." } },
        () => {
          throw new TypeError("Failed to fetch");
        },
      ],
    });
    render(<CheckLetterScreen onBack={vi.fn()} />);
    const user = await fill("GSA/HR/2026/0009", "AAAA-AAAA-AAAA");
    expect(await screen.findByRole("alert")).toHaveTextContent("No letter matches that reference and code.");
    expect(screen.queryByRole("article", { name: "The letter" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check the letter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many wrong codes have been tried.");
    await user.click(screen.getByRole("button", { name: "Check the letter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the School's server.");
  });
});
