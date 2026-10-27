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
import { Hire } from "./pages/Hire";
import { FindWork } from "./pages/FindWork";
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
            <Route path="hire" element={<Hire />} />
            <Route path="find-work" element={<FindWork />} />
          </Route>
        </Routes>
      </AuthProvider>
    </ErrorBoundary>
  );
}