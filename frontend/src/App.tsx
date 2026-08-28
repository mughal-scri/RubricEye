import { FolderKanban, Server, Sparkles, Trash2 } from "lucide-react";
import logoImage from "./assets/rubriceye-logo.jpeg";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
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
import TemplateMapReview from "./pages/TemplateMapReview";
import UploadAnswerSheet from "./pages/UploadAnswerSheet";
import Trash from "./pages/Trash";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="app-header">
          <Link to="/" className="brand-container">
            <img src={logoImage} alt="RubricEye" className="brand-logo-image" />
            <span className="brand-title">RubricEye</span>
            <span className="brand-tag">Local assessment workspace</span>
          </Link>
          <nav className="global-nav" aria-label="Primary navigation">
            <Link to="/" className="global-nav-link"><FolderKanban size={15} /> Workspace</Link>
            <Link to="/rubric-studio" className="global-nav-link"><Sparkles size={15} /> Rubric Studio</Link>
            <Link to="/trash" className="global-nav-link"><Trash2 size={15} /> Trash</Link>
          </nav>
          <div className="header-status" title="Your files and grading data stay in this local workspace">
            <span className="status-dot status-dot-neutral" aria-label="Local backend status not checked"></span>
            <Server size={15} />
            <span>Local workspace</span>
          </div>
        </header>

        <main className="app-main">
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
            <Route path="/projects/:projectId/upload" element={<UploadAnswerSheet />} />
            <Route path="/projects/:projectId/answer-sheets/:sheetId" element={<AnswerSheetDetailPage />} />
            <Route path="/projects/:projectId/answer-sheets/:sheetId/results" element={<GradingResults />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
