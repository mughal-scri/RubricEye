import { AlertCircle, ArrowLeft, FileDown, FileText, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import FilePicker from "../components/FilePicker";
import RubricCriteriaEditor from "../components/RubricCriteriaEditor";
import { approveRubricStudio, fileUrl, generateRubricStudio, getRubricStudio, RubricStudioCriterion, updateRubricStudioCriterion, uploadManualRubric } from "../api/client";
import { errorMessage } from "../ui";

export default function RubricStudio() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [criteria, setCriteria] = useState<RubricStudioCriterion[]>([]);
  const [status, setStatus] = useState("loading");
  const [warning, setWarning] = useState<string | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const load = () => {
    if (!projectId) return;
    setLoading(true); setError("");
    getRubricStudio(projectId).then((data) => { setCriteria(data.criteria); setStatus(data.status); setWarning(data.warning); setDownloadUrl(data.generated_rubric_download_url ?? null); }).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  };
  useEffect(load, [projectId]);

  const generate = async () => {
    if (!projectId || status === "approved") return;
    setSaving(true); setError("");
    try { const data = await generateRubricStudio(projectId); setCriteria(data.criteria); setStatus(data.status); setWarning(data.warning); setDownloadUrl(data.generated_rubric_download_url ?? null); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  const incompleteCount = useMemo(() => criteria.filter((criterion) => !criterion.key_points?.trim() || criterion.marks_possible === null).length, [criteria]);
  const updateLocal = (questionNumber: string, field: "marks_possible" | "key_points", value: string | number | null) => setCriteria((current) => current.map((criterion) => criterion.question_number === questionNumber ? { ...criterion, [field]: value } : criterion));
  const save = async (criterion: RubricStudioCriterion) => {
    if (!projectId || status === "approved") return;
    setSaving(true); setError("");
    try { await updateRubricStudioCriterion(projectId, criterion.question_number, { marks_possible: criterion.marks_possible, key_points: criterion.key_points }); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };
  const approve = async () => {
    if (!projectId || incompleteCount) return;
    setSaving(true); setError("");
    try { const data = await approveRubricStudio(projectId); setStatus(data.status); setDownloadUrl(data.generated_rubric_download_url ?? null); setCriteria(data.criteria); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };
  const manualUpload = async () => {
    if (!projectId || !selectedFile) return;
    setSaving(true); setError("");
    try { await uploadManualRubric(projectId, selectedFile); navigate(`/projects/${projectId}/question-bank`); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  if (!projectId) return null;
  if (loading) return <div className="loading-state" role="status">Loading Rubric Studio…</div>;
  if (error && !criteria.length && status === "loading") return <div className="empty-state"><h3>Rubric Studio could not be loaded</h3><p>{error}</p><button type="button" className="btn btn-primary" onClick={load}><RotateCcw size={15} /> Retry</button></div>;

  return <div className="page-narrow rubric-studio-page">
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Rubric Studio</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">{status === "approved" ? "Approved rubric viewer" : "Human-reviewed rubric drafting"}</div><div className="title-with-badges"><h1>Rubric Studio</h1><span className={`badge ${status === "approved" ? "badge-success" : status === "draft_ready" ? "badge-warning" : "badge-slate"}`}>{status.replace(/_/g, " ")}</span></div><p>{status === "approved" ? "This rubric was approved during project creation and is now locked. Download the structured PDF or return to the project." : "Review the generated questions in paper order, edit the criteria, and save the rubric when the draft is complete."}</p></div><div className="button-row">{downloadUrl && <a className="btn btn-secondary" href={fileUrl(downloadUrl)} download="rubric.pdf"><FileDown size={15} /> Download PDF</a>}<button type="button" className="btn btn-secondary" onClick={load} disabled={saving}><RotateCcw size={15} /> Refresh</button>{status !== "approved" && <button type="button" className="btn btn-secondary" onClick={generate} disabled={saving}><Sparkles size={15} /> {criteria.length ? "Regenerate draft" : "Generate draft"}</button>}{status !== "approved" && criteria.length > 0 && <button type="button" className="btn btn-success" onClick={approve} disabled={saving || incompleteCount > 0}><ShieldCheck size={16} /> Save reviewed rubric</button>}</div></div>
    {error && <div className="alert alert-error" role="alert"><AlertCircle size={17} /><span>{error}</span></div>}
    {status === "approved" && <div className="alert alert-info rubric-locked-notice" role="status"><ShieldCheck size={17} /><span><strong>Approved rubric is locked.</strong> It was reviewed and saved during project creation; per-project editing is intentionally unavailable.</span></div>}
    {status === "needs_generation" && <div className="alert alert-warning" role="status"><AlertCircle size={17} /><span><strong>Project creation did not finish saving the rubric.</strong> Generate and approve it here to continue.</span></div>}
    {warning && <div className="alert alert-warning" role="status"><AlertCircle size={17} /><span>{warning}</span></div>}
    {status === "manual_required" && <section className="card fallback-card"><div className="fallback-icon"><FileText size={22} /></div><div><h2>Use an official rubric instead</h2><p>Studio generation did not complete. Upload the marking scheme and continue with the normal Question Bank review.</p><FilePicker id="manual-rubric" file={selectedFile} emptyLabel="Choose official rubric PDF" emptyHint="PDF files only" readyHint="Official source selected" onChange={setSelectedFile} /><button type="button" className="btn btn-primary" onClick={manualUpload} disabled={!selectedFile || saving}>Use uploaded rubric</button></div></section>}
    {criteria.length > 0 && <><div className={`structure-summary ${incompleteCount === 0 ? "is-resolved" : ""}`}><div><span className="eyebrow">Review progress</span><strong>{criteria.length - incompleteCount} of {criteria.length} criteria complete</strong><p>{incompleteCount ? `${incompleteCount} still need marks or criteria text.` : status === "approved" ? "This rubric is saved and ready for Question Bank setup." : "All generated criteria are ready for one final save."}</p></div><div className="structure-metrics"><span><b>{criteria.length}</b> questions</span><span><b>{incompleteCount}</b> open</span></div></div><RubricCriteriaEditor criteria={criteria} readOnly={status === "approved"} saving={saving} onChange={updateLocal} onSave={(criterion) => void save(criterion as RubricStudioCriterion)} /></>}
    {!criteria.length && status !== "manual_required" && <div className="empty-state"><Sparkles size={26} /><h3>No rubric criteria yet</h3><p>Generate a draft from the project’s question paper or use the manual upload fallback.</p></div>}
  </div>;
}
