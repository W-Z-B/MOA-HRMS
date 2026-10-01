import type { Dependant, EmergencyContact } from "../../api/types";
import { dmy } from "../../app/format";
import { RecordList } from "./RecordList";

const RELATIONSHIPS = [
  { value: "child", label: "Child" },
  { value: "spouse", label: "Spouse or partner" },
  { value: "parent", label: "Parent" },
  { value: "other", label: "Other" },
];

interface Props {
  employeeId: number;
  canEdit: boolean;
  /** Dependants are family details: HR, Finance and auditors only. */
  canSeeDependants: boolean;
}

/** Who to call in an emergency, in order, and the people who depend on the employee. */
export function ContactsTab({ employeeId, canEdit, canSeeDependants }: Props) {
  return (
    <>
      <RecordList<EmergencyContact>
        title="Emergency contacts"
        endpoint="/emergency-contacts/"
        employeeId={employeeId}
        canEdit={canEdit}
        emptyText="No emergency contact. Add at least one."
        addLabel="Add an emergency contact"
        nameOf={(c) => c.name}
        fields={[
          { name: "name", label: "Name", required: true },
          { name: "relationship", label: "Relationship" },
          { name: "phone", label: "Phone", type: "tel", required: true },
          { name: "alternate_phone", label: "Other phone", type: "tel" },
          { name: "priority", label: "Order to call (1 first)", type: "number" },
        ]}
        describe={(c) => (
          <>
            <strong>{c.name}</strong>
            {c.relationship ? `, ${c.relationship}` : ""}
            <br />
            <span className="muted small">
              {c.priority}. call {c.phone}
              {c.alternate_phone ? ` or ${c.alternate_phone}` : ""}
            </span>
          </>
        )}
      />
      {canSeeDependants && (
        <RecordList<Dependant>
          title="Dependants"
          endpoint="/dependants/"
          employeeId={employeeId}
          canEdit={canEdit}
          emptyText="No dependants recorded."
          addLabel="Add a dependant"
          nameOf={(d) => d.name}
          fields={[
            { name: "name", label: "Name", required: true },
            { name: "relationship", label: "Relationship", type: "select", options: RELATIONSHIPS, required: true },
            { name: "date_of_birth", label: "Date of birth (needed for the child tax deduction)", type: "date" },
          ]}
          describe={(d) => (
            <>
              <strong>{d.name}</strong>, {d.relationship_name.toLowerCase()}
              {d.date_of_birth && <span className="muted small"> · born {dmy(d.date_of_birth)}</span>}
            </>
          )}
        />
      )}
    </>
  );
}
