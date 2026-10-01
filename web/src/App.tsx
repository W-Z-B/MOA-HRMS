import { useCallback, useEffect, useState } from "react";
import { get, post, SIGNED_OUT_EVENT } from "./api/client";
import { isOfficeUser, type Me } from "./api/types";
import { Shell } from "./app/Shell";
import { useHashRoute } from "./app/router";
import { AdminScreen } from "./features/admin/AdminScreen";
import { ForgotPasswordScreen } from "./features/auth/ForgotPasswordScreen";
import { LoginScreen } from "./features/auth/LoginScreen";
import { SetPasswordScreen } from "./features/auth/SetPasswordScreen";
import { DashboardScreen } from "./features/dashboard/DashboardScreen";
import { LeaveScreen } from "./features/leave/LeaveScreen";
import { AccountScreen } from "./features/me/AccountScreen";
import { MyContractScreen } from "./features/me/MyContractScreen";
import { DirectoryScreen } from "./features/people/DirectoryScreen";
import { ComingSoon } from "./features/placeholder/ComingSoon";
import { MyRecordScreen } from "./features/privacy/MyRecordScreen";
import { PrivacyNoticeScreen } from "./features/privacy/PrivacyNoticeScreen";
import { ReportsScreen } from "./features/reports/ReportsScreen";

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
  const [knownUsername, setKnownUsername] = useState("");

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

  const noticeRead = useCallback(() => setMe((person) => (person ? { ...person, privacy_notice_due: null } : person)), []);

  async function signOutFromNotice() {
    await post("/auth/logout/").catch(() => undefined);
    setMe(null);
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

  // An emailed link opens this page whether or not someone is signed in on this browser.
  const link = path.match(/^\/set-password\/([^/]+)\/([^/]+)$/);
  if (link)
    return (
      <SetPasswordScreen
        uid={link[1]}
        token={link[2]}
        onDone={(username) => {
          setKnownUsername(username);
          setSignedOutReason("Your password is saved. Sign in with it now.");
          navigate("/");
        }}
        onAskAgain={() => navigate("/forgot-password")}
      />
    );
  if (me === undefined) return <p className="loading">Loading GSA HRMS…</p>;
  if (me === null || (me.mfa_required && !me.mfa_verified)) {
    if (path === "/forgot-password") return <ForgotPasswordScreen onBack={() => navigate("/")} />;
    return (
      <LoginScreen
        key={knownUsername}
        onSignedIn={signedIn}
        notice={signedOutReason}
        username={knownUsername}
        onForgotPassword={() => navigate("/forgot-password")}
      />
    );
  }
  // The privacy notice in force is read once, after sign-in, before anything else (item 1.31).
  if (me.privacy_notice_due) return <PrivacyNoticeScreen onAcknowledged={noticeRead} onSignOut={signOutFromNotice} />;

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
  else if (path === "/my-record") screen = <MyRecordScreen />;
  else if (path === "/account") screen = <AccountScreen />;
  else if (path.startsWith("/attendance"))
    screen = <ComingSoon title="Attendance" sprint="Release 2" requirement="F07" />;
  else if (path.startsWith("/appraisals"))
    screen = <ComingSoon title="Appraisals" sprint="Release 2" requirement="F08" />;
  else if (path.startsWith("/payroll")) screen = <ComingSoon title="Payroll" sprint="Release 2" requirement="F13" />;
  else if (path.startsWith("/reports")) screen = <ReportsScreen campusId={campusId} onNavigate={navigate} />;
  else if (path.startsWith("/admin"))
    screen = <AdminScreen me={me} campusId={campusId} path={path} onNavigate={navigate} />;
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
