import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Circle,
  HelpCircle,
  ImageOff,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AnswerSheetResultsResponse,
  confirmGradingResult,
  fileUrl,
  GradingResult,
  listGradingResults,
} from "../api/client";

const CONFIDENCE_BADGE: Record<string, string> = {
  high: "badge-success",
  medium: "badge-warning",
  low: "badge-slate",
};

const CHOICE_STATUS_LABEL: Record<string, string> = {
  graded: "Graded",
  skipped_blank: "Blank -- skipped",
  skipped_beyond_n: "Skipped (beyond N)",
  flagged_ambiguous: "Ambiguous -- needs review",
  no_regions: "No matching region",
};

export default function GradingResults() {
  const { projectId, sheetId } = useParams();
  const [data, setData] = useState<AnswerSheetResultsResponse | null>(null);
  const [selectedQuestion, setSelectedQuestion] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [confirmScore, setConfirmScore] = useState<string>("");
  const [confirmNote, setConfirmNote] = useState<string>("");
  const [saving, setSaving] = useState(false);

  const load = () => {
    if (!projectId || !sheetId) return;
    setLoading(true);
    listGradingResults(projectId, sheetId)
      .then((body) => {
        setData(body);
        if (!selectedQuestion && body.results.length > 0) {
          setSelectedQuestion(body.results[0].question_number);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  };

  useEffect(load, [projectId, sheetId]);

  const selected: GradingResult | undefined = useMemo(
    () => data?.results.find((r) => r.question_number === selectedQuestion),
    [data, selectedQuestion]
  );

  useEffect(() => {
    if (selected) {
      setConfirmScore(String(selected.human_confirmed_score ?? selected.ai_score ?? ""));
      setConfirmNote(selected.human_reviewer_note ?? "");
    }
  }, [selected]);

  const submitConfirm = async () => {
    if (!projectId || !sheetId || !selected || confirmScore === "") return;
    setSaving(true);
    setError("");
    try {
      await confirmGradingResult(projectId, sheetId, selected.question_number, {
        human_confirmed_score: Number(confirmScore),
        human_reviewer_note: confirmNote || null,
      });
      load();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  if (!projectId || !sheetId) return null;
  if (loading) return <div style={{ textAlign: "center", padding: "3rem" }}>Loading grading results...</div>;
  if (error) return <div className="alert alert-error">Error: {error}</div>;
  if (!data) return null;

  return (
    <div>
      <div className="breadcrumb">
        <Link to={`/projects/${projectId}/answer-sheets/${sheetId}`}><ArrowLeft size={14} /> Back to Answer Sheet</Link>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1>Grading Results</h1>
            <span className={`badge ${data.grading_status === "complete" ? "badge-success" : "badge-warning"}`}>
              {data.grading_status}
            </span>
          </div>
          <p>
            Grand total: <strong>{data.summary.grand_total_awarded} / {data.summary.grand_total_possible}</strong>
          </p>
        </div>
      </div>

      {/* Section roll-up */}
      <div className="card-grid" style={{ marginBottom: "1.5rem" }}>
        {data.summary.sections.map((section) => (
          <div key={section.section_name} className="card" style={{ padding: "1.25rem" }}>
            <div style={{ fontWeight: 700 }}>{section.section_name}</div>
            <div style={{ fontSize: "1.3rem", fontWeight: 800, color: "var(--color-brand-600)", marginTop: "0.4rem" }}>
              {section.section_total_awarded} / {section.section_total_possible}
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: "1.5rem" }}>
        {/* Left sidebar */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {data.results.map((result) => {
            const isActive = result.question_number === selectedQuestion;
            return (
              <button
                key={result.question_number}
                type="button"
                onClick={() => setSelectedQuestion(result.question_number)}
                className="card"
                style={{
                  textAlign: "left",
                  padding: "0.85rem 1rem",
                  cursor: "pointer",
                  border: isActive ? "2px solid var(--color-brand-500)" : undefined,
                  background: isActive ? "var(--color-brand-50)" : undefined,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 700 }}>Q{result.question_number}</span>
                  {result.reviewed ? (
                    <span className="badge badge-success"><CheckCircle2 size={11} /> Confirmed</span>
                  ) : (
                    <span className="badge badge-warning"><Circle size={11} /> Pending</span>
                  )}
                </div>
                <div style={{ fontSize: "0.85rem", color: "var(--color-slate-500)", marginTop: "0.25rem" }}>
                  {result.ai_score !== null ? `${result.ai_score} / ${result.ai_total_possible}` : CHOICE_STATUS_LABEL[result.choice_status]}
                </div>
              </button>
            );
          })}
        </div>

        {/* Right panel */}
        {selected && (
          <div className="card" style={{ padding: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1rem" }}>
              <h2 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Question {selected.question_number}</h2>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <span className={`badge ${CONFIDENCE_BADGE[selected.confidence] ?? "badge-slate"}`}>
                  Confidence: {selected.confidence}
                </span>
                <span className="badge badge-slate">
                  {selected.ink_status === "attempted" && <CheckCircle2 size={11} />}
                  {selected.ink_status === "blank" && <Circle size={11} />}
                  {selected.ink_status === "ambiguous" && <HelpCircle size={11} />}
                  {" "}{selected.ink_status}
                </span>
              </div>
            </div>

            {selected.grading_status === "failed" && (
              <div className="alert alert-error">
                <AlertTriangle size={18} style={{ flexShrink: 0 }} />
                <span>{selected.error_message ?? "Grading failed for this question."}</span>
              </div>
            )}

            {selected.choice_status !== "graded" && (
              <div className="alert alert-warning">
                <AlertTriangle size={18} style={{ flexShrink: 0 }} />
                <span>{CHOICE_STATUS_LABEL[selected.choice_status]}</span>
              </div>
            )}

            {selected.transcription_summary && (
              <p style={{ color: "var(--color-slate-600)", fontSize: "0.9rem" }}>{selected.transcription_summary}</p>
            )}

            {selected.part_scores.length > 0 && (
              <div className="table-container" style={{ marginBottom: "1rem" }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Part</th>
                      <th>Awarded</th>
                      <th>Possible</th>
                      <th>Rationale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selected.part_scores.map((part, idx) => (
                      <tr key={idx}>
                        <td>{part.part || "--"}</td>
                        <td>{part.marks_awarded}</td>
                        <td>{part.marks_possible}</td>
                        <td style={{ fontSize: "0.85rem" }}>{part.rationale}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {selected.flags.length > 0 && (
              <div style={{ marginBottom: "1rem" }}>
                {selected.flags.map((flag, idx) => (
                  <div key={idx} className="alert alert-warning" style={{ marginBottom: "0.5rem" }}>
                    <AlertTriangle size={16} style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: "0.85rem" }}>{flag}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Region previews */}
            <div style={{ marginBottom: "1.25rem" }}>
              <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--color-slate-600)", marginBottom: "0.5rem" }}>
                Cropped Answer Regions
              </div>
              {selected.region_preview_urls.length === 0 ? (
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--color-slate-400)" }}>
                  <ImageOff size={16} /> No region images found.
                </div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
                  {selected.region_preview_urls.map((url) => (
                    <img
                      key={url}
                      src={fileUrl(url)}
                      alt={`Region for Q${selected.question_number}`}
                      style={{ maxWidth: "260px", border: "1px solid var(--color-slate-200)", borderRadius: "var(--radius-md)" }}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Examiner confirmation */}
            <div style={{ borderTop: "1px solid var(--color-slate-200)", paddingTop: "1.25rem" }}>
              <h3 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Examiner Confirmation</h3>
              <div style={{ display: "flex", gap: "1rem", alignItems: "flex-end" }}>
                <div className="form-group" style={{ marginBottom: 0, maxWidth: "140px" }}>
                  <label className="form-label">Confirmed score</label>
                  <input
                    type="number"
                    className="form-input"
                    value={confirmScore}
                    onChange={(e) => setConfirmScore(e.target.value)}
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0, flex: 1 }}>
                  <label className="form-label">Reviewer note (optional)</label>
                  <input
                    type="text"
                    className="form-input"
                    value={confirmNote}
                    onChange={(e) => setConfirmNote(e.target.value)}
                  />
                </div>
                <button type="button" className="btn btn-success" onClick={submitConfirm} disabled={saving || confirmScore === ""}>
                  <CheckCircle2 size={16} /> Confirm Score
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
