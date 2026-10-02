import { useEffect, useState } from "react";
import { errorMessage, get } from "../../api/client";
import { HR_ROLES, hasAnyRole, type Employee, type Me } from "../../api/types";
import { useCrumb } from "../../app/frame";
import { EmployeeForm } from "./EmployeeForm";

interface Props {
  me: Me;
  /** The file to edit; none for a new employee. */
  employeeId: number | null;
  campusId: number | null;
  onNavigate: (to: string) => void;
}

/** A new staff file, or the details of one, as a page of its own (item 2.30). */
export function EmployeeFormPage({ me, employeeId, campusId, onNavigate }: Props) {
  const [existing, setExisting] = useState<Employee | null>(null);
  const [error, setError] = useState<string | null>(null);
  useCrumb(employeeId === null ? "New employee" : existing?.full_name);

  useEffect(() => {
    if (employeeId === null) return;
    let current = true;
    get<Employee>(`/employees/${employeeId}/`)
      .then((e) => current && setExisting(e))
      .catch((err) => current && setError(errorMessage(err, "Could not open this file.")));
    return () => {
      current = false;
    };
  }, [employeeId]);

  const back = employeeId === null ? "/people" : `/people/${employeeId}`;
  if (!hasAnyRole(me, HR_ROLES))
    return (
      <>
        <h1>Staff details</h1>
        <p className="muted">Only Human Resources opens and changes staff files.</p>
      </>
    );

  return (
    <>
      <div className="page-head">
        <div className="stacked">
          <h1>{employeeId === null ? "New employee" : "Edit details"}</h1>
          {existing && <p className="muted lead">{existing.full_name}, {existing.employee_no}</p>}
        </div>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {(employeeId === null || existing) && (
        <section className="panel-card padded form-page">
          <EmployeeForm
            existing={existing}
            defaultCampus={campusId}
            onSaved={(saved) => onNavigate(`/people/${saved.id}`)}
            onCancel={() => onNavigate(back)}
          />
        </section>
      )}
    </>
  );
}
