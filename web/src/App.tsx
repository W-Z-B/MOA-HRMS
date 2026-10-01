import { useEffect, useState } from "react";
import { get, SIGNED_OUT_EVENT } from "./api/client";
import { isOfficeUser, type Me } from "./api/types";
import { Shell } from "./app/Shell";
import { useHashRoute } from "./app/router";
import { LoginScreen } from "./features/auth/LoginScreen";
import { DashboardScreen } from "./features/dashboard/DashboardScreen";
import { LeaveScreen } from "./features/leave/LeaveScreen";
import { AccountScreen } from "./features/me/AccountScreen";
import { MyContractScreen } from "./features/me/MyContractScreen";
import { DirectoryScreen } from "./features/people/DirectoryScreen";
import { ComingSoon } from "./features/placeholder/ComingSoon";

const CAMPUS_KEY = "gsa-hrms.campus";

function readCampus(): number | null {
  try {
    const stored = localStorage.getItem(CAMPUS_KEY);
    return stored ? Number(stored) : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = still loading
  const [path, navigate] = useHashRoute();
  const [campusId, setCampusId] = useState<number | null>(readCampus);
  const [signedOutReason, setSignedOutReason] = useState<string | null>(null);

  useEffect(() => {
    get<Me>("/auth/me/")
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  // The server ended the session (idle, expired, or ended from another device): back to sign-in.
  useEffect(() => {
    const onSignedOut = (event: Event) => {
      setSignedOutReason((event as CustomEvent<string>).detail || null);
      setMe(null);
    };
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, []);

  function signedIn(person: Me) {
    setSignedOutReason(null);
    setMe(person);
  }

  function changeCampus(id: number | null) {
    setCampusId(id);
    try {
      if (id) localStorage.setItem(CAMPUS_KEY, String(id));
      else localStorage.removeItem(CAMPUS_KEY);
    } catch {
      /* per-viewer convenience only */
    }
  }

  if (me === undefined) return <p className="loading">Loading GSA HRMS…</p>;
  if (me === null || (me.mfa_required && !me.mfa_verified))
    return <LoginScreen onSignedIn={signedIn} notice={signedOutReason} />;

  const idIn = (prefix: string) => {
    const m = path.match(new RegExp(`^${prefix}/(\\d+)`));
    return m ? Number(m[1]) : null;
  };

  const leave = <LeaveScreen me={me} focusId={idIn("/leave/requests")} onNavigate={navigate} />;
  let screen;
  // An employee with no other role opens on their own leave: the dashboard is about the School.
  if (path === "/") screen = isOfficeUser(me) ? <DashboardScreen campusId={campusId} /> : leave;
  else if (path.startsWith("/people"))
    screen = <DirectoryScreen me={me} campusId={campusId} initialId={idIn("/people")} onNavigate={navigate} />;
  else if (path.startsWith("/leave")) screen = leave;
  else if (path === "/me") screen = <MyContractScreen />;
  else if (path === "/account") screen = <AccountScreen />;
  else if (path.startsWith("/attendance"))
    screen = <ComingSoon title="Attendance" sprint="Release 2" requirement="F07" />;
  else if (path.startsWith("/appraisals"))
    screen = <ComingSoon title="Appraisals" sprint="Release 2" requirement="F08" />;
  else if (path.startsWith("/payroll")) screen = <ComingSoon title="Payroll" sprint="Release 2" requirement="F13" />;
  else if (path.startsWith("/reports")) screen = <ComingSoon title="Reports" sprint="Sprint 6" requirement="F17" />;
  else if (path.startsWith("/admin")) screen = <ComingSoon title="Admin" sprint="Sprint 2" requirement="F05" />;
  else screen = <ComingSoon title="Not found" sprint="a later sprint" requirement="unknown route" />;

  return (
    <Shell
      me={me}
      path={path}
      onNavigate={navigate}
      onLogout={() => setMe(null)}
      campusId={campusId}
      onCampusChange={changeCampus}
    >
      {screen}
    </Shell>
  );
}
