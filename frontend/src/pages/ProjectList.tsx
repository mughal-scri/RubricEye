import { CheckCircle2, Clock, FolderPlus, Layers, FileCheck, ArrowRight, ShieldLock, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { deleteProject, listProjects, ProjectSummary } from "../api/client";

export default function ProjectList() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadProjects = () => {
    setLoading(true);
    listProjects()
      .then((data) => {
        setProjects(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Are you sure you want to permanently delete project "${name}"? This action cannot be undone.`)) {
      return;
    }
    setDeletingId(id);
    setError("");
    try {
      await deleteProject(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (err) {
      setError(`Failed to delete project: ${String(err)}`);
    } finally {
      setDeletingId(null);
    }
  };

  const totalProjects = projects.length;
  const confirmedTemplates = projects.filter((p) => p.template_map_confirmed).length;

  return (
    <div>
      <div className="page-header">
        <div className="page-title-group">
          <h1>Evaluation Projects</h1>
          <p>Manage exam rubrics, template region maps, and answer sheet uploads.</p>
        </div>
        <Link to="/projects/new" className="btn btn-primary">
          <FolderPlus size={18} /> Create New Project
        </Link>
      </div>

      {/* Quick Stats Banner */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem", marginBottom: "2rem" }}>
        <div className="card" style={{ padding: "1.25rem", display: "flex", alignItems: "center", gap: "1rem" }}>
          <div style={{ padding: "10px", background: "var(--color-brand-50)", borderRadius: "var(--radius-md)", color: "var(--color-brand-600)" }}>
            <Layers size={24} />
          </div>
          <div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, fontFamily: "var(--font-display)" }}>{totalProjects}</div>
            <div style={{ fontSize: "0.85rem", color: "var(--color-slate-500)" }}>Total Projects</div>
          </div>
        </div>

        <div className="card" style={{ padding: "1.25rem", display: "flex", alignItems: "center", gap: "1rem" }}>
          <div style={{ padding: "10px", background: "var(--color-emerald-50)", borderRadius: "var(--radius-md)", color: "var(--color-emerald-600)" }}>
            <FileCheck size={24} />
          </div>
          <div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, fontFamily: "var(--font-display)" }}>{confirmedTemplates}</div>
            <div style={{ fontSize: "0.85rem", color: "var(--color-slate-500)" }}>Templates Confirmed</div>
          </div>
        </div>

        <div className="card" style={{ padding: "1.25rem", display: "flex", alignItems: "center", gap: "1rem" }}>
          <div style={{ padding: "10px", background: "var(--color-amber-50)", borderRadius: "var(--radius-md)", color: "var(--color-amber-600)" }}>
            <ShieldLock size={24} />
          </div>
          <div>
            <div style={{ fontSize: "1.5rem", fontWeight: 800, fontFamily: "var(--font-display)" }}>100%</div>
            <div style={{ fontSize: "0.85rem", color: "var(--color-slate-500)" }}>Anti-Bias Lock Active</div>
          </div>
        </div>
      </div>

      {error && (
        <div className="alert alert-error">
          <span>Failed to load projects: {error}</span>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: "center", padding: "3rem", color: "var(--color-slate-500)" }}>
          Loading projects...
        </div>
      ) : projects.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <Layers size={28} />
          </div>
          <h3>No projects yet</h3>
          <p>Get started by scaffolding your first evaluation project with rubric PDFs.</p>
          <Link to="/projects/new" className="btn btn-primary">
            <FolderPlus size={18} /> Create Project
          </Link>
        </div>
      ) : (
        <div className="card-grid">
          {projects.map((project) => (
            <div key={project.id} className="card" style={{ display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "0.75rem" }}>
                  <span className={`badge ${project.template_map_confirmed ? "badge-success" : "badge-warning"}`}>
                    {project.template_map_confirmed ? (
                      <>
                        <CheckCircle2 size={12} /> Confirmed
                      </>
                    ) : (
                      <>
                        <Clock size={12} /> Pending Review
                      </>
                    )}
                  </span>

                  {project.rubric_locked && (
                    <span className="badge badge-indigo" title="Rubric is permanently locked against modification">
                      <ShieldLock size={12} /> Rubric Locked
                    </span>
                  )}
                </div>

                <h3 style={{ fontSize: "1.2rem", fontWeight: 700, fontFamily: "var(--font-display)", color: "var(--color-slate-900)", marginBottom: "0.5rem" }}>
                  {project.name}
                </h3>
                <p style={{ fontSize: "0.85rem", color: "var(--color-slate-500)", marginBottom: "1.25rem" }}>
                  Created {new Date(project.created_at).toLocaleDateString()} at {new Date(project.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>

              <div style={{ borderTop: "1px solid var(--color-slate-100)", paddingTop: "1rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "0.8rem", color: "var(--color-slate-600)" }}>
                  ID: <code style={{ fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>{project.id.slice(0, 8)}</code>
                </span>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    className="btn btn-danger"
                    style={{ padding: "0.4rem 0.6rem", fontSize: "0.85rem" }}
                    onClick={() => handleDelete(project.id, project.name)}
                    disabled={deletingId === project.id}
                    title="Delete project permanently"
                  >
                    <Trash2 size={14} />
                  </button>
                  <Link to={`/projects/${project.id}`} className="btn btn-secondary" style={{ padding: "0.4rem 0.85rem", fontSize: "0.85rem" }}>
                    Open <ArrowRight size={14} />
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
