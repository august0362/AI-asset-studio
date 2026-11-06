import { useEffect } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  Box,
  Boxes,
  Cpu,
  FolderOpen,
  Hexagon,
  ListChecks,
  Sparkles,
} from "lucide-react";
import { isMock } from "./api/client";
import { Badge } from "./components/ui";
import { DraftProvider } from "./features/generate/Draft";
import { GeneratePage } from "./features/generate/GeneratePage";
import { JobsPage } from "./features/jobs/JobsPage";
import { LibraryPage } from "./features/library/LibraryPage";
import { ResourcesPage } from "./features/resources/ResourcesPage";
const links = [
  { to: "/generate", label: "Generate studio", icon: Sparkles },
  { to: "/library", label: "Asset library", icon: FolderOpen },
  { to: "/jobs", label: "Jobs & logs", icon: ListChecks },
  { to: "/resources", label: "Kaggle resources", icon: Cpu },
];
export default function App() {
  const location = useLocation();
  useEffect(() => {
    const title =
      links.find((l) => location.pathname.startsWith(l.to))?.label ??
      "Workspace";
    document.title = `${title} · AI Asset Studio`;
  }, [location.pathname]);
  return (
    <DraftProvider>
      <a className="skip-link" href="#main-content">
        Skip to workspace
      </a>
      <header className="app-header">
        <NavLink className="brand" to="/generate/image-to-3d">
          <span className="brand-mark">
            <Hexagon size={25} aria-hidden="true" />
            <Box size={13} aria-hidden="true" />
          </span>
          <span>
            AI Asset <strong>Studio</strong>
          </span>
        </NavLink>
        <Badge tone="cyan">Obsidian</Badge>
        <nav aria-label="Main navigation">
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to}>
              <Icon size={16} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="header-profile">
          <span className="status-dot" />
          <span>{isMock ? "Local mock session" : "Local API session"}</span>
          <Badge>{isMock ? "MOCK" : "HTTP"}</Badge>
        </div>
      </header>
      <aside className="tool-shelf" aria-label="Workspace tools">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink title={label} aria-label={label} key={to} to={to}>
            <Icon size={20} aria-hidden="true" />
          </NavLink>
        ))}
        <span className="shelf-end" title="M1 Mock Frontend">
          <Boxes size={20} aria-hidden="true" />
        </span>
      </aside>
      <main id="main-content" tabIndex={-1}>
        <Routes>
          <Route
            path="/"
            element={<Navigate replace to="/generate/image-to-3d" />}
          />
          <Route
            path="/generate"
            element={<Navigate replace to="/generate/image-to-3d" />}
          />
          <Route path="/generate/:pipeline" element={<GeneratePage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/jobs/:jobId" element={<JobsPage />} />
          <Route path="/resources" element={<ResourcesPage />} />
          <Route
            path="*"
            element={
              <div className="empty">
                <h1>Page not found</h1>
                <NavLink to="/generate/image-to-3d">Return to studio</NavLink>
              </div>
            }
          />
        </Routes>
      </main>
      <footer className="statusbar">
        <span>
          <span className="status-dot" />
          Local workspace
        </span>
        <span>
          {isMock ? "Mock API · No Kaggle connection" : "HTTP API · /api/v1"}
        </span>
        <span>
          Contract v1.0 <span className="statusbar-divider">/</span> M1 preview
        </span>
      </footer>
    </DraftProvider>
  );
}
