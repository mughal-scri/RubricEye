import { Check, Save, Sparkles } from "lucide-react";
import { useCallback } from "react";
import { RubricStudioCriterion, RubricStudioCriterionDraft } from "../api/client";

type Criterion = RubricStudioCriterion | RubricStudioCriterionDraft;
type EditableField = "marks_possible" | "key_points";

interface RubricCriteriaEditorProps {
  criteria: Criterion[];
  readOnly?: boolean;
  saving?: boolean;
  onChange: (questionNumber: string, field: EditableField, value: string | number | null) => void;
  onSave?: (criterion: Criterion) => void;
}

export default function RubricCriteriaEditor({ criteria, readOnly = false, saving = false, onChange, onSave }: RubricCriteriaEditorProps) {
  const resizeElement = useCallback((element: HTMLTextAreaElement | null) => {
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.max(element.scrollHeight, 84)}px`;
  }, []);

  if (!criteria.length) {
    return <div className="empty-state"><Sparkles size={26} /><h3>No criteria returned</h3><p>Use the manual rubric path or generate a new draft.</p></div>;
  }

  return (
    <div className="studio-criteria-list" aria-label="Rubric criteria in question-paper order">
      {criteria.map((criterion, index) => (
        <article className="card studio-criterion" key={`${criterion.question_number}-${index}`}>
          {criterion.section_label && <div className="eyebrow">{criterion.section_label}</div>}
          <div className="studio-criterion-header">
            <div className="criterion-title"><span className="criterion-index">{String(index + 1).padStart(2, "0")}</span><strong>Q{criterion.question_number}</strong></div>
            <span className={`badge ${criterion.rubric_confidence === "high" ? "badge-success" : criterion.rubric_confidence === "medium" ? "badge-warning" : "badge-slate"}`}>{criterion.rubric_confidence ?? "low"} confidence</span>
          </div>
          {criterion.question_text && <p className="studio-question-text">{criterion.question_text}</p>}
          <div className="form-grid">
            <div className="form-group">
              <label className="form-label" htmlFor={`studio-marks-${criterion.question_number}-${index}`}>Maximum marks</label>
              <input id={`studio-marks-${criterion.question_number}-${index}`} type="number" min={0} step={1} className="form-input" value={criterion.marks_possible ?? ""} disabled={readOnly} onChange={(event) => onChange(criterion.question_number, "marks_possible", event.target.value === "" ? null : Number(event.target.value))} onBlur={() => onSave?.(criterion)} />
            </div>
            <div className="form-group">
              <label className="form-label">Source signal</label>
              <div className="provenance-note">{criterion.rubric_provenance ?? "Question-paper wording"}</div>
            </div>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor={`studio-key-points-${criterion.question_number}-${index}`}>Generated marking criteria</label>
            <textarea id={`studio-key-points-${criterion.question_number}-${index}`} className="form-input auto-grow-textarea" rows={3} ref={resizeElement} value={criterion.key_points ?? ""} disabled={readOnly} onInput={(event) => resizeElement(event.currentTarget)} onChange={(event) => onChange(criterion.question_number, "key_points", event.target.value)} onBlur={() => onSave?.(criterion)} />
          </div>
          {!readOnly && onSave && <div className="studio-criterion-actions"><span className="field-help"><Check size={13} /> Edit the wording, marks, or order before saving.</span><button type="button" className="btn btn-secondary btn-sm" onClick={() => onSave(criterion)} disabled={saving}><Save size={14} /> Save criterion</button></div>}
        </article>
      ))}
    </div>
  );
}
