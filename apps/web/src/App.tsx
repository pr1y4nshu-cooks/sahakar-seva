import { Route, Routes, Navigate } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { Home } from "./pages/Home";
import { Placeholder } from "./pages/Placeholder";
import { Login } from "./pages/Login";
import { Signup } from "./pages/Signup";
import { Dashboard } from "./pages/Dashboard";
import { Profile } from "./pages/Profile";
import { Earn } from "./pages/Earn";
import { Organizations } from "./pages/Organizations";
import { AuthProvider } from "./lib/auth";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { AuthGuard, PublicOnlyGuard } from "./components/auth/AuthGuard";

export function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Home />} />
            <Route path="login" element={<PublicOnlyGuard><Login /></PublicOnlyGuard>} />
            <Route path="signup" element={<PublicOnlyGuard><Signup /></PublicOnlyGuard>} />
            <Route
              path="dashboard"
              element={
                <AuthGuard>
                  <Dashboard />
                </AuthGuard>
              }
            />
            <Route
              path="profile"
              element={
                <AuthGuard>
                  <Profile />
                </AuthGuard>
              }
            />
            <Route
              path="earn"
              element={
                <AuthGuard>
                  <Earn />
                </AuthGuard>
              }
            />
            <Route
              path="organizations"
              element={
                <AuthGuard>
                  <Organizations />
                </AuthGuard>
              }
            />
            <Route path="hire" element={<Placeholder title="Hire a Worker" description="Worker discovery and direct hiring will be introduced in Phase 3." />} />
            <Route path="find-work" element={<Placeholder title="Find Work" description="Job discovery and applications will be introduced in Phase 3." />} />
          </Route>
        </Routes>
      </AuthProvider>
    </ErrorBoundary>
  );
}