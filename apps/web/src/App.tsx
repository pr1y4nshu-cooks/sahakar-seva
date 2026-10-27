import { Route, Routes } from "react-router-dom";
import { Layout } from "./components/layout/Layout";
import { Home } from "./pages/Home";
import { Placeholder } from "./pages/Placeholder";

export function App() {
  return <Routes><Route element={<Layout />}><Route path="/" element={<Home />} /><Route path="/hire" element={<Placeholder title="Hire a Worker" description="Worker discovery and direct hiring will be introduced after the foundation is verified." />} /><Route path="/find-work" element={<Placeholder title="Find Work" description="Job discovery and applications will be introduced in a later phase." />} /><Route path="/dashboard" element={<Placeholder title="Your Dashboard" description="Personalized account functionality will arrive with authentication and user workflows." />} /><Route path="/organizations" element={<Placeholder title="Organizations" description="Business and cooperative account tools will be built on the organization foundation." />} /></Route></Routes>;
}

