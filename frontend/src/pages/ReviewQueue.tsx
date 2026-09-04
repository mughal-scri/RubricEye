import { AlertTriangle, ArrowLeft, CheckCircle2, ChevronDown, ChevronRight, ClipboardCheck, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getProject, getProjectReviewQueue, ProjectDetail, ProjectReviewQueueResponse } from "../api/client";
import { errorMessage, gradingStatusLabel, reviewStateBadge } from "../ui";
import BrandedLoader from "../components/BrandedLoader";

export default function ReviewQueue() {
  const { projectId } = useParams();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [queue, setQueue] = useState<ProjectReviewQueueResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedSheets, setExpandedSheets] = useState<Set<string>>(new Set());

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    Promise.all([getProject(projectId), getProjectReviewQueue(projectId)])
      .then(([projectData, queueData]) => {
        setProject(projectData);
        setQueue(queueData);
        // Auto-expand the first sheet with pending items.
        if (queueData.sheets.length > 0) {
          setExpandedSheets(new Set([queueData.sheets[0].answer_sheet_id]));
        }
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  };
  useEffect(load, [projectId]);

  const toggleExpand = (sheetId: string) => {
    setExpandedSheets((prev) => {
      const next = new Set(prev);
      if (next.has(sheetId)) next.delete(sheetId);
      else next.add(sheetId);
      return next;
    });
  };

  if (!projectId) return null;
  if (loading) return <div className="page-narrow"><div className="processing-card" role="status"><BrandedLoader message="Loading review queue…" /></div></div>;
  if (error && !queue) return <div className="empty-state"><h3>Review queue could not be loaded</h3><p>{error}</p><button type="button" className="btn btn-primary" onClick={load}><RotateCcw size={15} /> Retry</button></div>;
  if (!project || !queue) return null;

  const allReviewed = queue.total_pending === 0 && queue.sheets.length === 0;

  return (
    <div>
      <div className="breadcrumb">
        <Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link>
        <span aria-hidden="true">/</span>
        <span>Review queue</span>
      </div>
      <div className="page-header">
        <div className="page-title-group">
          <div className="eyebrow">Examiner review</div>
          <div className="title-with-badges">
            <h1>Review queue</h1>
            {queue.total_pending > 0
              ? <span className="badge badge-warning"><ClipboardCheck size={12} /> {queue.total_pending} pending</span>
              : <span className="badge badge-success"><CheckCircle2 size={12} /> All reviewed</span>
            }
          </div>
          <p>{project.name} — items that need examiner confirmation before the report can be generated.</p>
        </div>
      </div>

      {error && <div className="alert alert-error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button type="button" className="btn btn-quiet" onClick={load}>Retry</button></div>}

      {allReviewed ? (
        <div className="empty-state">
          <div className="empty-state-icon"><CheckCircle2 size={28} /></div>
          <h3>All results have been confirmed</h3>
          <p>Every gradable answer across this project has an examiner decision. You can generate reports from individual answer sheet results.</p>
          <Link to={`/projects/${projectId}`} className="btn btn-primary">Back to project</Link>
        </div>
      ) : queue.sheets.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon"><ClipboardCheck size={28} /></div>
          <h3>No answer sheets have been graded yet</h3>
          <p>Grade an answer sheet from the project page to start reviewing AI-scored results.</p>
          <Link to={`/projects/${projectId}`} className="btn btn-secondary">Back to project</Link>
        </div>
      ) : (
        <div className="review-queue-dashboard">
          {queue.sheets.map((sheet) => {
            const isExpanded = expandedSheets.has(sheet.answer_sheet_id);
            const status = gradingStatusLabel(sheet.grading_status);
            const progressPercent = sheet.total_reviewable > 0 ? Math.round((sheet.reviewed_count / sheet.total_reviewable) * 100) : 0;
            return (
              <article className="card review-sheet-card" key={sheet.answer_sheet_id}>
                <button type="button" className="review-sheet-header" onClick={() => toggleExpand(sheet.answer_sheet_id)} aria-expanded={isExpanded}>
                  <div className="review-sheet-title">
                    {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                    <strong>Roll {sheet.roll_number}</strong>
                    <span className={`badge badge-${status.tone}`}>{status.label}</span>
                  </div>
                  <div className="review-sheet-stats">
                    <span>{sheet.reviewed_count}/{sheet.total_reviewable} reviewed</span>
                    <span className="review-progress-bar">
                      <span className="review-progress-fill" style={{ width: `${progressPercent}%` }} />
                    </span>
                    <span className="badge badge-warning">{sheet.pending_count} pending</span>
                  </div>
                </button>
                {isExpanded && (
                  <div className="review-sheet-body">
                    <div className="table-container">
                      <table className="table">
                        <thead>
                          <tr>
                            <th>Question</th>
                            <th>AI score</th>
                            <th>State</th>
                            <th>Confidence</th>
                            <th>Ink</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sheet.pending_items.map((item) => {
                            const state = reviewStateBadge(item.review_state);
                            return (
                              <tr key={item.question_number}>
                                <td>
                                  <strong>Q{item.question_number}</strong>
                                  {item.truncation_flag && <span className="badge badge-danger" title="Possible crop overflow">overflow</span>}
                                </td>
                                <td>{item.ai_score !== null ? `${item.ai_score} / ${item.ai_total_possible ?? "?"}` : "—"}</td>
                                <td><span className={`badge badge-${state.tone}`}>{state.label}</span></td>
                                <td>{item.confidence}</td>
                                <td>{item.ink_status}{item.ink_density_ratio !== null ? ` (${item.ink_density_ratio.toFixed(3)})` : ""}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    <div className="review-sheet-actions">
                      <Link to={`/projects/${projectId}/answer-sheets/${sheet.answer_sheet_id}/results`} className="btn btn-primary btn-sm">
                        <ClipboardCheck size={14} /> Open review for Roll {sheet.roll_number}
                      </Link>
                    </div>
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
