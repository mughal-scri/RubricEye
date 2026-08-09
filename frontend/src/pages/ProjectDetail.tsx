import { ArrowLeft, CheckCircle2, Clock, FileUp, Layers, ShieldLock, Upload, Eye } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnswerSheetSummary, getProject, listAnswerSheets, ProjectDetail } from "../api/client";

export default function ProjectDetailPage() {
  const { projectId } = useParams();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [sheets, setSheets] = useState<AnswerSheetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId) return;
    Promise.all([getProject(projectId), listAnswerSheets(projectId)])
      .then(([projectData, sheetData]) => {
        setProject(projectData);
        setSheets(sheetData);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, [projectId]);

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
          </div>
          <p>Project ID: <code style={{ fontFamily: "var(--font-mono)" }}>{project.id}</code></p>
        </div>

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <Link to={`/projects/${projectId}/template-map`} className="btn btn-secondary">
            <Layers size={16} /> Review Template Map
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
                <th>Status</th>
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
                  <td style={{ textAlign: "right" }}>
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
