import type { PreviousEmployment, Qualification } from "../../api/types";
import { dmy } from "../../app/format";
import { RecordList } from "./RecordList";

const LEVELS = [
  ["certificate", "Certificate"],
  ["diploma", "Diploma"],
  ["associate", "Associate degree"],
  ["bachelor", "Bachelor's degree"],
  ["postgraduate", "Postgraduate diploma or certificate"],
  ["master", "Master's degree"],
  ["doctorate", "Doctorate"],
  ["professional", "Professional qualification or licence"],
  ["other", "Other"],
].map(([value, label]) => ({ value, label }));

/** Qualifications and work before GSA. */
export function BackgroundTab({ employeeId, canEdit }: { employeeId: number; canEdit: boolean }) {
  return (
    <>
      <RecordList<Qualification>
        title="Qualifications"
        endpoint="/qualifications/"
        employeeId={employeeId}
        canEdit={canEdit}
        emptyText="No qualifications recorded."
        addLabel="Add a qualification"
        nameOf={(q) => q.title}
        fields={[
          { name: "level", label: "Level", type: "select", options: LEVELS, required: true },
          { name: "title", label: "Title, as on the certificate", required: true },
          { name: "institution", label: "Institution", required: true },
          { name: "country", label: "Country" },
          { name: "year_awarded", label: "Year awarded", type: "number" },
          { name: "verified_on", label: "Original seen by HR on", type: "date" },
        ]}
        describe={(q) => (
          <>
            <strong>{q.title}</strong>, {q.institution}
            {q.country && q.country !== "Guyana" ? `, ${q.country}` : ""}
            <br />
            <span className="muted small">
              {q.level_name}
              {q.year_awarded ? ` · ${q.year_awarded}` : ""}
              {q.verified_on ? ` · original seen ${dmy(q.verified_on)}` : " · original not yet seen"}
            </span>
          </>
        )}
      />
      <RecordList<PreviousEmployment>
        title="Work before GSA"
        endpoint="/previous-employment/"
        employeeId={employeeId}
        canEdit={canEdit}
        emptyText="No earlier employment recorded."
        addLabel="Add earlier employment"
        nameOf={(p) => `${p.position}, ${p.employer}`}
        fields={[
          { name: "employer", label: "Employer", required: true },
          { name: "position", label: "Position", required: true },
          { name: "start_date", label: "From", type: "date", required: true },
          { name: "end_date", label: "To", type: "date" },
          { name: "reason_for_leaving", label: "Reason for leaving" },
        ]}
        describe={(p) => (
          <>
            <strong>{p.position}</strong>, {p.employer}
            <br />
            <span className="muted small">
              {dmy(p.start_date)} to {p.end_date ? dmy(p.end_date) : "not recorded"}
              {p.reason_for_leaving ? ` · ${p.reason_for_leaving}` : ""}
            </span>
          </>
        )}
      />
    </>
  );
}
