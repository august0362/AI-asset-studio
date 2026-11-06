import { useEffect, useMemo } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  matchPath,
  useLocation,
} from "react-router-dom";
import {
  Box,
  Cpu,
  FolderOpen,
  Hexagon,
  Layers,
  ListChecks,
  Network,
  Sparkles,
  UsersRound,
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
import { I18nProvider, useI18n } from "./i18n";
import { ThemeProvider } from "./theme/ThemeProvider";
import { PreferenceSwitchers } from "./theme/PreferenceSwitchers";
const core = [
  { to: "/generate", label: "copy.generateStudio" as const, icon: Sparkles },
  { to: "/jobs", label: "copy.jobsLogs" as const, icon: ListChecks },
  { to: "/resources", label: "copy.kaggleResources" as const, icon: Cpu },
  { to: "/library", label: "copy.assetLibrary" as const, icon: FolderOpen },
];
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
  const location = useLocation();
  const links = useMemo(
    () => [
      ...core.map((link) => ({ ...link, label: t(link.label) })),
      { to: "/characters", label: t("char.characters") },
    ],
    [t],
  );
  const inCharacters = location.pathname.startsWith("/characters");
  const stage = matchPath("/characters/:characterId/stages/:stageId", location.pathname);
  const character = matchPath("/characters/:characterId", location.pathname) ?? stage;
  useEffect(() => {
    if (inCharacters) window.scrollTo(0, 0);
    const title =
      links.find((l) => location.pathname.startsWith(l.to))?.label ??
      t("copy.workspace");
    document.title = `${title} · AI Asset Studio`;
  }, [location.pathname, links, t, inCharacters]);
  const section = inCharacters
    ? t("char.productionTitle")
    : (links.find((l) => location.pathname.startsWith(l.to))?.label ?? t("copy.workspace"));
  return (
    <DraftProvider>
      <a className="skip-link" href="#main-content">
        {t("copy.skipToWorkspace")}
      </a>
      <aside className="app-sidebar">
        <NavLink className="brand" to="/generate/image-to-3d">
          <span className="brand-mark">
            <Hexagon size={25} aria-hidden="true" />
            <Box size={13} aria-hidden="true" />
          </span>
          <span className="brand-name">
            AI Asset <strong>Studio</strong>
          </span>
        </NavLink>
        <nav aria-label={t("copy.mainNavigation")}>
          <p className="nav-section" aria-hidden="true">{t("copy.coreStudio")}</p>
          {core.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} title={t(label)}>
              <Icon size={18} aria-hidden="true" />
              <span className="nav-label">{t(label)}</span>
            </NavLink>
          ))}
          <p className="nav-section" aria-hidden="true">{t("char.productionTitle")}</p>
          <NavLink to="/characters" end title={t("char.characters")} className={() => (inCharacters ? "active" : "")}>
            <UsersRound size={18} aria-hidden="true" />
            <span className="nav-label">{t("char.characters")}</span>
          </NavLink>
          {character && (
            <div className="nav-sub">
              <NavLink
                to={`/characters/${character.params.characterId}`}
                end
                title={t("char.workspace")}
              >
                <Network size={16} aria-hidden="true" />
                <span className="nav-label">{t("char.workspace")}</span>
              </NavLink>
              {stage && (
                <NavLink to={location.pathname} title={t("char.stageDetail")}>
                  <Layers size={16} aria-hidden="true" />
                  <span className="nav-label">
                    {t("char.stageDetail")} · {stage.params.stageId?.toUpperCase()}
                  </span>
                </NavLink>
              )}
            </div>
          )}
        </nav>
        <div className="sidebar-environment">
          <span className="nav-section">{t("copy.environment")}</span>
          <span className="sidebar-session">
            <span className="status-dot" aria-hidden="true" />
            <span>{isMock ? t("copy.localMockSession") : t("copy.localApiSession")}</span>
            <Badge>{isMock ? t("common.mock") : t("common.http")}</Badge>
          </span>
          <small>
            {isMock ? t("copy.mockApiNoKaggleConnection") : t("copy.httpApiApiV1")}
          </small>
          <small>
            {t(inCharacters ? "char.contractVersion" : "copy.contractV10")}
          </small>
        </div>
      </aside>
      <header className="app-topbar">
        <span className="topbar-section">{section}</span>
        <PreferenceSwitchers />
      </header>
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
    </DraftProvider>
  );
}
