import { useState } from "react";
import { plainMessage } from "../../api/client";

/** One change at a time: busy while it runs, then the server's words, good or bad, and a reload. */
export function useAction(reload: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function run(work: () => Promise<string>): Promise<boolean> {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setNotice(await work());
      reload();
      return true;
    } catch (err) {
      setError(plainMessage(err, "That did not go through. Try again."));
      return false;
    } finally {
      setBusy(false);
    }
  }

  return { busy, error, notice, setError, run };
}
