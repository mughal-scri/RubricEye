import { AlertTriangle, ArrowLeft, CheckCircle2, Circle, HelpCircle, ImageOff, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnswerSheetResultsResponse, confirmGradingResult, fileUrl, GradingResult, listGradingResults } from "../api/client";
import { choiceStatusLabel, errorMessage, gradingStatusLabel } from "../ui";

export default function GradingResults() {
  const { projectId, sheetId } = useParams();
  const [data, setData] = useState<AnswerSheetResultsResponse | null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmScore, setConfirmScore] = useState("");
  const [confirmNote, setConfirmNote] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => {
    if (!projectId || !sheetId) return;
    setLoading(true);
    setError("");
    listGradingResults(projectId, sheetId)
      .then((body) => {
        setData(body);
        setSelectedQuestion((current) => current ?? body.results[0]?.question_number ?? null);
      })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  };

  useEffect(load, [projectId, sheetId]);

  const selected: GradingResult | undefined = useMemo(() => data?.results.find((result) => result.question_number === selectedQuestion), [data, selectedQuestion]);
  const reviewedCount = data?.results.filter((result) => result.reviewed).length ?? 0;
  const totalCount = data?.results.length ?? 0;
  const remainingCount = Math.max(0, totalCount - reviewedCount);

  useEffect(() => {
    if (selected) {
      setConfirmScore(String(selected.human_confirmed_score ?? selected.ai_score ?? ""));
      setConfirmNote(selected.human_reviewer_note ?? "");
    }
  }, [selected]);

  const submitConfirm = async () => {
    if (!projectId || !sheetId || !selected || confirmScore.trim() === "") return;
    const maxMarks = selected.ai_total_possible;
    const score = Number(confirmScore);
    if (maxMarks === null || maxMarks === undefined) {
      setError("Marks limit unavailable. Review the question definition before confirming a score.");
      return;
    }
    if (!Number.isInteger(score) || score < 0 || score > maxMarks) {
      setError(`Enter a score from 0 to ${maxMarks} marks.`);
      return;
    }

    setSaving(true);
    setError("");
    try {
      await confirmGradingResult(projectId, sheetId, selected.question_number, { human_confirmed_score: score, human_reviewer_note: confirmNote.trim() || null });
      load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (!projectId || !sheetId) return null;
  if (loading) return <div className="loading-state" role="status">Loading grading review…</div>;
  if (error && !data) return <div className="empty-state"><h3>Results could not be loaded</h3><p>{error}</p><button type="button" className="btn btn-primary" onClick={load}><RotateCcw size={15} /> Retry</button></div>;
  if (!data) return null;

  const sheetStatus = gradingStatusLabel(data.grading_status);

  return (
    <div>
      <div className="breadcrumb"><Link to={`/projects/${projectId}/answer-sheets/${sheetId}`}><ArrowLeft size={14} /> Back to answer sheet</Link><span>/</span><span>Results</span></div>
      <div className="page-header">
        <div className="page-title-group"><div className="eyebrow">Examiner review</div><div className="title-with-badges"><h1>Grading results</h1><span className={`badge badge-${sheetStatus.tone}`}>{sheetStatus.label}</span></div><p>{reviewedCount} of {totalCount} questions confirmed · {remainingCount} still need review.</p></div>
      </div>

      {error && <div className="alert alert-error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button type="button" className="btn btn-quiet" onClick={load}>Retry</button></div>}

      <div className="results-summary-grid">
        <div className="card summary-card"><span>Current calculated total</span><strong>{data.summary.grand_total_awarded} / {data.summary.grand_total_possible}</strong><small>Review individual decisions before treating this as final.</small></div>
        <div className="card summary-card"><span>Examiner confirmations</span><strong>{reviewedCount} / {totalCount}</strong><small>{remainingCount ? `${remainingCount} question${remainingCount === 1 ? "" : "s"} remain unresolved.` : "All loaded results have a human decision."}</small></div>
        <div className="card summary-card"><span>Review status</span><strong>{remainingCount ? "Review required" : "Ready to inspect"}</strong><small>AI output is a draft until confirmed.</small></div>
      </div>

      <div className="section-heading"><div><h2>Section totals</h2><p>These totals are provided for orientation and may include draft values.</p></div></div>
      <div className="section-rollup-grid">{data.summary.sections.map((section) => <div className="card section-rollup" key={section.section_name}><span>{section.section_name}</span><strong>{section.section_total_awarded} / {section.section_total_possible}</strong></div>)}</div>

      <div className="review-layout">
        <aside className="review-queue" aria-label="Questions to review"><div className="queue-header"><strong>Review queue</strong><span>{remainingCount} open</span></div>{data.results.map((result) => { const isActive = result.question_number === selectedQuestion; const issue = result.truncation_flag ? "Possible crop truncation" : result.choice_status !== "graded" ? choiceStatusLabel(result.choice_status) : result.flags[0]; return <button key={result.question_number} type="button" className={`queue-item ${isActive ? "is-active" : ""}`} onClick={() => setSelectedQuestion(result.question_number)} aria-current={isActive ? "true" : undefined}><span className="queue-item-top"><strong>Q{result.question_number}</strong>{result.reviewed ? <span className="badge badge-success"><CheckCircle2 size={11} /> Confirmed</span> : <span className="badge badge-warning"><Circle size={11} /> Needs review</span>}</span><span className="queue-item-bottom">{result.ai_score !== null ? `${result.ai_score} / ${result.ai_total_possible ?? "?"}` : issue ?? "No draft score"}</span></button>; })}</aside>

        {selected ? <section className="evidence-workspace" aria-labelledby="selected-question-title">
          <div className="evidence-header"><div><span className="eyebrow">Question {selected.question_number}</span><h2 id="selected-question-title">Evidence review</h2></div><div className="button-row"><span className={`badge ${selected.reviewed ? "badge-success" : "badge-warning"}`}>{selected.reviewed ? "Examiner confirmed" : "Draft · review required"}</span></div></div>

          {selected.grading_status === "failed" && <div className="alert alert-error"><AlertTriangle size={17} /><span><strong>This question could not be graded.</strong> {selected.error_message ?? "No score was saved."}</span></div>}
          {selected.choice_status !== "graded" && <div className="alert alert-info"><HelpCircle size={17} /><span>{choiceStatusLabel(selected.choice_status)}</span></div>}
          {selected.truncation_flag && <div className="alert alert-warning"><AlertTriangle size={17} /><span><strong>Possible crop truncation.</strong> Inspect the original answer before confirming a score.</span></div>}

          <div className="evidence-grid">
            <div className="evidence-pane"><div className="panel-heading"><div><h3>Evidence used for this draft</h3><p>These are the answer-region images included in the grading request.</p></div></div>{selected.region_preview_urls.length === 0 ? <div className="no-preview"><ImageOff size={18} /><span>No crop preview is available. Inspect the answer sheet directly before confirming.</span></div> : <div className="crop-grid">{selected.region_preview_urls.map((url, index) => <button type="button" className="crop-button" key={url} onClick={() => window.open(fileUrl(url), "_blank", "noopener,noreferrer")}><img src={fileUrl(url)} alt={`Answer evidence for question ${selected.question_number}, region ${index + 1}`} /><span>Region {index + 1} · Open image</span></button>)}</div>}</div>
            <div className="context-pane"><div className="panel-heading"><div><h3>Question context</h3><p>Use the approved question and criteria when available.</p></div></div><div className="context-placeholder">Question text is not included in this result payload. Review the approved question bank if more context is needed.</div><div className="signal-list"><div><span>AI recommendation</span><strong className="text-ai">Draft only</strong></div><div><span>Model confidence</span><strong>{selected.confidence}</strong></div><div><span>Answer state</span><strong>{selected.ink_status}</strong></div><div><span>Choice rule</span><strong>{choiceStatusLabel(selected.choice_status)}</strong></div>{selected.ink_density_ratio !== null && <div><span>Ink density</span><strong>{selected.ink_density_ratio.toFixed(3)}</strong></div>}</div></div>
          </div>

          {selected.transcription_summary && <div className="transcription-block"><strong>Transcription summary</strong><p>{selected.transcription_summary}</p></div>}
          {selected.part_scores.length > 0 && <div className="part-score-block"><div className="panel-heading"><div><h3>Part-score rationale</h3><p>Review how the draft was broken down.</p></div></div><div className="table-container"><table className="table"><thead><tr><th>Part</th><th>Awarded</th><th>Possible</th><th>Evidence rationale</th></tr></thead><tbody>{selected.part_scores.map((part, index) => <tr key={`${part.part}-${index}`}><td><strong>{part.part || "—"}</strong></td><td>{part.marks_awarded}</td><td>{part.marks_possible}</td><td>{part.rationale}</td></tr>)}</tbody></table></div></div>}
          {selected.flags.length > 0 && <div className="flag-list"><strong>Flags to consider</strong>{selected.flags.map((flag, index) => <div className="flag-row" key={`${flag}-${index}`}><AlertTriangle size={15} />{flag}</div>)}</div>}

          <div className="decision-panel"><div className="panel-heading"><div><h3>Examiner decision</h3><p>Confirm the draft or adjust it within the allowed marks range.</p></div></div><div className="decision-form"><div className="score-field"><label className="form-label" htmlFor="confirmed-score">Confirmed score</label><div className="score-input-wrap"><input id="confirmed-score" type="number" min={0} max={selected.ai_total_possible ?? undefined} step={1} className="form-input" value={confirmScore} onChange={(event) => setConfirmScore(event.target.value)} aria-describedby="score-range" /><span>/ {selected.ai_total_possible ?? "?"}</span></div><small id="score-range" className="field-help">{selected.ai_total_possible === null ? "Marks limit unavailable" : `Allowed range: 0–${selected.ai_total_possible} marks`}</small></div><div className="form-group note-field"><label className="form-label" htmlFor="reviewer-note">Examiner note</label><textarea id="reviewer-note" className="form-input" rows={2} value={confirmNote} onChange={(event) => setConfirmNote(event.target.value)} placeholder="Recommended when changing the AI draft." /></div><button type="button" className="btn btn-success" onClick={submitConfirm} disabled={saving || confirmScore === "" || selected.ai_total_possible === null}><CheckCircle2 size={16} />{saving ? "Saving…" : selected.reviewed ? "Update confirmed score" : "Confirm score"}</button></div></div>
        </section> : <div className="empty-state"><h3>No result selected</h3><p>Choose a question from the review queue.</p></div>}
      </div>
    </div>
  );
}
