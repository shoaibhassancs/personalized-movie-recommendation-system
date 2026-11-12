import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "./AuthContext";

/** Pages that need a login. Visitors go to /login and come back afterwards. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <p role="status">Checking your session…</p>;
  if (status === "anonymous") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: location.pathname + location.search }}
      />
    );
  }
  return <Outlet />;
}
