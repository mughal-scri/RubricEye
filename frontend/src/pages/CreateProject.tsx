import { FileText, FolderPlus, Upload, ShieldLock, AlertCircle, ArrowLeft } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createProject } from "../api/client";

export default function CreateProject() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [rubric, setRubric] = useState<File | null>(null);
  const [questionPaper, setQuestionPaper] = useState<File | null>(null);
  const [blankBooklet, setBlankBooklet] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Please provide a project name.");
      return;
    }
    if (!rubric || !questionPaper || !blankBooklet) {
      setError("All three PDF documents (Rubric, Question Paper, and Blank Booklet) are required.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("rubric", rubric);
      formData.append("question_paper", questionPaper);
      formData.append("blank_booklet", blankBooklet);

      const project = await createProject(formData);
      navigate(`/projects/${project.id}/template-map`);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "760px", margin: "0 auto" }}>
      <div className="breadcrumb">
        <Link to="/"><ArrowLeft size={14} /> Back to Projects</Link>
      </div>

      <div className="page-header" style={{ marginBottom: "1.5rem" }}>
        <div className="page-title-group">
          <h1>Create Evaluation Project</h1>
          <p>Upload exam documentation to initialize template derivation and anti-bias rubric lock.</p>
        </div>
      </div>

      {error && (
        <div className="alert alert-error">
          <AlertCircle size={18} style={{ flexShrink: 0 }} />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={onSubmit} className="card">
        <div className="form-group">
          <label className="form-label" htmlFor="project-name">Project Title</label>
          <input
            id="project-name"
            className="form-input"
            placeholder="e.g. CS101 Midterm Examination 2026"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>

        <div style={{ margin: "1.5rem 0", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <h3 style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--color-slate-800)" }}>
            Required PDF Documents
          </h3>

          {/* Rubric PDF */}
          <div className={`file-dropzone ${rubric ? "has-file" : ""}`}>
            <label style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "1rem" }}>
              <div style={{ padding: "10px", background: rubric ? "var(--color-emerald-100)" : "var(--color-slate-200)", borderRadius: "var(--radius-md)", color: rubric ? "var(--color-emerald-700)" : "var(--color-slate-600)" }}>
                {rubric ? <ShieldLock size={22} /> : <Upload size={22} />}
              </div>
              <div style={{ flex: 1, textAlign: "left" }}>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                  1. Official Rubric PDF (Anti-Bias Lock)
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--color-slate-500)" }}>
                  {rubric ? `Selected: ${rubric.name} (${(rubric.size / 1024).toFixed(1)} KB)` : "Upload official grading rubric (locked upon creation)"}
                </div>
              </div>
              <input
                type="file"
                accept="application/pdf"
                style={{ display: "none" }}
                onChange={(e) => setRubric(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>

          {/* Question Paper PDF */}
          <div className={`file-dropzone ${questionPaper ? "has-file" : ""}`}>
            <label style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "1rem" }}>
              <div style={{ padding: "10px", background: questionPaper ? "var(--color-emerald-100)" : "var(--color-slate-200)", borderRadius: "var(--radius-md)", color: questionPaper ? "var(--color-emerald-700)" : "var(--color-slate-600)" }}>
                <FileText size={22} />
              </div>
              <div style={{ flex: 1, textAlign: "left" }}>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                  2. Question Paper PDF
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--color-slate-500)" }}>
                  {questionPaper ? `Selected: ${questionPaper.name} (${(questionPaper.size / 1024).toFixed(1)} KB)` : "Upload question paper layout"}
                </div>
              </div>
              <input
                type="file"
                accept="application/pdf"
                style={{ display: "none" }}
                onChange={(e) => setQuestionPaper(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>

          {/* Blank Answer Booklet PDF */}
          <div className={`file-dropzone ${blankBooklet ? "has-file" : ""}`}>
            <label style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "1rem" }}>
              <div style={{ padding: "10px", background: blankBooklet ? "var(--color-emerald-100)" : "var(--color-slate-200)", borderRadius: "var(--radius-md)", color: blankBooklet ? "var(--color-emerald-700)" : "var(--color-slate-600)" }}>
                <FileText size={22} />
              </div>
              <div style={{ flex: 1, textAlign: "left" }}>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                  3. Blank Answer Booklet PDF (Template Source)
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--color-slate-500)" }}>
                  {blankBooklet ? `Selected: ${blankBooklet.name} (${(blankBooklet.size / 1024).toFixed(1)} KB)` : "Used to derive geometric bounding box template map"}
                </div>
              </div>
              <input
                type="file"
                accept="application/pdf"
                style={{ display: "none" }}
                onChange={(e) => setBlankBooklet(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "1rem", marginTop: "1.5rem" }}>
          <Link to="/" className="btn btn-secondary">Cancel</Link>
          <button type="submit" disabled={loading} className="btn btn-primary">
            {loading ? "Deriving Template..." : (
              <>
                <FolderPlus size={18} /> Initialize Project & Derive Template
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
