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
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { RecommendationsPage } from "./pages/RecommendationsPage";
import { AccountDeletedPage, AccountPage, NotFoundPage } from "./pages/AccountPage";
import { CataloguePage } from "./pages/CataloguePage";
import { HistoryPage, WatchlistPage } from "./pages/ListPages";
import { LoginPage } from "./pages/LoginPage";
import { MovieDetailPage } from "./pages/MovieDetailPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { RegisterPage } from "./pages/RegisterPage";

/** Where "/" goes: logged-in people land on the dashboard, visitors on the catalogue. */
function Home() {
  const { status } = useAuth();
  if (status === "loading") return <p role="status">Checking your session…</p>;
  return <Navigate to={status === "authenticated" ? "/dashboard" : "/movies"} replace />;
}

function Layout() {
  const { status, user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <>
      <header className="top">
        <div className="top-inner">
          <Link to="/" className="brand">
            PMRS Movies
          </Link>
          <span className="pill">Local build</span>
          <nav aria-label="Main">
            {status === "authenticated" && (
              <>
                <NavLink to="/dashboard">Dashboard</NavLink>
                <NavLink to="/recommendations">Recommendations</NavLink>
              </>
            )}
            <NavLink to="/movies">Catalogue</NavLink>
            {status === "authenticated" ? (
              <>
                <NavLink to="/watchlist">Watchlist</NavLink>
                <NavLink to="/history">History</NavLink>
                <NavLink to="/analytics">Analytics</NavLink>
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
        </div>
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
          Not endorsed by GroupLens or the University of Minnesota.
        </p>
        <p>
          Cite: F. M. Harper and J. A. Konstan (2015), The MovieLens Datasets: History and
          Context, ACM TiiS 5(4), 19:1-19:19. https://doi.org/10.1145/2827872
        </p>
      </footer>
    </>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="movies" element={<CataloguePage />} />
        <Route path="movies/:id" element={<MovieDetailPage />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="register" element={<RegisterPage />} />
        <Route path="account-deleted" element={<AccountDeletedPage />} />
        <Route element={<RequireAuth />}>
          <Route path="onboarding/genres" element={<OnboardingPage />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="recommendations" element={<RecommendationsPage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
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
