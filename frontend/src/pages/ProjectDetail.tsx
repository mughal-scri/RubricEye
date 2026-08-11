import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Eye,
  FileUp,
  GraduationCap,
  Layers,
  ListChecks,
  ShieldLock,
  Sparkles,
  Upload,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AnswerSheetSummary,
  gradeAnswerSheet,
  getProject,
  listAnswerSheets,
  listQuestionBank,
  ProjectDetail,
} from "../api/client";

const GRADING_STATUS_BADGE: Record<string, string> = {
  not_graded: "badge-slate",
  in_progress: "badge-warning",
  complete: "badge-success",
  failed: "badge-warning",
};

export default function ProjectDetailPage() {
  const { projectId } = useParams();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [sheets, setSheets] = useState<AnswerSheetSummary[]>([]);
  const [questionBankCount, setQuestionBankCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [gradingSheetId, setGradingSheetId] = useState<string | null>(null);

  const load = () => {
    if (!projectId) return;
    Promise.all([getProject(projectId), listAnswerSheets(projectId), listQuestionBank(projectId)])
      .then(([projectData, sheetData, qbData]) => {
        setProject(projectData);
        setSheets(sheetData);
        setQuestionBankCount(qbData.items.length);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  };

  useEffect(load, [projectId]);

  const triggerGrade = async (sheetId: string) => {
    if (!projectId) return;
    setGradingSheetId(sheetId);
    setError("");
    try {
      await gradeAnswerSheet(projectId, sheetId);
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setGradingSheetId(null);
    }
  };

  if (!projectId) return null;
  if (error) return <div className="alert alert-error">Error loading project: {error}</div>;
  if (loading || !project) return <div style={{ textAlign: "center", padding: "3rem" }}>Loading project details...</div>;

  return (
    <div>
      <div className="breadcrumb">
        <Link to="/"><ArrowLeft size={14} /> Back to Projects</Link>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1>{project.name}</h1>
            <span className={`badge ${project.template_map_confirmed ? "badge-success" : "badge-warning"}`}>
              {project.template_map_confirmed ? (
                <>
                  <CheckCircle2 size={12} /> Template Confirmed
                </>
              ) : (
                <>
                  <Clock size={12} /> Pending Confirmation
                </>
              )}
            </span>
            <span className={`badge ${project.question_bank_confirmed ? "badge-success" : "badge-warning"}`}>
              {project.question_bank_confirmed ? (
                <>
                  <CheckCircle2 size={12} /> Question Bank Locked
                </>
              ) : (
                <>
                  <Clock size={12} /> Question Bank Pending
                </>
              )}
            </span>
          </div>
          <p>Project ID: <code style={{ fontFamily: "var(--font-mono)" }}>{project.id}</code></p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
          <Link to={`/projects/${projectId}/template-map`} className="btn btn-secondary">
            <Layers size={16} /> Review Template Map
          </Link>
          <Link to={`/projects/${projectId}/question-bank`} className="btn btn-secondary">
            <ListChecks size={16} /> Setup Question Bank
          </Link>
          <Link to={`/projects/${projectId}/question-groups`} className="btn btn-secondary">
            <Sparkles size={16} /> Setup Question Groups
          </Link>
          {project.template_map_confirmed ? (
            <Link to={`/projects/${projectId}/upload`} className="btn btn-primary">
              <Upload size={16} /> Upload Answer Sheet
            </Link>
          ) : (
            <button className="btn btn-secondary" disabled title="Confirm template map first to enable answer sheet uploads">
              <Upload size={16} /> Upload Answer Sheet (Locked)
            </button>
          )}
        </div>
      </div>

      {project.question_bank_marks_warning && (
        <div className="alert alert-warning">
          <span>{project.question_bank_marks_warning}</span>
        </div>
      )}

      {/* Project Status Summary Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        <div className="card" style={{ padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-brand-600)", marginBottom: "0.5rem" }}>
            <ShieldLock size={18} />
            <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>Anti-Bias Rubric Lock</span>
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--color-emerald-700)" }}>
            Locked & Immutable
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--color-slate-500)", marginTop: "0.25rem" }}>
            MODIFICATIONS forbidden via HTTP 403 status code to preserve grading anti-bias integrity.
          </p>
        </div>

        <div className="card" style={{ padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-brand-600)", marginBottom: "0.5rem" }}>
            <Layers size={18} />
            <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>Template Derivation</span>
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 700, color: project.template_map_confirmed ? "var(--color-emerald-700)" : "var(--color-amber-700)" }}>
            Status: {project.template_map_status}
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--color-slate-500)", marginTop: "0.25rem" }}>
            {project.template_map_confirmed ? "Locked against further coordinate edits." : "Review bounding box regions before answer sheet upload."}
          </p>
        </div>

        <div className="card" style={{ padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-brand-600)", marginBottom: "0.5rem" }}>
            <GraduationCap size={18} />
            <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>Question Bank</span>
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 700, color: project.question_bank_confirmed ? "var(--color-emerald-700)" : "var(--color-amber-700)" }}>
            {questionBankCount} question(s) {project.question_bank_confirmed ? "locked" : "in draft"}
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--color-slate-500)", marginTop: "0.25rem" }}>
            {project.question_bank_confirmed ? "Ready for grading." : "Confirm to enable the Grade button."}
          </p>
        </div>

        <div className="card" style={{ padding: "1.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", color: "var(--color-brand-600)", marginBottom: "0.5rem" }}>
            <FileUp size={18} />
            <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>Uploaded Answer Sheets</span>
          </div>
          <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--color-slate-900)" }}>
            {sheets.length} Booklet(s) Processed
          </div>
          <p style={{ fontSize: "0.8rem", color: "var(--color-slate-500)", marginTop: "0.25rem" }}>
            Aligned & cropped into question region maps.
          </p>
        </div>
      </div>

      {/* Answer Sheets List */}
      <div style={{ marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "1.3rem", fontWeight: 800, fontFamily: "var(--font-display)", color: "var(--color-slate-900)" }}>
          Answer Sheets
        </h2>
      </div>

      {sheets.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <FileUp size={28} />
          </div>
          <h3>No answer sheets uploaded yet</h3>
          <p>
            {project.template_map_confirmed
              ? "Upload candidate answer sheet PDFs to perform structural alignment and question region segmentation."
              : "Please review and confirm the template map before uploading answer sheets."}
          </p>
          {project.template_map_confirmed && (
            <Link to={`/projects/${projectId}/upload`} className="btn btn-primary">
              <Upload size={16} /> Upload Answer Sheet
            </Link>
          )}
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Candidate Roll #</th>
                <th>Page Count</th>
                <th>Uploaded Timestamp</th>
                <th>Segmentation</th>
                <th>Grading</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sheets.map((sheet) => (
                <tr key={sheet.id}>
                  <td style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                    Roll {sheet.roll_number}
                  </td>
                  <td>
                    <span className="badge badge-slate">{sheet.page_count} Pages</span>
                  </td>
                  <td style={{ color: "var(--color-slate-500)" }}>
                    {new Date(sheet.uploaded_at).toLocaleString()}
                  </td>
                  <td>
                    <span className="badge badge-success">
                      <CheckCircle2 size={12} /> Aligned & Segmented
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${GRADING_STATUS_BADGE[sheet.grading_status] ?? "badge-slate"}`}>
                      {sheet.grading_status.replace("_", " ")}
                    </span>
                  </td>
                  <td style={{ textAlign: "right", display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                    {sheet.grading_status === "not_graded" || sheet.grading_status === "failed" ? (
                      <button
                        type="button"
                        className="btn btn-primary"
                        style={{ padding: "0.35rem 0.75rem", fontSize: "0.85rem" }}
                        disabled={!project.question_bank_confirmed || gradingSheetId === sheet.id}
                        title={!project.question_bank_confirmed ? "Confirm the question bank first" : undefined}
                        onClick={() => triggerGrade(sheet.id)}
                      >
                        <GraduationCap size={14} /> {gradingSheetId === sheet.id ? "Grading..." : "Grade"}
                      </button>
                    ) : (
                      <Link
                        to={`/projects/${projectId}/answer-sheets/${sheet.id}/results`}
                        className="btn btn-secondary"
                        style={{ padding: "0.35rem 0.75rem", fontSize: "0.85rem" }}
                      >
                        <GraduationCap size={14} /> View Results
                      </Link>
                    )}
                    <Link
                      to={`/projects/${projectId}/answer-sheets/${sheet.id}`}
                      className="btn btn-secondary"
                      style={{ padding: "0.35rem 0.75rem", fontSize: "0.85rem" }}
                    >
                      <Eye size={14} /> View Segmentation
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
