import { Link, NavLink, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import UploadJD from "./pages/UploadJD";
import Upload from "./pages/Upload";
import Verify from "./pages/Verify";
import SchemaPage from "./pages/Schema";

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b bg-white">
        <div className="max-w-6xl mx-auto flex items-center gap-6 px-6 py-4">
          <Link to="/" className="font-semibold text-lg">
            Resume ATS
          </Link>
          <nav className="flex gap-4 text-sm">
            {[
              ["/", "Dashboard"],
              ["/jd", "Job Description"],
              ["/upload", "Upload"],
              ["/schema", "Schema"],
            ].map(([to, label]) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  isActive ? "text-blue-600 font-medium" : "text-slate-600 hover:text-slate-900"
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jd" element={<UploadJD />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/resumes/:id" element={<Verify />} />
          <Route path="/schema" element={<SchemaPage />} />
        </Routes>
      </main>
    </div>
  );
}
