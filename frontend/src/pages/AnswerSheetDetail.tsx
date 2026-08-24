import { AlertCircle, ArrowLeft, CheckCircle2, FileText, GraduationCap, RotateCcw, ZoomIn } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnswerSheetDetail as AnswerSheetDetailType, fileUrl, getAnswerSheet, gradeAnswerSheet } from "../api/client";
import { errorMessage, formatDate, gradingStatusLabel } from "../ui";

export default function AnswerSheetDetailPage() {
  const { projectId, sheetId } = useParams();
  const [sheet, setSheet] = useState<AnswerSheetDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedPreviewUrl, setSelectedPreviewUrl] = useState<string | null>(null);
  const [grading, setGrading] = useState(false);

  const load = () => {
    if (!projectId || !sheetId) return;
    setLoading(true); setError("");
    getAnswerSheet(projectId, sheetId).then(setSheet).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  };
  useEffect(load, [projectId, sheetId]);

  const grade = async () => {
    if (!projectId || !sheetId) return;
    setGrading(true); setError("");
    try {
      await gradeAnswerSheet(projectId, sheetId);
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setGrading(false);
    }
  };

  if (!projectId || !sheetId) return null;
  if (loading) return <div className="loading-state" role="status">Loading answer sheet…</div>;
  if (error && !sheet) return <div className="empty-state"><h3>Answer sheet could not be loaded</h3><p>{error}</p><button type="button" className="btn btn-primary" onClick={load}><RotateCcw size={15} /> Retry</button></div>;
  if (!sheet) return null;

  const status = gradingStatusLabel(sheet.grading_status);
  const regionCount = Object.keys(sheet.question_region_map).length;
  const canGrade = sheet.grading_status === "not_graded" || sheet.grading_status === "failed";
  const actionLabel = sheet.grading_status === "failed" ? "Retry grading" : "Grade paper";
  const uncertainRegionCount = Object.values(sheet.question_region_map).flat().filter((ref) => ref.alignment_uncertain || ref.page_correspondence_uncertain).length;

  return <div>
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Roll {sheet.roll_number}</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Answer sheet inspection</div><div className="title-with-badges"><h1>Roll {sheet.roll_number}</h1><span className="badge badge-slate"><CheckCircle2 size={12} /> Prepared for review</span></div><p>{sheet.page_count} pages · Uploaded {formatDate(sheet.uploaded_at)} · {status.label}</p></div><div className="button-row">{canGrade ? <button type="button" className="btn btn-primary" onClick={grade} disabled={grading}><GraduationCap size={16} /> {grading ? "Grading…" : actionLabel}</button> : <Link to={`/projects/${projectId}/answer-sheets/${sheet.id}/results`} className="btn btn-primary"><GraduationCap size={16} /> Review results</Link>}</div></div>

    {error && <div className="alert alert-error" role="alert"><AlertCircle size={18} /><span><strong>Action could not be completed.</strong> {error}</span><button type="button" className="btn btn-quiet" onClick={load}>Retry</button></div>}
    {uncertainRegionCount > 0 && <div className="alert alert-warning" role="status"><AlertCircle size={18} /><span><strong>Manual review required before grading.</strong> {uncertainRegionCount} region{uncertainRegionCount === 1 ? " is" : "s are"} uncertain because the uploaded page could not be matched confidently to the confirmed template. Inspect the page and template map before retrying.</span><Link className="alert-action" to={`/projects/${projectId}/template-map`}>Open template map</Link></div>}
    {sheet.report_ready && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>Examiner report is ready.</span><a className="alert-action" href={fileUrl(sheet.report_download_url ?? "")} download="examiner-report.pdf">Download report</a></div>}

    {selectedPreviewUrl && <div className="lightbox" role="dialog" aria-modal="true" aria-label="Enlarged answer preview" onClick={() => setSelectedPreviewUrl(null)}><div className="lightbox-content" onClick={(event) => event.stopPropagation()}><button type="button" className="lightbox-close" onClick={() => setSelectedPreviewUrl(null)} aria-label="Close preview">×</button><img src={fileUrl(selectedPreviewUrl)} alt="Enlarged answer preview" /><p>Click outside or press the close button to return.</p></div></div>}

    <div className="segmentation-layout"><aside className="card pages-panel"><div className="panel-heading"><div><h2><FileText size={18} /> Scanned pages</h2><p>{sheet.page_image_urls.length} ordered page images</p></div></div><div className="page-thumb-list">{sheet.page_image_urls.map((url, index) => <button type="button" className="page-thumb" key={url} onClick={() => setSelectedPreviewUrl(url)}><img src={fileUrl(url)} alt={`Page ${index + 1}`} /><span>Page {index + 1}</span><ZoomIn size={14} /></button>)}</div></aside><section><div className="section-heading"><div><h2>Question regions</h2><p>Stored crop previews grouped by question for inspection. Overflow-marked crops should be checked before confirmation.</p></div><span className="badge badge-indigo"><GraduationCap size={12} /> {regionCount} question regions</span></div>{regionCount === 0 ? <div className="empty-state"><h3>No regions mapped</h3><p>No answer regions were associated with questions for this sheet.</p></div> : <div className="region-card-list">{Object.entries(sheet.question_region_map).map(([questionKey, refs]) => { const previews = sheet.region_preview_urls[questionKey] ?? []; const hasOverflow = refs.some((ref) => ref.overflow_detected); return <article className={`region-preview-card ${hasOverflow ? "has-review-signal" : ""}`} key={questionKey}><div className="region-preview-header"><span>Question {questionKey}</span><small>{refs.length} region slice{refs.length === 1 ? "" : "s"}{hasOverflow ? " · possible overflow" : ""}</small></div>{previews.length === 0 ? <div className="no-preview"><FileText size={16} /> No crop preview available.</div> : <div className="crop-grid">{previews.map((url, index) => <button type="button" className="crop-button" key={url} onClick={() => setSelectedPreviewUrl(url)}><img src={fileUrl(url)} alt={`Region ${questionKey}, slice ${index + 1}`} /><span>Slice {index + 1} <ZoomIn size={13} /></span></button>)}</div>}</article>; })}</div>}</section></div>
  </div>;
}
