import { ArrowLeft, CheckCircle2, FileText, Layers, RotateCcw, ZoomIn } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnswerSheetDetail as AnswerSheetDetailType, fileUrl, getAnswerSheet } from "../api/client";
import { errorMessage, formatDate, gradingStatusLabel } from "../ui";

export default function AnswerSheetDetailPage() {
  const { projectId, sheetId } = useParams();
  const [sheet, setSheet] = useState<AnswerSheetDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedPreviewUrl, setSelectedPreviewUrl] = useState<string | null>(null);

  const load = () => {
    if (!projectId || !sheetId) return;
    setLoading(true); setError("");
    getAnswerSheet(projectId, sheetId).then(setSheet).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  };
  useEffect(load, [projectId, sheetId]);

  if (!projectId || !sheetId) return null;
  if (loading) return <div className="loading-state" role="status">Loading answer sheet…</div>;
  if (error || !sheet) return <div className="empty-state"><h3>Answer sheet could not be loaded</h3><p>{error || "The requested sheet is unavailable."}</p><button type="button" className="btn btn-primary" onClick={load}><RotateCcw size={15} /> Retry</button></div>;
  const status = gradingStatusLabel(sheet.grading_status);
  const regionCount = Object.keys(sheet.question_region_map).length;

  return <div>
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Roll {sheet.roll_number}</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Answer sheet inspection</div><div className="title-with-badges"><h1>Roll {sheet.roll_number}</h1><span className="badge badge-slate"><CheckCircle2 size={12} /> Prepared for review</span></div><p>{sheet.page_count} pages · Uploaded {formatDate(sheet.uploaded_at)} · {status.label}</p></div><Link to={`/projects/${projectId}/answer-sheets/${sheet.id}/results`} className="btn btn-primary">Review results</Link></div>

    {selectedPreviewUrl && <div className="lightbox" role="dialog" aria-modal="true" aria-label="Enlarged answer preview" onClick={() => setSelectedPreviewUrl(null)}><div className="lightbox-content" onClick={(event) => event.stopPropagation()}><button type="button" className="lightbox-close" onClick={() => setSelectedPreviewUrl(null)} aria-label="Close preview">×</button><img src={fileUrl(selectedPreviewUrl)} alt="Enlarged answer preview" /><p>Click outside or press the close button to return.</p></div></div>}

    <div className="segmentation-layout"><aside className="card pages-panel"><div className="panel-heading"><div><h2><FileText size={18} /> Scanned pages</h2><p>{sheet.page_image_urls.length} ordered page images</p></div></div><div className="page-thumb-list">{sheet.page_image_urls.map((url, index) => <button type="button" className="page-thumb" key={url} onClick={() => setSelectedPreviewUrl(url)}><img src={fileUrl(url)} alt={`Page ${index + 1}`} /><span>Page {index + 1}</span><ZoomIn size={14} /></button>)}</div></aside><section><div className="section-heading"><div><h2>Question regions</h2><p>Stored crop previews grouped by question for inspection.</p></div><span className="badge badge-indigo"><Layers size={12} /> {regionCount} question regions</span></div>{regionCount === 0 ? <div className="empty-state"><h3>No regions mapped</h3><p>No answer regions were associated with questions for this sheet.</p></div> : <div className="region-card-list">{Object.entries(sheet.question_region_map).map(([questionKey, refs]) => { const previews = sheet.region_preview_urls[questionKey] ?? []; return <article className="region-preview-card" key={questionKey}><div className="region-preview-header"><span>Question {questionKey}</span><small>{refs.length} region slice{refs.length === 1 ? "" : "s"}</small></div>{previews.length === 0 ? <div className="no-preview"><FileText size={16} /> No crop preview available.</div> : <div className="crop-grid">{previews.map((url, index) => <button type="button" className="crop-button" key={url} onClick={() => setSelectedPreviewUrl(url)}><img src={fileUrl(url)} alt={`Region ${questionKey}, slice ${index + 1}`} /><span>Slice {index + 1} <ZoomIn size={13} /></span></button>)}</div>}</article>; })}</div>}</section></div>
  </div>;
}
