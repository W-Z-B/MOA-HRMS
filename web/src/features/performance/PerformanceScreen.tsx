import { useCallback, useEffect, useState } from "react";
import { get, plainMessage, post, patch } from "../../api/client";
import {
  PERFORMANCE_OPEN_ROLES,
  PERFORMANCE_SIGN_ROLES,
  hasAnyRole,
  type Appraisal,
  type AppraisalCycle,
  type Me,
  type Paginated,
} from "../../api/types";
import { AppraisalCard } from "./AppraisalCard";
import { NewCycleForm } from "./NewCycleForm";
import { StartAppraisalForm } from "./StartAppraisalForm";

interface Props {
  me: Me;
  path: string;
  onNavigate: (to: string) => void;
}

type Tab = "mine" | "team" | "setup";

/** Performance management (item H-M03): goals, a self-assessment and a manager assessment, driven by
 * the approvals engine (performance.workflow), replacing the read-only F08 scaffold. "Mine" is open to
 * everyone; "Team" to a manager with appraisals to rate; "Setup" (cycles, opening appraisals) to HR. */
export function PerformanceScreen({ me, path, onNavigate }: Props) {
  const query = path.includes("?") ? new URLSearchParams(path.split("?")[1]) : new URLSearchParams();
  const canOpen = hasAnyRole(me, PERFORMANCE_OPEN_ROLES);
  const canSign = hasAnyRole(me, PERFORMANCE_SIGN_ROLES);
  const [tab, setTab] = useState<Tab>((query.get("tab") as Tab) || "mine");
  const [appraisals, setAppraisals] = useState<Appraisal[]>([]);
  const [cycles, setCycles] = useState<AppraisalCycle[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    get<Paginated<Appraisal>>("/performance/appraisals/")
      .then((r) => {
        setAppraisals(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load appraisals.")));
  }, []);

  const loadCycles = useCallback(() => {
    get<Paginated<AppraisalCycle>>("/performance/cycles/")
      .then((r) => setCycles(r.results))
      .catch(() => setCycles([]));
  }, []);

  useEffect(() => {
    load();
    loadCycles();
  }, [load, loadCycles]);

  function goTo(nextTab: Tab) {
    setTab(nextTab);
    setNotice(null);
    onNavigate(`/appraisals?tab=${nextTab}`);
  }

  async function writeSelfAssessment(appraisal: Appraisal, text: string) {
    try {
      await patch<Appraisal>(`/performance/appraisals/${appraisal.id}/self-assessment/`, { self_assessment: text });
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "Could not save that."));
    }
  }

  async function writeManagerAssessment(appraisal: Appraisal, text: string, rating: number, outcome: string) {
    try {
      await patch<Appraisal>(`/performance/appraisals/${appraisal.id}/manager-assessment/`, {
        manager_assessment: text,
        overall_rating: rating,
        outcome,
      });
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "Could not save that."));
    }
  }

  async function act(appraisal: Appraisal, action: string, comment?: string) {
    try {
      await post<Appraisal>(`/performance/appraisals/${appraisal.id}/transition/`, { action, comment });
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "That did not go through."));
    }
  }

  async function addGoal(appraisal: Appraisal, title: string) {
    try {
      await post("/performance/goals/", { employee: appraisal.employee, cycle: appraisal.cycle, title });
      setError(null);
      load();
    } catch (err) {
      setError(plainMessage(err, "Could not add that goal."));
    }
  }

  async function startAppraisal(fields: { employee: number; cycle: number; kind: string }) {
    await post("/performance/appraisals/start/", fields);
    setNotice("Appraisal opened.");
    load();
  }

  async function openCycle(fields: { name: string; year: number; starts: string; ends: string; is_open: boolean }) {
    await post("/performance/cycles/", fields);
    setNotice("Cycle opened.");
    loadCycles();
  }

  const mine = appraisals.filter((a) => a.is_mine);
  const team = appraisals.filter((a) => !a.is_mine && (a.is_rated_by_me || canSign));

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Appraisals</h1>
          <p className="muted lead">Goals, self-assessment and appraisals.</p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Appraisals">
        <button role="tab" aria-selected={tab === "mine"} className={tab === "mine" ? "tab active" : "tab"} onClick={() => goTo("mine")}>
          Mine
        </button>
        <button role="tab" aria-selected={tab === "team"} className={tab === "team" ? "tab active" : "tab"} onClick={() => goTo("team")}>
          Team
        </button>
        {canOpen && (
          <button role="tab" aria-selected={tab === "setup"} className={tab === "setup" ? "tab active" : "tab"} onClick={() => goTo("setup")}>
            Setup
          </button>
        )}
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

      {tab === "mine" &&
        (mine.length === 0 ? (
          <p className="panel-card padded">No appraisal is open for you.</p>
        ) : (
          mine.map((a) => (
            <AppraisalCard
              key={a.id}
              appraisal={a}
              canSign={canSign}
              canSetGoals={false}
              onWriteSelfAssessment={writeSelfAssessment}
              onWriteManagerAssessment={writeManagerAssessment}
              onAction={act}
              onAddGoal={addGoal}
            />
          ))
        ))}

      {tab === "team" &&
        (team.length === 0 ? (
          <p className="panel-card padded">Nobody's appraisal is waiting for you.</p>
        ) : (
          team.map((a) => (
            <AppraisalCard
              key={a.id}
              appraisal={a}
              canSign={canSign}
              canSetGoals={a.is_rated_by_me || canOpen}
              onWriteSelfAssessment={writeSelfAssessment}
              onWriteManagerAssessment={writeManagerAssessment}
              onAction={act}
              onAddGoal={addGoal}
            />
          ))
        ))}

      {tab === "setup" && canOpen && (
        <>
          <NewCycleForm onCreate={openCycle} />
          <StartAppraisalForm cycles={cycles} onCreate={startAppraisal} />
        </>
      )}
    </>
  );
}
