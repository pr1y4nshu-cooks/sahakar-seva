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

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return <Routes><Route path="*" element={children} /></Routes>;
}

function PublicOnlyRoute({ children }: { children: React.ReactNode }) {
  return <Routes><Route path="*" element={children} /></Routes>;
}

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
          <Route path="signup" element={<PublicOnlyRoute><Signup /></PublicOnlyRoute>} />
          <Route
            path="dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="profile"
            element={
              <ProtectedRoute>
                <Profile />
              </ProtectedRoute>
            }
          />
          <Route
            path="earn"
            element={
              <ProtectedRoute>
                <Earn />
              </ProtectedRoute>
            }
          />
          <Route
            path="organizations"
            element={
              <ProtectedRoute>
                <Organizations />
              </ProtectedRoute>
            }
          />
          <Route path="hire" element={<Placeholder title="Hire a Worker" description="Worker discovery and direct hiring will be introduced in Phase 3." />} />
          <Route path="find-work" element={<Placeholder title="Find Work" description="Job discovery and applications will be introduced in Phase 3." />} />
        </Route>
      </Routes>
    </AuthProvider>
  );
}

