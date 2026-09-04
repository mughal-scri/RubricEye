import { AlertCircle, ArrowLeft, Check, CheckCircle2, ChevronLeft, ChevronRight, FileText, FolderPlus, ShieldLock, Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import BrandedLoader from "../components/BrandedLoader";
import FilePicker from "../components/FilePicker";
import RubricCriteriaEditor from "../components/RubricCriteriaEditor";
import { createProject, exportRubricStudioPdf, fileUrl, previewRubricStudio, RubricStudioCriterionDraft, RubricStudioPreviewResponse } from "../api/client";
import { errorMessage } from "../ui";

type DocumentKind = "questionPaper" | "blankBooklet" | "rubric";
type RubricMode = "upload" | "studio";

const steps = ["Question paper", "Answer booklet", "Rubric source", "Confirm"];
const copy: Record<Exclude<DocumentKind, "rubric">, { title: string; description: string }> = {
  questionPaper: { title: "Question paper", description: "The printed paper used to understand question numbers, sections, instructions, and marks." },
  blankBooklet: { title: "Answer booklet / template", description: "The blank booklet whose own printed structure will be read for answer regions and page order." },
};

export default function CreateProject() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [files, setFiles] = useState<Record<DocumentKind, File | null>>({ questionPaper: null, blankBooklet: null, rubric: null });
  const [rubricMode, setRubricMode] = useState<RubricMode>("upload");
  const [studioPreview, setStudioPreview] = useState<RubricStudioPreviewResponse | null>(null);
  const [studioPdfUrl, setStudioPdfUrl] = useState<string | null>(null);
  const [studioGenerating, setStudioGenerating] = useState(false);
  const [studioExporting, setStudioExporting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const chooseFile = (kind: DocumentKind, file: File | null) => setFiles((current) => ({ ...current, [kind]: file }));
  const updateCriterion = (questionNumber: string, field: "marks_possible" | "key_points", value: string | number | null) => setStudioPreview((current) => current ? { ...current, criteria: current.criteria.map((criterion) => criterion.question_number === questionNumber ? { ...criterion, [field]: value } : criterion) } : current);

  const generateStudioPreview = async () => {
    if (!files.questionPaper) { setError("Choose the question paper before generating a rubric."); return; }
    setStudioGenerating(true); setError("");
    try {
      const preview = await previewRubricStudio(files.questionPaper);
      setStudioPreview(preview);
      setStudioPdfUrl(preview.generated_rubric_download_url ?? null);
      if (preview.status === "manual_required") setError(preview.warning ?? "Rubric Studio could not generate a draft. Upload an official rubric instead.");
    } catch (err) { setError(errorMessage(err)); } finally { setStudioGenerating(false); }
  };

  const studioIncomplete = studioPreview?.criteria.filter((criterion) => !criterion.key_points?.trim() || criterion.marks_possible === null).length ?? 0;

  const exportEditedStudioPdf = async () => {
    if (!studioPreview?.criteria.length || studioIncomplete) { setError("Complete every generated criterion before exporting the PDF."); return; }
    setStudioExporting(true); setError("");
    try { const result = await exportRubricStudioPdf(name.trim() || "RubricEye Assessment", studioPreview.criteria); setStudioPdfUrl(result.download_url); } catch (err) { setError(errorMessage(err)); } finally { setStudioExporting(false); }
  };

  const goNext = async () => {
    setError("");
    if (step === 0 && !files.questionPaper) return setError("Choose the question paper before continuing.");
    if (step === 1 && !files.blankBooklet) return setError("Choose the blank answer booklet or template before continuing.");
    if (step === 2) {
      if (rubricMode === "upload" && !files.rubric) return setError("Choose the official rubric PDF before continuing.");
      if (rubricMode === "studio") {
        if (!studioPreview) { await generateStudioPreview(); return; }
        if (studioPreview.status === "manual_required") return setError("Upload an official rubric to continue.");
        if (studioPreview.status !== "draft_ready" || !studioPreview.criteria.length) return setError("Rubric Studio returned an incomplete draft. Use the official rubric upload path instead.");
        if (studioIncomplete) return setError("Complete every generated criterion before continuing.");
      }
    }
    setStep((current) => Math.min(3, current + 1));
  };

  const goBack = () => { setError(""); setStep((current) => Math.max(0, current - 1)); };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    if (!name.trim()) return setError("Enter a project name before creating it.");
    if (!files.questionPaper || !files.blankBooklet) return setError("Complete the question paper and answer booklet steps before creating the project.");
    if (rubricMode === "upload" && !files.rubric) return setError("Upload the official rubric before creating the project.");
    if (rubricMode === "studio" && (!studioPreview || studioPreview.status !== "draft_ready" || studioIncomplete)) return setError("Complete the Rubric Studio review or choose another rubric source.");
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("name", name.trim());
      formData.append("rubric_mode", rubricMode);
      formData.append("question_paper", files.questionPaper);
      formData.append("blank_booklet", files.blankBooklet);
      if (rubricMode === "upload" && files.rubric) formData.append("rubric", files.rubric);
      if (rubricMode === "studio" && studioPreview) {
        formData.append("rubric_draft_json", JSON.stringify({ criteria: studioPreview.criteria }));
        formData.append("rubric_draft_reviewed", "true");
      }
      const project = await createProject(formData);
      navigate(`/projects/${project.id}/template-map`);
    } catch (err) { setError(errorMessage(err)); } finally { setLoading(false); }
  };

  if (loading) return <div className="page-narrow"><div className="processing-card" role="status"><BrandedLoader message="Preparing your assessment…" /><p>RubricEye is saving the reviewed materials and preparing the adaptive booklet map. Keep this window open until the review step is ready.</p></div></div>;

  return <div className="page-narrow staged-creation">
    <div className="breadcrumb"><Link to="/"><ArrowLeft size={14} /> Back to projects</Link></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">New assessment</div><h1>Create evaluation project</h1><p>Prepare the assessment in four steps. Studio drafts stay provisional until you review the full source.</p></div></div>
    <nav className="wizard-steps" aria-label="Project creation steps">{steps.map((label, index) => <div key={label} className={`wizard-step ${index === step ? "is-current" : ""} ${index < step ? "is-done" : ""}`}><span>{index < step ? <Check size={14} /> : index + 1}</span><strong>{label}</strong></div>)}</nav>
    {error && <div className="alert alert-error" role="alert"><AlertCircle size={18} /><span>{error}</span></div>}

    <form onSubmit={onSubmit} className="card form-card staged-card">
      {step < 3 && <section className="wizard-panel"><div className="section-heading"><div><div className="eyebrow">Step {step + 1} of 4</div><h2>{copy[step === 0 ? "questionPaper" : "blankBooklet"].title}</h2><p>{copy[step === 0 ? "questionPaper" : "blankBooklet"].description}</p></div></div>
        <FilePicker id={`file-${step === 0 ? "question-paper" : "blank-booklet"}`} file={files[step === 0 ? "questionPaper" : "blankBooklet"]} emptyLabel="Choose a PDF" emptyHint="PDF files only" readyHint="Ready for the next step" onChange={(file) => chooseFile(step === 0 ? "questionPaper" : "blankBooklet", file)} />
        {step === 1 && <div className="info-panel"><FileText size={17} /><div><strong>What RubricEye reads</strong><p>The booklet’s printed labels and answer structure. Technical coordinates stay hidden during ordinary setup; uncertain structure will be surfaced for review.</p></div></div>}
      </section>}

      {step === 2 && <section className="wizard-panel"><div className="section-heading"><div><div className="eyebrow">Step 3 of 4</div><h2>Choose a rubric source</h2><p>Use the source you already have. Rubric Studio is optional and always produces an examiner-editable draft.</p></div></div>
        <div className="rubric-choice" role="tablist" aria-label="Rubric source options">
          <button type="button" role="tab" aria-selected={rubricMode === "upload"} className={`choice-card ${rubricMode === "upload" ? "is-selected" : ""}`} onClick={() => { setRubricMode("upload"); setError(""); }}><ShieldLock size={18} /><span><strong>Upload PDF</strong><small>Use an official marking scheme.</small></span></button>
          <button type="button" role="tab" aria-selected={rubricMode === "studio"} className={`choice-card ${rubricMode === "studio" ? "is-selected" : ""}`} onClick={() => { setRubricMode("studio"); setError(""); }}><Sparkles size={18} /><span><strong>Rubric Studio</strong><small>Draft criteria from the question paper, then edit them in order.</small></span></button>
        </div>
        {rubricMode === "upload" && <FilePicker id="file-rubric" file={files.rubric} emptyLabel="Choose an official rubric PDF" emptyHint="PDF files only" readyHint="Official source selected" onChange={(file) => chooseFile("rubric", file)} />}
        {rubricMode === "studio" && <div className="studio-review-panel"><div className="info-panel"><Sparkles size={17} /><div><strong>One explicit draft call</strong><p>Rubric Studio reads the selected question paper, keeps its question labels, and returns provisional criteria for you to edit. It will not create an autonomous final rubric.</p></div></div>{studioPreview?.warning && <div className="alert alert-warning" role="status"><AlertCircle size={17} /><span>{studioPreview.warning}</span></div>}{studioPreview?.criteria.length ? <><div className="structure-summary"><div><span className="eyebrow">Draft criteria</span><strong>{studioPreview.criteria.length} criteria in paper order</strong><p>{studioIncomplete ? `${studioIncomplete} still need marks or criteria text.` : "All criteria have editable marks and text."}</p></div><div className="structure-metrics"><span><b>{studioPreview.criteria.length - studioIncomplete}</b> complete</span><span><b>{studioIncomplete}</b> open</span>{studioPdfUrl && <a className="btn btn-secondary btn-sm" href={fileUrl(studioPdfUrl)} download="rubric.pdf"><FileText size={14} /> Download PDF</a>}<button type="button" className="btn btn-secondary btn-sm" onClick={() => void exportEditedStudioPdf()} disabled={studioExporting || studioIncomplete > 0}><FileText size={14} /> {studioExporting ? "Preparing PDF…" : "Export edited PDF"}</button></div></div><RubricCriteriaEditor criteria={studioPreview.criteria} onChange={updateCriterion} /></> : <div className="empty-state"><Sparkles size={26} /><h3>Ready to draft the rubric</h3><p>Generate one provisional draft from the question paper, or upload a PDF above.</p></div>}<button type="button" className="btn btn-secondary" onClick={generateStudioPreview} disabled={studioGenerating}>{studioGenerating ? "Generating draft…" : studioPreview ? "Regenerate draft" : "Generate rubric draft"}</button></div>}
      </section>}

      {step === 3 && <section className="wizard-panel"><div className="eyebrow">Step 4 of 4</div><h2>Confirm project creation</h2><p>Review the source files once. The project will be created only after this final confirmation.</p><div className="review-file-list"><div className="review-file"><CheckCircle2 size={18} /><div><strong>Question paper</strong><span>{files.questionPaper?.name ?? "Missing PDF"}</span></div></div><div className="review-file"><CheckCircle2 size={18} /><div><strong>Answer booklet / template</strong><span>{files.blankBooklet?.name ?? "Missing PDF"}</span></div></div><div className="review-file"><CheckCircle2 size={18} /><div><strong>{rubricMode === "studio" ? "Rubric Studio draft" : "Official rubric PDF"}</strong><span>{rubricMode === "studio" ? `${studioPreview?.criteria.length ?? 0} edited criteria` : files.rubric?.name ?? "Missing PDF"}</span></div></div></div><div className="form-group"><label className="form-label" htmlFor="project-name">Project name</label><input id="project-name" className="form-input" value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Physics Midterm Examination 2026" required /></div><div className="info-panel"><CheckCircle2 size={17} /><div><strong>What happens next</strong><p>After creation, you’ll review what RubricEye understood from the uploaded booklet, then confirm the Question Bank before grading.</p></div></div></section>}
      <div className="form-actions"><button type="button" className="btn btn-secondary" onClick={goBack} disabled={step === 0}><ChevronLeft size={16} /> Back</button>{step < 3 ? <button type="button" className="btn btn-primary" onClick={() => void goNext()} disabled={studioGenerating}>{studioGenerating ? "Generating…" : <>Continue <ChevronRight size={16} /></>}</button> : <button type="submit" className="btn btn-primary"><FolderPlus size={17} /> Create project</button>}</div>
    </form>
  </div>;
}
