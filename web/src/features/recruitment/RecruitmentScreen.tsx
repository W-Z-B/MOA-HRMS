import { useCallback, useEffect, useState } from "react";
import { get, plainMessage, post } from "../../api/client";
import {
  RECRUITMENT_READ_ROLES,
  RECRUITMENT_WRITE_ROLES,
  hasAnyRole,
  type Application,
  type Interview,
  type Me,
  type Paginated,
  type Vacancy,
} from "../../api/types";
import { dmyTime } from "../../app/format";
import { ApplicationCard } from "./ApplicationCard";
import { NewApplicationForm } from "./NewApplicationForm";
import { NewVacancyForm } from "./NewVacancyForm";

interface Props {
  me: Me;
  path: string;
  campusId: number | null;
  onNavigate: (to: string) => void;
}

type Tab = "vacancies" | "applications" | "interviews";

const VACANCY_STATE_CLASS: Record<string, string> = { open: "chip-approved", closed: "chip-rejected" };

/** Recruitment (item H-W01, Phase B): vacancies against an approved post, applications through to a
 * decision, interview scheduling with no double-booking, and the bare hire a decided offer leaves behind
 * for onboarding (H-W02, a later phase) to pick up. */
export function RecruitmentScreen({ me, path, campusId, onNavigate }: Props) {
  const query = path.includes("?") ? new URLSearchParams(path.split("?")[1]) : new URLSearchParams();
  const canRead = hasAnyRole(me, RECRUITMENT_READ_ROLES);
  const canWrite = hasAnyRole(me, RECRUITMENT_WRITE_ROLES);
  const [tab, setTab] = useState<Tab>((query.get("tab") as Tab) || "vacancies");
  const [vacancyId, setVacancyId] = useState<number | null>(query.get("vacancy") ? Number(query.get("vacancy")) : null);
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadVacancies = useCallback(() => {
    get<Paginated<Vacancy>>("/recruitment/vacancies/")
      .then((r) => {
        setVacancies(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load vacancies.")));
  }, []);

  const loadApplications = useCallback(() => {
    if (vacancyId === null) return;
    get<Paginated<Application>>(`/recruitment/applications/?vacancy=${vacancyId}`)
      .then((r) => {
        setApplications(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load applications.")));
  }, [vacancyId]);

  const loadInterviews = useCallback(() => {
    get<Paginated<Interview>>("/recruitment/interviews/")
      .then((r) => {
        setInterviews(r.results);
        setError(null);
      })
      .catch((err) => setError(plainMessage(err, "Could not load interviews.")));
  }, []);

  useEffect(() => {
    if (tab === "vacancies") loadVacancies();
    else if (tab === "applications") loadApplications();
    else loadInterviews();
  }, [tab, loadVacancies, loadApplications, loadInterviews]);

  function goTo(nextTab: Tab, vacancy?: number) {
    setTab(nextTab);
    setNotice(null);
    if (vacancy !== undefined) setVacancyId(vacancy);
    const parts = [`tab=${nextTab}`, ...(vacancy !== undefined ? [`vacancy=${vacancy}`] : [])];
    onNavigate(`/recruitment?${parts.join("&")}`);
  }

  async function createVacancy(fields: { position: number; title: string; opens_on: string; closes_on: string }) {
    try {
      await post("/recruitment/vacancies/", fields);
      setNotice("Vacancy posted.");
      setError(null);
      loadVacancies();
    } catch (err) {
      setError(plainMessage(err, "Could not post that vacancy."));
    }
  }

  async function act(application: Application, action: string, comment?: string) {
    try {
      await post<Application>(`/recruitment/applications/${application.id}/transition/`, { action, comment });
      setError(null);
      loadApplications();
    } catch (err) {
      setError(plainMessage(err, "That did not go through."));
    }
  }

  async function cancelInterview(interview: Interview) {
    try {
      await post(`/recruitment/interviews/${interview.id}/cancel/`);
      setNotice("Interview cancelled; the candidate and the interviewer have been told.");
      loadInterviews();
    } catch (err) {
      setError(plainMessage(err, "Could not cancel that interview."));
    }
  }

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>Recruitment</h1>
          <p className="muted lead">Vacancies, applications and interviews.</p>
        </div>
      </div>

      <div className="tabs" role="tablist" aria-label="Recruitment">
        <button role="tab" aria-selected={tab === "vacancies"} className={tab === "vacancies" ? "tab active" : "tab"} onClick={() => goTo("vacancies")}>
          Vacancies
        </button>
        <button
          role="tab"
          aria-selected={tab === "applications"}
          className={tab === "applications" ? "tab active" : "tab"}
          onClick={() => goTo("applications", vacancyId ?? undefined)}
        >
          Applications
        </button>
        <button role="tab" aria-selected={tab === "interviews"} className={tab === "interviews" ? "tab active" : "tab"} onClick={() => goTo("interviews")}>
          Interviews
        </button>
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

      {tab === "vacancies" && (
        <>
          {canWrite && <NewVacancyForm campusId={campusId} onCreate={createVacancy} />}
          {vacancies.length === 0 ? (
            <p className="panel-card padded">No vacancies yet.</p>
          ) : (
            <ul className="rows">
              {vacancies.map((v) => (
                <li key={v.id} className="item-row">
                  <span className="stacked grow">
                    <span className="strong">{v.title}</span>
                    <span className="muted small">
                      {v.grade_label} · {v.campus_name} · {v.opens_on} to {v.closes_on}
                    </span>
                  </span>
                  <span className={`chip ${VACANCY_STATE_CLASS[v.state] ?? ""}`}>{v.state}</span>
                  <button type="button" className="secondary small-button" onClick={() => goTo("applications", v.id)}>
                    Applications
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {tab === "applications" && (
        <>
          {vacancyId === null ? (
            <p className="panel-card padded">Choose a vacancy from the Vacancies tab first.</p>
          ) : (
            <>
              {canWrite && <NewApplicationForm vacancyId={vacancyId} onCreated={() => loadApplications()} />}
              {!canRead ? null : applications.length === 0 ? (
                <p className="panel-card padded">No applications for this vacancy yet.</p>
              ) : (
                applications.map((a) => (
                  <ApplicationCard key={a.id} application={a} onAction={act} onScheduled={loadApplications} />
                ))
              )}
            </>
          )}
        </>
      )}

      {tab === "interviews" &&
        (interviews.length === 0 ? (
          <p className="panel-card padded">No interviews scheduled.</p>
        ) : (
          <ul className="rows">
            {interviews.map((interview) => (
              <li key={interview.id} className="item-row">
                <span className="stacked grow">
                  <span className="strong">{interview.candidate_name}</span>
                  <span className="muted small">
                    {interview.interviewer_name} · {dmyTime(interview.starts_at)}–{dmyTime(interview.ends_at).split(" ").pop()}
                    {interview.location && ` · ${interview.location}`}
                  </span>
                </span>
                <span className={`chip ${interview.state === "cancelled" ? "chip-rejected" : "chip-waiting"}`}>{interview.state}</span>
                {canWrite && interview.state === "scheduled" && (
                  <button type="button" className="secondary small-button" onClick={() => cancelInterview(interview)}>
                    Cancel
                  </button>
                )}
              </li>
            ))}
          </ul>
        ))}
    </>
  );
}
