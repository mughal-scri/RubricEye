import { AlertTriangle, ArrowLeft, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hardDeleteProject, listTrash, ProjectSummary, restoreProject } from "../api/client";
import { errorMessage, formatDate } from "../ui";

export default function Trash() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    setLoading(true); setError("");
    listTrash().then(setProjects).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const restore = async (project: ProjectSummary) => {
    setBusyId(project.id); setError("");
    try { await restoreProject(project.id); setProjects((prev) => prev.filter((item) => item.id !== project.id)); } catch (err) { setError(errorMessage(err)); } finally { setBusyId(null); }
  };

  const removeForever = async (project: ProjectSummary) => {
    if (!window.confirm(`Delete “${project.name}” forever? This cannot be undone.`)) return;
    setBusyId(project.id); setError("");
    try { await hardDeleteProject(project.id); setProjects((prev) => prev.filter((item) => item.id !== project.id)); } catch (err) { setError(errorMessage(err)); } finally { setBusyId(null); }
  };

  const clearAll = async () => {
    if (!projects.length || !window.confirm(`Delete all ${projects.length} project${projects.length === 1 ? "" : "s"} in Trash forever?`)) return;
    setBusyId("all"); setError("");
    try { await Promise.all(projects.map((project) => hardDeleteProject(project.id))); setProjects([]); } catch (err) { setError(errorMessage(err)); load(); } finally { setBusyId(null); }
  };

  return <div>
    <div className="breadcrumb"><Link to="/"><ArrowLeft size={14} /> Back to projects</Link><span>/</span><span>Trash</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Recovery</div><h1>Trash</h1><p>Deleted projects remain recoverable for 30 days before automatic cleanup.</p></div>{projects.length > 0 && <button type="button" className="btn btn-danger" onClick={clearAll} disabled={busyId !== null}><Trash2 size={16} /> Delete all forever</button>}</div>
    {error && <div className="alert alert-error" role="alert"><AlertTriangle size={17} /><span>{error}</span><button type="button" className="btn btn-quiet" onClick={load}>Retry</button></div>}
    {loading ? <div className="loading-state" role="status">Loading Trash…</div> : projects.length === 0 ? <div className="empty-state"><div className="empty-state-icon"><Trash2 size={28} /></div><h3>Trash is empty</h3><p>Projects moved to Trash will appear here for recovery.</p><Link to="/" className="btn btn-secondary">Back to projects</Link></div> : <div className="card-grid">{projects.map((project) => <article className="card project-card" key={project.id}><div><span className="badge badge-slate">Deleted {project.deleted_at ? formatDate(project.deleted_at) : "recently"}</span><h2>{project.name}</h2><p className="muted-text">Project data and answer-sheet results are retained until permanently deleted.</p></div><div className="project-card-footer"><span className="id-text">ID {project.id.slice(0, 8)}</span><div className="button-row"><button type="button" className="btn btn-secondary btn-sm" onClick={() => restore(project)} disabled={busyId !== null}><RotateCcw size={14} /> Restore</button><button type="button" className="btn btn-danger btn-sm" onClick={() => removeForever(project)} disabled={busyId !== null}><Trash2 size={14} /> Delete forever</button></div></div></article>)}</div>}
  </div>;
}
