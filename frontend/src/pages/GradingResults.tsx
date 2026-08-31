import { AlertTriangle, ArrowLeft, CheckCircle2, Circle, FileDown, HelpCircle, ImageOff, RotateCcw, ZoomIn } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnswerSheetResultsResponse, createExaminerReport, fileUrl, GradingResult, confirmGradingResult, listGradingResults } from "../api/client";
import { choiceStatusLabel, errorMessage, gradingStatusLabel, reviewStateBadge } from "../ui";

const isReviewable = (result: GradingResult) => (result.choice_status === "graded" || result.choice_status === "flagged_ambiguous") && result.grading_status !== "failed";
const isClosed = (result: GradingResult) => result.choice_status === "skipped_blank" || result.choice_status === "skipped_beyond_n";

export default function GradingResults() {
  const { projectId, sheetId } = useParams();
  const [data, setData] = useState<AnswerSheetResultsResponse | null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);
  const [selectedPreviewUrl, setSelectedPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmScore, setConfirmScore] = useState("");
  const [confirmNote, setConfirmNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [reporting, setReporting] = useState(false);

  const load = () => {
    if (!projectId || !sheetId) return;
    setLoading(true); setError("");
    listGradingResults(projectId, sheetId).then((body) => { setData(body); setSelectedQuestion((current) => current ?? body.results[0]?.question_number ?? null); }).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  };
  useEffect(load, [projectId, sheetId]);
  useEffect(() => { const onKey = (event: KeyboardEvent) => event.key === "Escape" && setSelectedPreviewUrl(null); window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey); }, []);

  const selected: GradingResult | undefined = useMemo(() => data?.results.find((result) => result.question_number === selectedQuestion), [data, selectedQuestion]);

  useEffect(() => {
    if (!data) return;
    const onKey = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      const results = data.results;
      const idx = results.findIndex((r) => r.question_number === selectedQuestion);
      if (event.key === "ArrowDown" && idx < results.length - 1) { event.preventDefault(); setSelectedQuestion(results[idx + 1].question_number); }
      else if (event.key === "ArrowUp" && idx > 0) { event.preventDefault(); setSelectedQuestion(results[idx - 1].question_number); }
      else if (event.key === "Enter" && selected && isReviewable(selected)) { event.preventDefault(); document.getElementById("confirmed-score")?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [data, selectedQuestion, selected]);

  const reviewable = data?.results.filter(isReviewable) ?? [];
  const reviewedCount = reviewable.filter((result) => result.reviewed).length;
  const totalCount = reviewable.length;
  const remainingCount = Math.max(0, totalCount - reviewedCount);
  const hasFailures = data?.results.some((result) => result.grading_status === "failed") ?? false;
  const canReport = Boolean(data && data.results.length > 0 && remainingCount === 0 && !hasFailures && !data.report_ready);

  useEffect(() => { if (selected) { setConfirmScore(String(selected.human_confirmed_score ?? selected.ai_score ?? "")); setConfirmNote(selected.human_reviewer_note ?? ""); } }, [selected]);

  const submitConfirm = async () => {
    if (!projectId || !sheetId || !selected || !isReviewable(selected) || confirmScore.trim() === "") return;
    const maxMarks = selected.ai_total_possible; const score = Number(confirmScore);
    if (maxMarks === null || maxMarks === undefined) { setError("Marks limit unavailable. Review the question definition before confirming a score."); return; }
    if (!Number.isInteger(score) || score < 0 || score > maxMarks) { setError(`Enter a score from 0 to ${maxMarks} marks.`); return; }
    setSaving(true); setError("");
    try { await confirmGradingResult(projectId, sheetId, selected.question_number, { human_confirmed_score: score, human_reviewer_note: confirmNote.trim() || null }); load(); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  const generateReport = async () => {
    if (!projectId || !sheetId) return;
    setReporting(true); setError("");
    try { await createExaminerReport(projectId, sheetId); load(); } catch (err) { setError(errorMessage(err)); } finally { setReporting(false); }
  };

  if (!projectId || !sheetId) return null;
  if (loading) return <div className="loading-state" role="status">Loading grading review…</div>;
  if (error && !data) return <div className="empty-state"><h3>Results could not be loaded</h3><p>{error}</p><button type="button" className="btn btn-primary" onClick={load}><RotateCcw size={15} /> Retry</button></div>;
  if (!data) return null;
  const sheetStatus = gradingStatusLabel(data.grading_status);

  return <div>
    <div className="breadcrumb"><Link to={`/projects/${projectId}/answer-sheets/${sheetId}`}><ArrowLeft size={14} /> Back to answer sheet</Link><span>/</span><span>Results</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Examiner review</div><div className="title-with-badges"><h1>Grading results</h1><span className={`badge badge-${sheetStatus.tone}`}>{sheetStatus.label}</span></div><p>{reviewedCount} of {totalCount} gradable questions confirmed · {remainingCount} still need review.</p></div><div className="button-row">{data.report_ready && data.report_download_url ? <a className="btn btn-success" href={fileUrl(data.report_download_url)} download="examiner-report.pdf"><FileDown size={16} /> Download report</a> : <button type="button" className="btn btn-primary" onClick={generateReport} disabled={!canReport || reporting}><FileDown size={16} /> {reporting ? "Generating…" : "Generate report"}</button>}</div></div>
    {error && <div className="alert alert-error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button type="button" className="btn btn-quiet" onClick={load}>Retry</button></div>}
    {selectedPreviewUrl && <div className="lightbox" role="dialog" aria-modal="true" aria-label="Enlarged answer evidence" onClick={() => setSelectedPreviewUrl(null)}><div className="lightbox-content" onClick={(event) => event.stopPropagation()}><button type="button" className="lightbox-close" onClick={() => setSelectedPreviewUrl(null)} aria-label="Close evidence preview">×</button><img src={fileUrl(selectedPreviewUrl)} alt="Enlarged answer evidence" /><p>Click outside or press Escape to close.</p></div></div>}

    <div className="results-summary-grid"><div className="card summary-card"><span>Current calculated total</span><strong>{data.summary.grand_total_awarded} / {data.summary.grand_total_possible}</strong><small>Only included gradable choices count toward the denominator.</small></div><div className="card summary-card"><span>Examiner confirmations</span><strong>{reviewedCount} / {totalCount}</strong><small>{remainingCount ? `${remainingCount} question${remainingCount === 1 ? "" : "s"} remain unresolved.` : "All gradable results have a human decision."}</small></div><div className="card summary-card"><span>Report status</span><strong>{data.report_ready ? "Ready to download" : canReport ? "Ready to generate" : "Review required"}</strong><small>Blank and choice-excluded parts are shown as closed decisions.</small></div></div>

    <div className="section-heading"><div><h2>Section totals</h2><p>Totals are calculated from included choices and confirmed scores where available.</p></div></div>
    <div className="section-rollup-grid">{data.summary.sections.map((section) => <div className="card section-rollup" key={section.section_name}><span>{section.section_name}</span><strong>{section.section_total_awarded} / {section.section_total_possible}</strong></div>)}</div>

    <div className="review-layout"><aside className="review-queue" aria-label="Questions to review"><div className="queue-header"><strong>Review queue</strong><span>{remainingCount} open</span></div>{data.results.map((result) => { const isActive = result.question_number === selectedQuestion; const closed = isClosed(result); const state = reviewStateBadge(result.review_state); const issue = result.truncation_flag ? "Possible crop overflow" : result.choice_status !== "graded" ? choiceStatusLabel(result.choice_status) : result.flags[0]; return <button key={result.question_number} type="button" className={`queue-item ${isActive ? "is-active" : ""} ${closed ? "is-closed" : ""}`} onClick={() => setSelectedQuestion(result.question_number)} aria-current={isActive ? "true" : undefined}><span className="queue-item-top"><strong>Q{result.question_number}</strong><span className={`badge badge-${state.tone}`} style={{ fontSize: "0.7rem" }}>{closed ? "Closed" : state.label}</span></span><span className="queue-item-bottom">{result.ai_score !== null ? `${result.reviewed ? result.human_confirmed_score : result.ai_score} / ${result.ai_total_possible ?? "?"}` : issue ?? "No draft score"}</span></button>; })}</aside>

      {selected ? <section className="evidence-workspace" aria-labelledby="selected-question-title"><div className="evidence-header"><div><span className="eyebrow">Question {selected.question_number}</span><h2 id="selected-question-title">Evidence review</h2></div><div className="button-row">{(() => { const state = reviewStateBadge(selected.review_state); return <span className={`badge badge-${state.tone}`}>{state.label}</span>; })()}</div></div>
        {isClosed(selected) ? <div className="alert alert-info"><HelpCircle size={17} /><span><strong>{choiceStatusLabel(selected.choice_status)}.</strong> No model score was requested for this part.</span></div> : selected.grading_status === "failed" && <div className="alert alert-error"><AlertTriangle size={17} /><span><strong>This question could not be graded.</strong> {selected.error_message ?? "No score was saved."}</span></div>}
        {selected.choice_status === "flagged_ambiguous" && <div className="alert alert-warning"><AlertTriangle size={17} /><span><strong>Ink state needs examiner attention.</strong> Inspect the original answer before deciding whether it was attempted.</span></div>}
        {selected.truncation_flag && <div className="alert alert-warning"><AlertTriangle size={17} /><span><strong>Possible crop overflow.</strong> Inspect the original answer before confirming a score.</span></div>}
        <div className="evidence-grid"><div className="evidence-pane"><div className="panel-heading"><div><h3>Evidence used for this draft</h3><p>Click an image to inspect it without leaving the review.</p></div></div>{selected.region_preview_urls.length === 0 ? <div className="no-preview"><ImageOff size={18} /><span>No crop preview is available. Inspect the answer sheet directly before confirming.</span></div> : <div className="crop-grid">{selected.region_preview_urls.map((url, index) => <button type="button" className="crop-button" key={url} onClick={() => setSelectedPreviewUrl(url)}><img src={fileUrl(url)} alt={`Answer evidence for question ${selected.question_number}, region ${index + 1}`} /><span>Region {index + 1} · <ZoomIn size={13} /> Enlarge</span></button>)}</div>}</div>
          <div className="review-context-pane">
            <div className="context-section">
              <div className="panel-heading"><div><h3>Question context</h3><p>Rubric criteria and expected key points.</p></div></div>
              {selected.question_text ? <div className="question-text-block"><p>{selected.question_text}</p></div> : <div className="context-placeholder">No question text available for this part.</div>}
              {selected.key_points && <div className="key-points-block"><strong>Key points</strong><p>{selected.key_points}</p></div>}
            </div>
            {selected.ai_rationale && <div className="rationale-panel"><strong>AI rubric rationale</strong><p>{selected.ai_rationale}</p></div>}
            <div className="context-section">
              <div className="panel-heading"><div><h3>Signals</h3><p>Model diagnostics for this draft.</p></div></div>
              <div className="signal-list"><div><span>AI recommendation</span><strong className="text-ai">{isClosed(selected) ? "No model score" : selected.choice_status === "flagged_ambiguous" ? "Manual decision" : "Draft only"}</strong></div><div><span>Model confidence</span><strong>{selected.confidence}</strong></div><div><span>Answer state</span><strong>{selected.ink_status}</strong></div><div><span>Choice rule</span><strong>{choiceStatusLabel(selected.choice_status)}</strong></div><div><span>Ink density</span><strong>{selected.ink_density_ratio !== null ? selected.ink_density_ratio.toFixed(3) : "\u2014"}</strong></div>{selected.truncation_flag && <div><span>Crop overflow</span><strong className="text-danger">Possible</strong></div>}</div>
            </div>
            {selected.transcription_summary && <div className="context-section transcription-block"><strong>Transcription summary</strong><p>{selected.transcription_summary}</p></div>}
            {selected.part_scores.length > 0 && <div className="context-section part-score-block"><div className="panel-heading"><div><h3>Part-score rationale</h3><p>Review how the draft was broken down.</p></div></div><div className="table-container"><table className="table"><thead><tr><th>Part</th><th>Awarded</th><th>Possible</th><th>Evidence rationale</th></tr></thead><tbody>{selected.part_scores.map((part, index) => <tr key={`${part.part}-${index}`}><td><strong>{part.part || "\u2014"}</strong></td><td>{part.marks_awarded}</td><td>{part.marks_possible}</td><td>{part.rationale}</td></tr>)}</tbody></table></div></div>}
            {selected.flags.length > 0 && <div className="context-section flag-list"><strong>Flags to consider</strong>{selected.flags.map((flag, index) => <div className="flag-row" key={`${flag}-${index}`}><AlertTriangle size={15} />{flag}</div>)}</div>}
            {isReviewable(selected) && <div className="context-section decision-panel"><div className="panel-heading"><div><h3>Examiner decision</h3><p>{selected.choice_status === "flagged_ambiguous" ? "Decide whether this answer was attempted and assign a bounded score." : "Confirm the draft or adjust it within the allowed marks range."}</p></div></div><div className="decision-form"><div className="score-field"><label className="form-label" htmlFor="confirmed-score">Confirmed score</label><div className="score-input-wrap"><input id="confirmed-score" type="number" min={0} max={selected.ai_total_possible ?? undefined} step={1} className="form-input" value={confirmScore} onChange={(event) => setConfirmScore(event.target.value)} aria-describedby="score-range" /><span>/ {selected.ai_total_possible ?? "?"}</span></div><small id="score-range" className="field-help">{selected.ai_total_possible === null ? "Marks limit unavailable" : `Allowed range: 0\u2013${selected.ai_total_possible} marks`}</small></div><div className="form-group note-field"><label className="form-label" htmlFor="reviewer-note">Examiner note</label><textarea id="reviewer-note" className="form-input" rows={2} value={confirmNote} onChange={(event) => setConfirmNote(event.target.value)} placeholder="Recommended when changing the AI draft." /></div><button type="button" className="btn btn-success" onClick={submitConfirm} disabled={saving || confirmScore === "" || selected.ai_total_possible === null}><CheckCircle2 size={16} />{saving ? "Saving\u2026" : selected.reviewed ? "Update confirmed score" : "Confirm score"}</button></div></div>}
          </div></div>
      </section> : <div className="empty-state"><h3>No result selected</h3><p>Choose a question from the review queue.</p></div>}
    </div>
  </div>;
}
