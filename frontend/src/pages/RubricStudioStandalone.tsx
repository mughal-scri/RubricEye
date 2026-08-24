import { AlertCircle, ArrowLeft, Download, FileText, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import FilePicker from "../components/FilePicker";
import RubricCriteriaEditor from "../components/RubricCriteriaEditor";
import { exportRubricStudioPdf, fileUrl, previewRubricStudio, RubricStudioCriterionDraft } from "../api/client";
import { errorMessage } from "../ui";

export default function RubricStudioStandalone() {
  const [questionPaper, setQuestionPaper] = useState<File | null>(null);
  const [criteria, setCriteria] = useState<RubricStudioCriterionDraft[]>([]);
  const [projectName, setProjectName] = useState("RubricEye Assessment");
  const [warning, setWarning] = useState("");
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  const generate = async () => {
    if (!questionPaper) { setError("Choose a question paper before generating criteria."); return; }
    setWorking(true); setError(""); setWarning(""); setDownloadUrl(null);
    try {
      const result = await previewRubricStudio(questionPaper);
      setCriteria(result.criteria);
      setWarning(result.warning ?? "");
      if (result.status === "manual_required") setError(result.warning ?? "Rubric Studio needs a configured provider or a clearer question paper.");
      if (result.status === "partial") setWarning(result.warning ?? "The draft is partial. Complete the missing criteria before exporting.");
    } catch (err) { setError(errorMessage(err)); } finally { setWorking(false); }
  };

  const updateCriterion = (questionNumber: string, field: "marks_possible" | "key_points", value: string | number | null) => setCriteria((current) => current.map((criterion) => criterion.question_number === questionNumber ? { ...criterion, [field]: value } : criterion));
  const incompleteCount = criteria.filter((criterion) => criterion.marks_possible === null || !criterion.key_points?.trim()).length;
  const exportPdf = async () => {
    if (!criteria.length || incompleteCount) { setError("Complete every generated criterion before exporting the PDF."); return; }
    setWorking(true); setError("");
    try { const result = await exportRubricStudioPdf(projectName.trim() || "RubricEye Assessment", criteria); setDownloadUrl(result.download_url); } catch (err) { setError(errorMessage(err)); } finally { setWorking(false); }
  };

  return <div className="page-narrow standalone-studio-page">
    <div className="breadcrumb"><Link to="/"><ArrowLeft size={14} /> Back to projects</Link></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Independent worker</div><h1>Rubric Studio</h1><p>Upload a question paper, review the generated criteria in order, and export a structured PDF for project creation.</p></div></div>
    {error && <div className="alert alert-error" role="alert"><AlertCircle size={17} /><span>{error}</span></div>}
    {warning && <div className="alert alert-warning" role="status"><AlertCircle size={17} /><span>{warning}</span></div>}
    <section className="card form-card standalone-studio-intake"><div className="section-heading compact"><div><h2>Source paper</h2><p>Only the question paper is sent for the explicit Studio draft call. Identity-bearing answer pages are not part of this workflow.</p></div></div><FilePicker id="standalone-question-paper" file={questionPaper} emptyLabel="Choose a question-paper PDF" emptyHint="PDF files only" readyHint="Ready to read" onChange={setQuestionPaper} /><div className="form-group"><label className="form-label" htmlFor="standalone-project-name">Rubric title</label><input id="standalone-project-name" className="form-input" value={projectName} onChange={(event) => setProjectName(event.target.value)} /></div><div className="form-actions"><button type="button" className="btn btn-primary" onClick={generate} disabled={working || !questionPaper}><Sparkles size={16} />{working ? "Reading paper…" : criteria.length ? "Regenerate criteria" : "Generate criteria"}</button></div></section>
    {criteria.length > 0 && <section className="card form-card standalone-studio-results"><div className="section-heading"><div><div className="eyebrow">Review before export</div><h2>{criteria.length} criteria in question-paper order</h2><p>{incompleteCount ? `${incompleteCount} criteria still need marks or text.` : "Edit any wording or mark value before exporting."}</p></div><div className="button-row">{downloadUrl && <a className="btn btn-success" href={fileUrl(downloadUrl)} download="rubric.pdf"><Download size={15} /> Download PDF</a>}<button type="button" className="btn btn-secondary" onClick={exportPdf} disabled={working || incompleteCount > 0}><FileText size={15} /> Export edited PDF</button></div></div><RubricCriteriaEditor criteria={criteria} saving={working} onChange={updateCriterion} /></section>}
  </div>;
}
