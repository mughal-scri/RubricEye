import { FolderKanban, Menu, Server, Sparkles, Trash2, X } from "lucide-react";
import { useState } from "react";
import logoImage from "./assets/rubriceye-logo.jpeg";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import AnswerSheetDetailPage from "./pages/AnswerSheetDetail";
import CreateProject from "./pages/CreateProject";
import GradingResults from "./pages/GradingResults";
import ProjectDetailPage from "./pages/ProjectDetail";
import RubricStudio from "./pages/RubricStudio";
import RubricAlignment from "./pages/RubricAlignment";
import RubricStudioStandalone from "./pages/RubricStudioStandalone";
import ProjectList from "./pages/ProjectList";
import QuestionBankSetup from "./pages/QuestionBankSetup";
import QuestionGroupSetup from "./pages/QuestionGroupSetup";
import ReviewQueue from "./pages/ReviewQueue";
import TemplateMapReview from "./pages/TemplateMapReview";
import UploadAnswerSheet from "./pages/UploadAnswerSheet";
import Trash from "./pages/Trash";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}

function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="app-shell">
        <a href="#main-content" className="skip-link">Skip to main content</a>
        <header className="app-header">
          <Link to="/" className="brand-container">
            <img src={logoImage} alt="RubricEye" className="brand-logo-image" />
            <span className="brand-title">RubricEye</span>
            <span className="brand-tag">Local assessment workspace</span>
          </Link>
          <nav className={`global-nav${mobileNavOpen ? " is-open" : ""}`} aria-label="Primary navigation">
            <Link to="/" className={`global-nav-link${isActive("/") ? " is-active" : ""}`} aria-current={isActive("/") ? "page" : undefined} onClick={() => setMobileNavOpen(false)}><FolderKanban size={15} /> Workspace</Link>
            <Link to="/rubric-studio" className={`global-nav-link${isActive("/rubric-studio") ? " is-active" : ""}`} aria-current={isActive("/rubric-studio") ? "page" : undefined} onClick={() => setMobileNavOpen(false)}><Sparkles size={15} /> Rubric Studio</Link>
            <Link to="/trash" className={`global-nav-link${isActive("/trash") ? " is-active" : ""}`} aria-current={isActive("/trash") ? "page" : undefined} onClick={() => setMobileNavOpen(false)}><Trash2 size={15} /> Trash</Link>
          </nav>
          <button type="button" className="mobile-nav-toggle" aria-label={mobileNavOpen ? "Close navigation menu" : "Open navigation menu"} aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((prev) => !prev)}>{mobileNavOpen ? <X size={20} /> : <Menu size={20} />}</button>
          <div className="header-status" title="Your files and grading data stay in this local workspace">
            <span className="status-dot status-dot-neutral" aria-label="Local backend status not checked"></span>
            <Server size={15} />
            <span>Local workspace</span>
          </div>
        </header>

        <main className="app-main" id="main-content">
          <Routes>
            <Route path="/" element={<ProjectList />} />
            <Route path="/projects/new" element={<CreateProject />} />
            <Route path="/rubric-studio" element={<RubricStudioStandalone />} />
            <Route path="/trash" element={<Trash />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="/projects/:projectId/template-map" element={<TemplateMapReview />} />
            <Route path="/projects/:projectId/question-bank" element={<QuestionBankSetup />} />
            <Route path="/projects/:projectId/rubric-studio" element={<RubricStudio />} />
            <Route path="/projects/:projectId/rubric-alignment" element={<RubricAlignment />} />
            <Route path="/projects/:projectId/question-groups" element={<QuestionGroupSetup />} />
            <Route path="/projects/:projectId/review-queue" element={<ReviewQueue />} />
            <Route path="/projects/:projectId/upload" element={<UploadAnswerSheet />} />
            <Route path="/projects/:projectId/answer-sheets/:sheetId" element={<AnswerSheetDetailPage />} />
            <Route path="/projects/:projectId/answer-sheets/:sheetId/results" element={<GradingResults />} />
          </Routes>
        </main>
      </div>
  );
}
