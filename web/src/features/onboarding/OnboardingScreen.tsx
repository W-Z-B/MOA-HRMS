import { useCallback, useEffect, useState } from "react";
import { get, plainMessage, post } from "../../api/client";
import { ONBOARDING_WRITE_ROLES, hasAnyRole, type Me, type Onboarding, type OnboardingStepCode, type Paginated } from "../../api/types";
import { OnboardingCard } from "./OnboardingCard";
import { StartOnboardingForm } from "./StartOnboardingForm";

interface Props {
  me: Me;
  onNavigate: (to: string) => void;
}

/** Onboarding (item H-W02): the checklist run from an accepted hire through to a full member of staff
 * (people.onboarding, on the approvals engine). HR starts it, confirms documents, issues equipment and
 * opens the account; a new hire's own self-service steps are on their own "My onboarding" page. */
export function OnboardingScreen({ me }: Props) {
  const canWrite = hasAnyRole(me, ONBOARDING_WRITE_ROLES);
  const [records, setRecords] = useState<Onboarding[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Onboarding>>("/onboarding/")
      .then((r) => {
        setRecords(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load onboarding.")));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function start(fields: {
    hire: number;
    employee_no: string;
    date_of_birth: string;
    gender: string;
    appointment_type: string;
    start_date?: string;
  }) {
    await post("/onboarding/start/", fields);
    setNotice("Onboarding started: the staff record and checklist are ready.");
    load();
  }

  async function act(record: Onboarding, action: string, comment?: string) {
    try {
      await post<Onboarding>(`/onboarding/${record.id}/transition/`, { action, comment });
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through."));
    }
  }

  async function clearStep(record: Onboarding, code: OnboardingStepCode, done: boolean) {
    try {
      await post<Onboarding>(`/onboarding/${record.id}/steps/${code}/clear/`, { done });
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "That step could not be closed."));
    }
  }

  async function openAccount(record: Onboarding) {
    try {
      await post<Onboarding>(`/onboarding/${record.id}/open-account/`);
      setNotice("Account opened; the invitation has been sent.");
      load();
    } catch (err) {
      setError(plainMessage(err, "Could not open the account."));
    }
  }

  const open = records.filter((r) => r.state === "in_progress" || r.state === "documents_submitted");
  const closed = records.filter((r) => r.state === "completed" || r.state === "cancelled");

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Onboarding</h1>
          <p className="muted lead">Joining the School: the checklist run from an accepted hire to a full member of staff.</p>
        </div>
      </div>

      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="notice good">
          {notice}
        </p>
      )}

      {canWrite && <StartOnboardingForm onCreate={start} />}

      {open.length === 0 ? (
        <p className="panel-card padded">Nobody is onboarding at the moment.</p>
      ) : (
        open.map((record) => (
          <OnboardingCard key={record.id} record={record} onAction={act} onClearStep={clearStep} onOpenAccount={openAccount} />
        ))
      )}

      {closed.length > 0 && (
        <details className="panel-card padded">
          <summary>Finished ({closed.length})</summary>
          <ul className="rows">
            {closed.map((record) => (
              <li key={record.id} className="item-row">
                <span className="stacked grow">
                  <span className="strong">{record.employee_name}</span>
                  <span className="muted small">{record.state === "cancelled" ? "Cancelled" : "Completed"}</span>
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
