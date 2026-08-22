import { AlertCircle, ArrowLeft, Check, FileText, FolderPlus, ShieldLock, Upload } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createProject } from "../api/client";
import { errorMessage } from "../ui";

type DocumentKind = "rubric" | "questionPaper" | "blankBooklet";

const documentCopy: Record<DocumentKind, { title: string; description: string; icon: typeof FileText }> = {
  rubric: { title: "Official marking rubric", description: "The criteria used to assess answers. It becomes locked after project creation.", icon: ShieldLock },
  questionPaper: { title: "Question paper", description: "Provides the question structure and marks context for the assessment.", icon: FileText },
  blankBooklet: { title: "Blank answer booklet", description: "Used to derive the candidate answer-region template for this booklet format.", icon: FileText },
};

export default function CreateProject() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [rubric, setRubric] = useState<File | null>(null);
  const [questionPaper, setQuestionPaper] = useState<File | null>(null);
  const [blankBooklet, setBlankBooklet] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const files: Record<DocumentKind, File | null> = { rubric, questionPaper, blankBooklet };
  const setters: Record<DocumentKind, (file: File | null) => void> = { rubric: setRubric, questionPaper: setQuestionPaper, blankBooklet: setBlankBooklet };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    if (!name.trim()) return setError("Enter a project name before continuing.");
    if (!rubric || !questionPaper || !blankBooklet) return setError("Select all three PDF documents before creating the project.");

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("name", name.trim());
      formData.append("rubric", rubric);
      formData.append("question_paper", questionPaper);
      formData.append("blank_booklet", blankBooklet);
      const project = await createProject(formData);
      navigate(`/projects/${project.id}/template-map`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="page-narrow">
        <div className="processing-card" role="status">
          <div className="spinner" />
          <h2>Creating project and deriving template…</h2>
          <p>Your source files are being prepared. Keep this window open until the template review is ready.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-narrow">
      <div className="breadcrumb"><Link to="/"><ArrowLeft size={14} /> Back to projects</Link></div>
      <div className="page-header">
        <div className="page-title-group">
          <div className="eyebrow">New assessment</div>
          <h1>Create evaluation project</h1>
          <p>Upload the three source documents used to prepare this assessment.</p>
        </div>
      </div>

      {error && <div className="alert alert-error" role="alert"><AlertCircle size={18} /><span><strong>Project could not be created.</strong> {error}</span></div>}

      <form onSubmit={onSubmit} className="card form-card">
        <div className="form-group">
          <label className="form-label" htmlFor="project-name">Project name</label>
          <input id="project-name" className="form-input" placeholder="e.g. Physics Midterm Examination 2026" value={name} onChange={(event) => setName(event.target.value)} required />
        </div>

        <div className="section-heading"><div><h2>Source documents</h2><p>Each document is used for a different part of the preparation process.</p></div></div>
        <div className="file-stack">
          {(Object.keys(documentCopy) as DocumentKind[]).map((kind, index) => {
            const copy = documentCopy[kind];
            const Icon = copy.icon;
            const file = files[kind];
            return (
              <div className={`file-dropzone ${file ? "has-file" : ""}`} key={kind}>
                <label className="file-choice" htmlFor={`file-${kind}`}>
                  <span className={`file-icon ${file ? "is-ready" : ""}`}>{file ? <Check size={20} /> : <Icon size={20} />}</span>
                  <span className="file-copy"><strong>{index + 1}. {copy.title}</strong><small>{file ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB` : copy.description}</small></span>
                  <span className="btn btn-secondary btn-sm">{file ? "Replace file" : "Choose PDF"}</span>
                  <input id={`file-${kind}`} type="file" accept="application/pdf,.pdf" onChange={(event) => setters[kind](event.target.files?.[0] ?? null)} />
                </label>
              </div>
            );
          })}
        </div>

        <div className="info-panel">
          <strong>What happens next</strong>
          <p>The project will be created, then you will review the candidate template map before uploading answer sheets. The rubric and approved assessment criteria are intended to remain fixed for consistent grading.</p>
        </div>

        <div className="form-actions"><Link to="/" className="btn btn-secondary">Cancel</Link><button type="submit" className="btn btn-primary"><FolderPlus size={17} /> Create project and derive template</button></div>
      </form>
    </div>
  );
}
