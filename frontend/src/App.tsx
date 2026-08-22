import { Eye, Server } from "lucide-react";
import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import AnswerSheetDetailPage from "./pages/AnswerSheetDetail";
import CreateProject from "./pages/CreateProject";
import GradingResults from "./pages/GradingResults";
import ProjectDetailPage from "./pages/ProjectDetail";
import ProjectList from "./pages/ProjectList";
import QuestionBankSetup from "./pages/QuestionBankSetup";
import QuestionGroupSetup from "./pages/QuestionGroupSetup";
import TemplateMapReview from "./pages/TemplateMapReview";
import UploadAnswerSheet from "./pages/UploadAnswerSheet";
import "./styles.css";

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <header className="app-header">
          <Link to="/" className="brand-container">
            <div className="brand-logo">
              <Eye size={20} color="white" />
            </div>
            <span className="brand-title">RubricEye</span>
            <span className="brand-tag">Local assessment workspace</span>
          </Link>
          <div className="header-status">
            <Server size={15} />
            <span>Local backend</span>
            <span className="status-dot status-dot-neutral" aria-label="Local backend status not checked"></span>
          </div>
        </header>

        <main className="app-main">
          <Routes>
            <Route path="/" element={<ProjectList />} />
            <Route path="/projects/new" element={<CreateProject />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="/projects/:projectId/template-map" element={<TemplateMapReview />} />
            <Route path="/projects/:projectId/question-bank" element={<QuestionBankSetup />} />
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
