import { ArrowRight, CheckCircle2, Clock, FileCheck, FolderPlus, Layers, ShieldLock, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { deleteProject, listProjects, ProjectSummary } from "../api/client";
import { errorMessage, formatDate } from "../ui";
import BrandedLoader from "../components/BrandedLoader";

export default function ProjectList() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadProjects = () => {
    setLoading(true);
    setError("");
    listProjects()
      .then(setProjects)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const needsReview = useMemo(
    () => projects.filter((project) => !project.template_map_confirmed || !project.question_bank_confirmed).length,
    [projects]
  );
  const confirmedTemplates = useMemo(
    () => projects.filter((project) => project.template_map_confirmed).length,
    [projects]
  );

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Move “${name}” to Trash? It will remain recoverable for 30 days.`)) return;
    setDeletingId(id);
    setError("");
    try {
      await deleteProject(id);
      setProjects((prev) => prev.filter((project) => project.id !== id));
    } catch (err) {
      setError(`Project could not be deleted. ${errorMessage(err)}`);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-title-group">
          <div className="eyebrow">Projects</div>
          <h1>Evaluation projects</h1>
          <p>Manage assessment rubrics, template maps, answer sheets, and examiner reviews.</p>
        </div>
        <div className="button-row">
          <Link to="/trash" className="btn btn-secondary"><Trash2 size={16} /> Trash</Link>
          <Link to="/projects/new" className="btn btn-primary"><FolderPlus size={18} /> Create project</Link>
        </div>
      </div>

      <div className="stats-grid">
        <div className="card stat-card">
          <div className="stat-icon stat-icon-indigo"><Layers size={21} /></div>
          <div><strong>{projects.length}</strong><span>Total projects</span></div>
        </div>
        <div className="card stat-card">
          <div className="stat-icon stat-icon-success"><FileCheck size={21} /></div>
          <div><strong>{confirmedTemplates}</strong><span>Templates confirmed</span></div>
        </div>
        <div className="card stat-card">
          <div className="stat-icon stat-icon-warning"><Clock size={21} /></div>
          <div><strong>{needsReview}</strong><span>Projects needing review</span></div>
        </div>
      </div>

      {error && (
        <div className="alert alert-error" role="alert">
          <span><strong>Projects could not be loaded.</strong> {error}</span>
          <button type="button" className="btn btn-quiet" onClick={loadProjects}>Retry</button>
        </div>
      )}

      {loading ? (
        <div className="page-narrow"><div className="processing-card" role="status"><BrandedLoader message="Loading projects…" /></div></div>
      ) : projects.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><Layers size={28} /></div>
          <h3>No projects yet</h3>
          <p>Create an assessment project from a rubric, question paper, and blank answer booklet.</p>
          <Link to="/projects/new" className="btn btn-primary"><FolderPlus size={18} /> Create project</Link>
        </div>
      ) : (
        <div className="card-grid">
          {projects.map((project) => {
            const ready = project.template_map_confirmed && project.question_bank_confirmed;
            return (
              <article key={project.id} className="card project-card">
                <div>
                  <div className="project-card-topline">
                    <span className={`badge ${ready ? "badge-success" : "badge-warning"}`}>
                      {ready ? <CheckCircle2 size={12} /> : <Clock size={12} />}
                      {ready ? "Ready for answer sheets" : "Setup needs review"}
                    </span>
                    {project.rubric_locked && <span className="badge badge-indigo"><ShieldLock size={12} /> Rubric locked</span>}
                  </div>
                  <h2>{project.name}</h2>
                  <p className="muted-text">Created {formatDate(project.created_at)}</p>
                  <p className="project-next-action">
                    {ready ? "Upload an answer sheet to begin processing." : !project.template_map_confirmed ? "Review the template map before uploading." : "Review and confirm the question bank before grading."}
                  </p>
                </div>
                <div className="project-card-footer">
                  <span className="id-text">ID {project.id.slice(0, 8)}</span>
                  <div className="button-row">
                    <button
                      type="button"
                      className="icon-button danger"
                      onClick={() => handleDelete(project.id, project.name)}
                      disabled={deletingId === project.id}
                      aria-label={`Delete ${project.name}`}
                      title="Move project to Trash"
                    >
                      <Trash2 size={15} />
                    </button>
                    <Link to={`/projects/${project.id}`} className="btn btn-secondary btn-sm">Open <ArrowRight size={14} /></Link>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
