import { useEffect, useMemo } from "react";
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
import { CharacterLibraryPage } from "./features/characters/CharacterLibraryPage";
import { CharacterWorkspacePage } from "./features/characters/CharacterWorkspacePage";
import { StageDetailPage } from "./features/characters/StageDetailPage";
const navigation = [
  { to: "/characters", label: "char.characters" as const, icon: Boxes },
  { to: "/generate", label: "copy.generateStudio" as const, icon: Sparkles },
  { to: "/library", label: "copy.assetLibrary" as const, icon: FolderOpen },
  { to: "/jobs", label: "copy.jobsLogs" as const, icon: ListChecks },
  { to: "/resources", label: "copy.kaggleResources" as const, icon: Cpu },
];
import { I18nProvider, useI18n } from "./i18n";
import { ThemeProvider } from "./theme/ThemeProvider";
import { PreferenceSwitchers } from "./theme/PreferenceSwitchers";
export default function App() {
  return (
    <ThemeProvider>
      <I18nProvider>
        <Workspace />
      </I18nProvider>
    </ThemeProvider>
  );
}
function Workspace() {
  const { t } = useI18n();
  const links = useMemo(
    () => navigation.map((link) => ({ ...link, label: t(link.label) })),
    [t],
  );
  const location = useLocation();
  useEffect(() => {
    if (location.pathname.startsWith("/characters")) window.scrollTo(0, 0);
    const title =
      links.find((l) => location.pathname.startsWith(l.to))?.label ??
      t("copy.workspace");
    document.title = `${title} · AI Asset Studio`;
  }, [location.pathname, links, t]);
  return (
    <DraftProvider>
      <a className="skip-link" href="#main-content">
        {t("copy.skipToWorkspace")}
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

        <nav aria-label={t("copy.mainNavigation")}>
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to}>
              <Icon size={16} aria-hidden="true" />
              {label}
            </NavLink>
          ))}
        </nav>
        <PreferenceSwitchers />
        <div className="header-profile">
          <span className="status-dot" />
          <span>
            {isMock ? t("copy.localMockSession") : t("copy.localApiSession")}
          </span>
          <Badge>{isMock ? t("common.mock") : t("common.http")}</Badge>
        </div>
      </header>
      <aside className="tool-shelf" aria-label={t("copy.workspaceTools")}>
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink title={label} aria-label={label} key={to} to={to}>
            <Icon size={20} aria-hidden="true" />
          </NavLink>
        ))}
        <span className="shelf-end" title={t("copy.m1MockFrontend")}>
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
          <Route path="/characters" element={<CharacterLibraryPage />} />
          <Route
            path="/characters/:characterId"
            element={<CharacterWorkspacePage />}
          />
          <Route
            path="/characters/:characterId/stages/:stageId"
            element={<StageDetailPage />}
          />
          <Route
            path="*"
            element={
              <div className="empty">
                <h1>{t("copy.pageNotFound")}</h1>
                <NavLink to="/generate/image-to-3d">
                  {t("copy.returnToStudio")}
                </NavLink>
              </div>
            }
          />
        </Routes>
      </main>
      <footer className="statusbar">
        <span>
          <span className="status-dot" />
          {t("copy.localWorkspace")}
        </span>
        <span>
          {isMock
            ? t("copy.mockApiNoKaggleConnection")
            : t("copy.httpApiApiV1")}
        </span>
        <span>
          {t(
            location.pathname.startsWith("/characters")
              ? "char.contractVersion"
              : "copy.contractV10",
          )}
          <span className="statusbar-divider">/</span>
          {t(
            location.pathname.startsWith("/characters")
              ? "char.productionTitle"
              : "copy.m1Preview",
          )}
        </span>
      </footer>
    </DraftProvider>
  );
}
