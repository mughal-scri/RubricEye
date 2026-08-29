import { ArrowLeft, CheckCircle2, Clock3, Eye, FileCheck2, FileDown, FileUp, GraduationCap, Layers, ListChecks, ShieldLock, Sparkles, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnswerSheetSummary, deleteAnswerSheet, fileUrl, getProject, gradeAnswerSheet, hardDeleteAnswerSheet, listAnswerSheets, listDeletedAnswerSheets, listQuestionBank, pollGradingJob, ProjectDetail as ProjectDetailType, restoreAnswerSheet } from "../api/client";
import { errorMessage, formatDate, gradingStatusLabel } from "../ui";

export default function ProjectDetailPage() {
  const { projectId } = useParams();
  const [project, setProject] = useState<ProjectDetailType | null>(null);
  const [sheets, setSheets] = useState<AnswerSheetSummary[]>([]);
  const [deletedSheets, setDeletedSheets] = useState<AnswerSheetSummary[]>([]);
  const [questionBankCount, setQuestionBankCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [gradingSheetId, setGradingSheetId] = useState<string | null>(null);
  const [sheetActionId, setSheetActionId] = useState<string | null>(null);

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    Promise.all([getProject(projectId), listAnswerSheets(projectId), listDeletedAnswerSheets(projectId), listQuestionBank(projectId)])
      .then(([projectData, sheetData, deletedSheetData, qbData]) => {
        setProject(projectData);
        setSheets(sheetData);
        setDeletedSheets(deletedSheetData);
        setQuestionBankCount(qbData.items.length);
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId]);

  const ready = Boolean(project?.template_map_confirmed && project?.question_bank_confirmed);
  const pendingSheets = useMemo(() => sheets.filter((sheet) => sheet.grading_status === "review_required").length, [sheets]);
  const nextStep = project?.rubric_source_mode === "studio" && !project.rubric_locked
    ? { title: "Review rubric alignment before locking", body: "Confirm each Studio criterion against a canonical question or mark it not applicable before approval.", href: `/projects/${projectId}/rubric-alignment`, label: "Review alignment" }
    : !project?.template_map_confirmed
    ? { title: "Review the template map before uploading", body: "The detected regions must be confirmed before answer sheets can be prepared.", href: `/projects/${projectId}/template-map`, label: "Review template map" }
    : !project.question_bank_confirmed
      ? { title: "Confirm the question bank before grading", body: "Review question numbers, marks, and key points so grading uses the intended criteria.", href: `/projects/${projectId}/question-bank`, label: "Review question bank" }
      : pendingSheets > 0
        ? { title: `${pendingSheets} sheet${pendingSheets === 1 ? "" : "s"} ready for examiner review`, body: "AI grading is complete, but these results are not final until the examiner confirms them.", href: `/projects/${projectId}`, label: "Review answer sheets" }
        : { title: "Assessment setup is ready", body: "Upload an answer sheet to begin preparation and grading.", href: `/projects/${projectId}/upload`, label: "Upload answer sheet" };

  const removeSheet = async (sheet: AnswerSheetSummary) => {
    if (!projectId || !window.confirm(`Move answer sheet Roll ${sheet.roll_number} to Trash? It can be restored later.`)) return;
    setSheetActionId(sheet.id); setError("");
    try { await deleteAnswerSheet(projectId, sheet.id); await load(); } catch (err) { setError(errorMessage(err)); } finally { setSheetActionId(null); }
  };

  const restoreSheet = async (sheet: AnswerSheetSummary) => {
    if (!projectId) return;
    setSheetActionId(sheet.id); setError("");
    try { await restoreAnswerSheet(projectId, sheet.id); await load(); } catch (err) { setError(errorMessage(err)); } finally { setSheetActionId(null); }
  };

  const removeSheetForever = async (sheet: AnswerSheetSummary) => {
    if (!projectId || !window.confirm(`Permanently delete Roll ${sheet.roll_number}? This removes the answer sheet files and cannot be undone.`)) return;
    setSheetActionId(sheet.id); setError("");
    try { await hardDeleteAnswerSheet(projectId, sheet.id); await load(); } catch (err) { setError(errorMessage(err)); } finally { setSheetActionId(null); }
  };

  const triggerGrade = async (sheetId: string) => {
    if (!projectId) return;
    setGradingSheetId(sheetId);
    setError("");
    try {
      const { job_id } = await gradeAnswerSheet(projectId, sheetId);
      if (job_id !== "already-processed") {
        await pollGradingJob(job_id);
      }
      load();
    } catch (err) {
      setError(`The sheet could not be graded. ${errorMessage(err)}`);
    } finally {
      setGradingSheetId(null);
    }
  };

  if (!projectId) return null;
  if (loading) return <div className="loading-state" role="status">Loading project…</div>;
  if (!project) return <div className="empty-state"><h3>Project unavailable</h3><p>{error || "This project could not be loaded."}</p><Link to="/" className="btn btn-secondary">Back to projects</Link></div>;

  return (
    <div>
      <div className="breadcrumb"><Link to="/"><ArrowLeft size={14} /> Projects</Link><span>/</span><span>{project.name}</span></div>
      <div className="page-header">
        <div className="page-title-group">
          <div className="eyebrow">Assessment workspace</div>
          <div className="title-with-badges"><h1>{project.name}</h1><span className="badge badge-indigo"><ShieldLock size={12} /> {project.rubric_source_mode === "studio" ? "Studio rubric" : project.rubric_source_mode === "text" ? "Pasted rubric" : "Rubric locked"}</span></div>
          <p>Created {formatDate(project.created_at)} · Project ID <code className="id-text">{project.id.slice(0, 8)}</code></p>
        </div>
        <div className="button-row wrap">
          <Link to={`/projects/${projectId}/template-map`} className="btn btn-secondary"><Layers size={16} /> Template map</Link>
          <Link to={`/projects/${projectId}/question-bank`} className="btn btn-secondary"><ListChecks size={16} /> Question bank</Link>
          <Link to={`/projects/${projectId}/question-groups`} className="btn btn-secondary"><Sparkles size={16} /> Question groups</Link>
          {project.rubric_source_mode === "studio" && <><Link to={`/projects/${projectId}/rubric-studio`} className="btn btn-secondary"><Sparkles size={16} /> Rubric Studio</Link>{!project.rubric_locked && <Link to={`/projects/${projectId}/rubric-alignment`} className="btn btn-primary"><ListChecks size={16} /> Review alignment</Link>}</>}
          {project.rubric_download_url && <a href={fileUrl(project.rubric_download_url)} download="rubric.pdf" className="btn btn-secondary"><FileDown size={16} /> Download rubric</a>}
          {ready ? <Link to={`/projects/${projectId}/upload`} className="btn btn-primary"><Upload size={16} /> Upload answer sheet</Link> : <button type="button" className="btn btn-secondary" disabled title="Confirm the template map and question bank first"><Upload size={16} /> Upload locked</button>}
        </div>
      </div>

      {error && <div className="alert alert-error" role="alert"><span><strong>Action could not be completed.</strong> {error}</span><button type="button" className="btn btn-quiet" onClick={load}>Retry</button></div>}
      {project.template_map_error && <div className="alert alert-error" role="alert"><span><strong>Template preparation needs attention.</strong> {project.template_map_error}</span><Link to={`/projects/${projectId}/template-map`} className="alert-action">Review template map</Link></div>}
      {project.question_bank_marks_warning && <div className="alert alert-warning" role="alert"><span><strong>Review marks before locking.</strong> {project.question_bank_marks_warning}</span><Link to={`/projects/${projectId}/question-bank`} className="alert-action">Review question bank</Link></div>}

      <section className="next-step-panel" aria-labelledby="next-step-title">
        <div><span className="eyebrow">Recommended next step</span><h2 id="next-step-title">{nextStep.title}</h2><p>{nextStep.body}</p></div>
        <Link to={nextStep.href} className="btn btn-primary">{nextStep.label}</Link>
      </section>

      <div className="readiness-grid">
        <div className="card readiness-card"><div className="card-label"><ShieldLock size={17} /> Rubric</div><strong>{project.rubric_source_mode === "studio" ? "Studio draft saved" : project.rubric_source_mode === "text" ? "Pasted rubric saved" : "Official rubric locked"}</strong><p>Source criteria remain fixed for consistent grading.</p></div>
        <div className="card readiness-card"><div className="card-label"><Layers size={17} /> Template map</div><strong className={project.template_map_confirmed ? "text-success" : "text-warning"}>{project.template_map_confirmed ? "Confirmed and locked" : "Needs review before upload"}</strong><p>{project.template_map_status || "Candidate map status unavailable"}</p></div>
        <div className="card readiness-card"><div className="card-label"><GraduationCap size={17} /> Question bank</div><strong className={project.question_bank_confirmed ? "text-success" : "text-warning"}>{project.question_bank_confirmed ? "Confirmed" : "In draft"}</strong><p>{questionBankCount} question{questionBankCount === 1 ? "" : "s"} available{project.question_bank_effective_total !== null && project.question_bank_effective_total !== undefined ? ` · ${project.question_bank_effective_total} effective marks` : ""}.</p></div>
        <div className="card readiness-card"><div className="card-label"><FileUp size={17} /> Answer sheets</div><strong>{sheets.length} uploaded</strong><p>{pendingSheets} with AI results ready for review.</p></div>
      </div>

      <div className="section-heading"><div><h2>Answer sheets</h2><p>Track preparation, grading, and examiner review by roll number.</p></div>{ready && <Link to={`/projects/${projectId}/upload`} className="btn btn-primary btn-sm"><Upload size={15} /> Upload</Link>}</div>
      {sheets.length === 0 ? (
        <div className="empty-state"><div className="empty-state-icon"><FileUp size={28} /></div><h3>No answer sheets uploaded yet</h3><p>{ready ? "Upload a roll-number-identified booklet to begin." : "Confirm the template map and question bank before uploading."}</p>{ready && <Link to={`/projects/${projectId}/upload`} className="btn btn-primary"><Upload size={16} /> Upload answer sheet</Link>}</div>
      ) : (
        <div className="table-container"><table className="table"><thead><tr><th>Roll number</th><th>Pages</th><th>Uploaded</th><th>Preparation</th><th>Grading</th><th>Actions</th></tr></thead><tbody>{sheets.map((sheet) => { const status = gradingStatusLabel(sheet.grading_status); const canGrade = sheet.grading_status === "not_graded" || sheet.grading_status === "failed"; return <tr key={sheet.id}><td><strong>Roll {sheet.roll_number}</strong></td><td><span className="badge badge-slate">{sheet.page_count} pages</span></td><td className="muted-text">{formatDate(sheet.uploaded_at)}</td><td><span className="badge badge-slate"><CheckCircle2 size={12} /> Prepared for review</span></td><td><span className={`badge badge-${status.tone}`}>{status.label}</span></td><td><div className="button-row table-actions">{canGrade ? <button type="button" className="btn btn-primary btn-sm" disabled={!project.question_bank_confirmed || gradingSheetId === sheet.id} title={!project.question_bank_confirmed ? "Confirm the question bank first" : undefined} onClick={() => triggerGrade(sheet.id)}><GraduationCap size={14} />{gradingSheetId === sheet.id ? "Grading…" : "Grade"}</button> : <Link to={`/projects/${projectId}/answer-sheets/${sheet.id}/results`} className="btn btn-secondary btn-sm"><GraduationCap size={14} /> Review results</Link>}{sheet.report_ready && sheet.report_download_url && <a href={fileUrl(sheet.report_download_url)} download="examiner-report.pdf" className="btn btn-success btn-sm"><FileDown size={14} /> Report PDF</a>}<Link to={`/projects/${projectId}/answer-sheets/${sheet.id}`} className="btn btn-secondary btn-sm"><Eye size={14} /> Segmentation</Link><button type="button" className="btn btn-danger btn-sm" disabled={sheetActionId === sheet.id} onClick={() => removeSheet(sheet)}><Trash2 size={14} /> {sheetActionId === sheet.id ? "Moving…" : "Delete"}</button></div></td></tr>; })}</tbody></table></div>
      )}
      {deletedSheets.length > 0 && <section className="trash-section"><div className="section-heading"><div><h2>Trashed answer sheets</h2><p>Deleted sheets remain recoverable until permanently removed.</p></div><span className="badge badge-warning"><Trash2 size={12} /> {deletedSheets.length}</span></div><div className="table-container"><table className="table"><thead><tr><th>Roll number</th><th>Deleted</th><th>Actions</th></tr></thead><tbody>{deletedSheets.map((sheet) => <tr key={sheet.id}><td><strong>Roll {sheet.roll_number}</strong></td><td className="muted-text">{sheet.deleted_at ? formatDate(sheet.deleted_at) : "In Trash"}</td><td><div className="button-row table-actions"><button type="button" className="btn btn-secondary btn-sm" disabled={sheetActionId === sheet.id} onClick={() => restoreSheet(sheet)}>Restore</button><button type="button" className="btn btn-danger btn-sm" disabled={sheetActionId === sheet.id} onClick={() => removeSheetForever(sheet)}><Trash2 size={14} /> Delete permanently</button></div></td></tr>)}</tbody></table></div></section>}
    </div>
  );
}
