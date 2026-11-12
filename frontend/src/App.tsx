import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useNavigate,
} from "react-router";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { RequireAuth } from "./auth/RequireAuth";
import { AccountDeletedPage, AccountPage, NotFoundPage } from "./pages/AccountPage";
import { CataloguePage } from "./pages/CataloguePage";
import { HistoryPage, WatchlistPage } from "./pages/ListPages";
import { LoginPage } from "./pages/LoginPage";
import { MovieDetailPage } from "./pages/MovieDetailPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { RegisterPage } from "./pages/RegisterPage";

function Layout() {
  const { status, user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <>
      <header className="top">
        <Link to="/movies" className="brand">
          PMRS Movies
        </Link>
        <span className="pill">Local build</span>
        <nav aria-label="Main">
          <NavLink to="/movies">Catalogue</NavLink>
          {status === "authenticated" ? (
            <>
              <NavLink to="/watchlist">Watchlist</NavLink>
              <NavLink to="/history">History</NavLink>
              <NavLink to="/account" className="nav-account">
                Account
                {user && (
                  <>
                    {" · "}
                    <span className="nav-name">{user.display_name}</span>
                  </>
                )}
              </NavLink>
              <button
                type="button"
                className="secondary small-button"
                onClick={() => {
                  logout();
                  navigate("/movies");
                }}
              >
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login">Log in</NavLink>
              <NavLink to="/register">Register</NavLink>
            </>
          )}
        </nav>
      </header>
      <main>
        <Outlet />
      </main>
      <footer>
        <p>
          Local development build: do not expose it publicly. The API has no rate limiting
          or HTTPS yet.
        </p>
        <p>
          Movie data: MovieLens (GroupLens, non-commercial). This is a portfolio project.
        </p>
      </footer>
    </>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/movies" replace />} />
        <Route path="movies" element={<CataloguePage />} />
        <Route path="movies/:id" element={<MovieDetailPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="account-deleted" element={<AccountDeletedPage />} />
        <Route element={<RequireAuth />}>
          <Route path="onboarding/genres" element={<OnboardingPage />} />
          <Route path="watchlist" element={<WatchlistPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="account" element={<AccountPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
