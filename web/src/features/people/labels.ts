/** Words for a staff record's codes, shared by the list and the file. */

import type { Employee } from "../../api/types";

export const STATUS_LABEL: Record<Employee["status"], string> = {
  active: "Active",
  on_leave: "On leave",
  suspended: "Suspended",
  separated: "Separated",
};
