import { AlertTriangle, ArrowLeft, Check, CheckCircle2, Lock, Plus, Trash2, Unlock } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { addQuestionBankItem, confirmQuestionBank, deleteQuestionBankItem, listQuestionBank, QuestionBankItem, unlockQuestionBank, updateQuestionBankItem } from "../api/client";
import { errorMessage } from "../ui";

export default function QuestionBankSetup() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [items, setItems] = useState<QuestionBankItem[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [warning, setWarning] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newQuestionNumber, setNewQuestionNumber] = useState("");
  const [savedQuestion, setSavedQuestion] = useState<string | null>(null);

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    listQuestionBank(projectId).then((data) => { setItems(data.items); setConfirmed(data.confirmed); }).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  };
  useEffect(load, [projectId]);

  const updateLocalField = (questionNumber: string, field: "marks_possible" | "key_points", value: string) => {
    setItems((prev) => prev.map((item) => item.question_number === questionNumber ? { ...item, [field]: field === "marks_possible" ? (value === "" ? null : Number(value)) : value } : item));
    setSavedQuestion(null);
  };

  const saveRow = async (item: QuestionBankItem): Promise<boolean> => {
    if (!projectId) return false;
    if (item.marks_possible !== null && (!Number.isInteger(item.marks_possible) || item.marks_possible < 0)) { setError(`Marks for ${item.question_number} must be a non-negative whole number.`); return false; }
    setError("");
    try { await updateQuestionBankItem(projectId, item.question_number, { marks_possible: item.marks_possible, key_points: item.key_points }); setSavedQuestion(item.question_number); return true; } catch (err) { setError(errorMessage(err)); return false; }
  };

  const removeRow = async (questionNumber: string) => {
    if (!projectId || !window.confirm(`Remove question ${questionNumber} from the draft question bank?`)) return;
    try { await deleteQuestionBankItem(projectId, questionNumber); setItems((prev) => prev.filter((item) => item.question_number !== questionNumber)); } catch (err) { setError(errorMessage(err)); }
  };

  const addRow = async () => {
    if (!projectId || !newQuestionNumber.trim()) { setError("Enter a question number before adding it."); return; }
    try { const created = await addQuestionBankItem(projectId, newQuestionNumber.trim(), null, null); setItems((prev) => [...prev, created]); setNewQuestionNumber(""); setMessage("Question added to the draft bank."); } catch (err) { setError(errorMessage(err)); }
  };

  const confirmAndLock = async () => {
    if (!projectId) return;
    setError(""); setMessage(""); setSaving(true);
    try {
      const savedRows = await Promise.all(items.map((item) => saveRow(item)));
      if (savedRows.some((saved) => !saved)) return;
      const result = await confirmQuestionBank(projectId);
      setConfirmed(true); setWarning(result.marks_mismatch_warning);
      setMessage(result.marks_mismatch_warning ? "Question bank locked. Review the marks warning before continuing." : "Question bank confirmed and locked.");
      if (!result.marks_mismatch_warning) navigate(`/projects/${projectId}`);
    } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  const unlock = async () => {
    if (!projectId) return;
    setError(""); setMessage(""); setSaving(true);
    try { const data = await unlockQuestionBank(projectId); setConfirmed(data.confirmed); setWarning(null); setMessage("Question bank unlocked for re-editing."); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  if (!projectId) return null;
  if (loading) return <div className="loading-state" role="status">Loading question bank…</div>;
  const totalMarks = items.reduce((sum, item) => sum + (item.marks_possible ?? 0), 0);

  return <div>
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Question bank</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Assessment setup</div><div className="title-with-badges"><h1>Question bank</h1><span className={`badge ${confirmed ? "badge-success" : "badge-warning"}`}>{confirmed ? <><CheckCircle2 size={12} /> Confirmed and locked</> : "Draft · review before locking"}</span></div><p>Review extracted question numbers, marks, and key points before grading. {items.length} question{items.length === 1 ? "" : "s"} · {totalMarks} extracted marks.</p></div>{!confirmed ? <button type="button" className="btn btn-success" onClick={confirmAndLock} disabled={saving || items.length === 0}><Lock size={16} /> Confirm and lock</button> : <button type="button" className="btn btn-secondary" onClick={unlock} disabled={saving}><Unlock size={16} /> Unlock to edit</button>}</div>
    {error && <div className="alert alert-error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>}
    {message && !warning && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>{message}</span></div>}
    {warning && <div className="alert alert-warning" role="alert"><AlertTriangle size={17} /><span><strong>Review marks before continuing.</strong> {warning}</span></div>}
    <div className="info-panel"><strong>Before locking</strong><p>Check question numbers, maximum marks, and key points. The approved question bank becomes the assessment criteria used for grading.</p></div>
    {items.length === 0 ? <div className="empty-state"><div className="empty-state-icon"><AlertTriangle size={28} /></div><h3>No question-bank items available</h3><p>The rubric may be scanned or have no extractable text. Add a question manually below.</p></div> : <div className="table-container"><table className="table"><thead><tr><th>Question</th><th className="marks-column">Marks</th><th>Key points and marking criteria</th>{!confirmed && <th>Actions</th>}</tr></thead><tbody>{items.map((item) => <tr key={item.question_number}><td><strong>{item.question_number}</strong></td><td><input type="number" min={0} step={1} className="form-input compact-input" value={item.marks_possible ?? ""} disabled={confirmed} onChange={(event) => updateLocalField(item.question_number, "marks_possible", event.target.value)} onBlur={() => saveRow(item)} aria-label={`Marks for question ${item.question_number}`} /></td><td><textarea className="form-input" rows={2} value={item.key_points ?? ""} disabled={confirmed} onChange={(event) => updateLocalField(item.question_number, "key_points", event.target.value)} onBlur={() => saveRow(item)} aria-label={`Key points for question ${item.question_number}`} /><div className="row-meta">{savedQuestion === item.question_number && <span className="saved-note"><Check size={13} /> Saved</span>}{item.question_image_path && <span>Question image available</span>}</div></td>{!confirmed && <td><button type="button" className="icon-button danger" onClick={() => removeRow(item.question_number)} aria-label={`Remove question ${item.question_number}`}><Trash2 size={15} /></button></td>}</tr>)}</tbody></table></div>}
    {!confirmed && <div className="inline-add card"><div className="form-group"><label className="form-label" htmlFor="new-question">Add question manually</label><input id="new-question" type="text" className="form-input" value={newQuestionNumber} onChange={(event) => setNewQuestionNumber(event.target.value)} placeholder="e.g. 5 or 5a" /></div><button type="button" className="btn btn-secondary" onClick={addRow}><Plus size={16} /> Add question</button></div>}
  </div>;
}
