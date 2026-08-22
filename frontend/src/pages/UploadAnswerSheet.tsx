import { AlertCircle, ArrowLeft, Check, FileText, ShieldAlert, Upload } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { uploadAnswerSheet } from "../api/client";
import { errorMessage } from "../ui";

export default function UploadAnswerSheet() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [rollNumber, setRollNumber] = useState("");
  const [pdf, setPdf] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!projectId) return;
    if (!rollNumber.trim()) return setError("Enter the answer sheet roll number before continuing.");
    if (!pdf) return setError("Choose the scanned answer-sheet PDF before continuing.");
    if (pdf.type && pdf.type !== "application/pdf" && !pdf.name.toLowerCase().endsWith(".pdf")) return setError("This file does not appear to be a readable PDF.");
    setLoading(true); setError("");
    try { const sheet = await uploadAnswerSheet(projectId, rollNumber.trim(), pdf); navigate(`/projects/${projectId}/answer-sheets/${sheet.id}`); } catch (err) { setError(errorMessage(err)); } finally { setLoading(false); }
  };

  if (!projectId) return null;
  if (loading) return <div className="page-narrow"><div className="processing-card" role="status"><div className="spinner" /><h2>Uploading and preparing booklet…</h2><p>The PDF is being converted into ordered pages and prepared against the confirmed template.</p></div></div>;

  return <div className="page-narrow">
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Upload answer sheet</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Answer sheet intake</div><h1>Upload answer sheet</h1><p>Identify the booklet by roll number only. The original page order will be preserved.</p></div></div>
    <div className="alert alert-warning"><ShieldAlert size={19} /><div><strong>Upload answer content only.</strong><p>If a page appears to contain identity-bearing material, processing may be stopped for review. Do not upload a cover page with candidate names or signatures.</p></div></div>
    {error && <div className="alert alert-error" role="alert"><AlertCircle size={18} /><span><strong>Answer sheet could not be prepared.</strong> {error}</span></div>}
    <form onSubmit={onSubmit} className="card form-card">
      <div className="form-group"><label className="form-label" htmlFor="roll-number">Roll number</label><input id="roll-number" className="form-input" placeholder="e.g. 109283" value={rollNumber} onChange={(event) => setRollNumber(event.target.value)} required /><small className="field-help">Use the board’s anonymized roll number. Do not enter a candidate name.</small></div>
      <div className="form-group"><label className="form-label" htmlFor="answer-pdf">Scanned answer-sheet PDF</label><div className={`file-dropzone ${pdf ? "has-file" : ""}`}><label className="file-choice" htmlFor="answer-pdf"><span className={`file-icon ${pdf ? "is-ready" : ""}`}>{pdf ? <Check size={20} /> : <FileText size={20} />}</span><span className="file-copy"><strong>{pdf ? pdf.name : "Choose the scanned answer booklet"}</strong><small>{pdf ? `${(pdf.size / 1024).toFixed(1)} KB · PDF selected` : "PDF only · page order will be preserved"}</small></span><span className="btn btn-secondary btn-sm">{pdf ? "Replace file" : "Choose PDF"}</span><input id="answer-pdf" type="file" accept="application/pdf,.pdf" onChange={(event) => setPdf(event.target.files?.[0] ?? null)} /></label></div></div>
      <div className="info-panel"><strong>Preparation steps</strong><p>Uploaded → pages rendered → page count checked → regions prepared. Grading starts separately after preparation.</p></div>
      <div className="form-actions"><Link to={`/projects/${projectId}`} className="btn btn-secondary">Cancel</Link><button type="submit" className="btn btn-primary"><Upload size={17} /> Upload and prepare booklet</button></div>
    </form>
  </div>;
}
