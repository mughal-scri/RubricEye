import { AlertCircle, ArrowLeft, CheckCircle2, Link2, ShieldCheck, Unlink } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { approveRubricStudio, getRubricStudio, RubricStudioResponse, updateRubricAlignment } from "../api/client";
import { errorMessage } from "../ui";

export default function RubricAlignment() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<RubricStudioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    getRubricStudio(projectId)
      .then(setData)
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  };
  useEffect(load, [projectId]);

  const candidates = useMemo(() => data?.alignment_candidates ?? [], [data]);
  const saveDecision = async (questionNumber: string, status: "linked" | "not_applicable" | "unreviewed", linkedQuestionNumber?: string | null) => {
    if (!projectId) return;
    setSaving(questionNumber);
    setError("");
    setMessage("");
    try {
      const next = await updateRubricAlignment(projectId, questionNumber, { status, linked_question_number: linkedQuestionNumber ?? null });
      setData(next);
      setMessage(`Alignment decision saved for ${questionNumber}.`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(null);
    }
  };

  const approve = async () => {
    if (!projectId || !data?.all_alignment_reviewed) return;
    setSaving("__approve__");
    setError("");
    try {
      await approveRubricStudio(projectId);
      navigate(`/projects/${projectId}/rubric-studio`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(null);
    }
  };

  if (!projectId) return null;
  if (loading) return <div className="loading-state" role="status">Loading rubric alignment…</div>;
  if (!data) return <div className="empty-state"><h3>Rubric alignment unavailable</h3><p>{error || "The Studio draft could not be loaded."}</p><button type="button" className="btn btn-secondary" onClick={load}>Retry</button></div>;

  return <div className="page-narrow rubric-alignment-page">
    <div className="breadcrumb"><Link to={`/projects/${projectId}/rubric-studio`}><ArrowLeft size={14} /> Rubric Studio</Link><span>/</span><span>Alignment review</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Trust checkpoint</div><h1>Rubric alignment review</h1><p>Confirm that every generated criterion belongs to a canonical question from the uploaded paper, or explicitly mark it not applicable.</p></div><div className="button-row"><Link to={`/projects/${projectId}/rubric-studio`} className="btn btn-secondary">Back to Studio</Link><button type="button" className="btn btn-success" onClick={() => void approve()} disabled={!data.all_alignment_reviewed || saving !== null}><ShieldCheck size={15} /> Approve and lock</button></div></div>
    {error && <div className="alert alert-error" role="alert"><AlertCircle size={17} /><span>{error}</span></div>}
    {message && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>{message}</span></div>}
    <div className={`structure-summary ${data.all_alignment_reviewed ? "is-resolved" : ""}`}><div><span className="eyebrow">Review status</span><strong>{data.all_alignment_reviewed ? "Every criterion has an examiner decision" : "Alignment decisions are still required"}</strong><p>{data.all_alignment_reviewed ? "The rubric may now be approved and locked." : "Low-confidence or unmatched criteria must not pass silently into grading."}</p></div><div className="structure-metrics"><span><b>{data.criteria.filter((criterion) => criterion.alignment_status !== "unreviewed").length}</b> decided</span><span><b>{data.criteria.length}</b> criteria</span></div></div>
    <section className="card alignment-list"><div className="section-heading compact"><div><h2>Criterion ↔ question mapping</h2><p>Provider confidence is evidence for review, not an approval decision.</p></div></div>{data.criteria.map((criterion) => <article className="alignment-row" key={criterion.id}><div className="alignment-criterion"><div className="alignment-title"><strong>{criterion.question_number}</strong><span className={`badge ${criterion.rubric_confidence === "high" ? "badge-success" : criterion.rubric_confidence === "medium" ? "badge-warning" : "badge-danger"}`}>{criterion.rubric_confidence ?? "low"} confidence</span></div><p>{criterion.question_text || criterion.key_points || "No criterion text recorded."}</p><small>{criterion.rubric_provenance || "No provenance recorded."}</small></div><div className="alignment-decision"><label className="form-label" htmlFor={`alignment-${criterion.id}`}>Canonical question</label><select id={`alignment-${criterion.id}`} className="form-input" value={criterion.alignment_status === "not_applicable" ? "__na__" : criterion.alignment_question_number ?? ""} disabled={saving === criterion.question_number || data.status === "approved"} onChange={(event) => { const value = event.target.value; if (value === "__na__") void saveDecision(criterion.question_number, "not_applicable"); else if (value) void saveDecision(criterion.question_number, "linked", value); else void saveDecision(criterion.question_number, "unreviewed"); }}><option value="">Choose a question key…</option>{candidates.map((candidate) => <option key={candidate.question_number} value={candidate.question_number}>{candidate.question_number}{candidate.marks_possible !== null ? ` · ${candidate.marks_possible} marks` : ""}</option>)}<option value="__na__">Not applicable — exclude from grading</option></select><div className="alignment-state">{criterion.alignment_status === "linked" ? <span className="saved-note"><Link2 size={14} /> Linked to {criterion.alignment_question_number}</span> : criterion.alignment_status === "not_applicable" ? <span className="muted-text"><Unlink size={14} /> Marked not applicable</span> : <span className="text-warning">Decision required</span>}</div></div></article>)}</section>
  </div>;
}
