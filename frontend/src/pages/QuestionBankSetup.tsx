import { AlertTriangle, ArrowLeft, Check, CheckCircle2, GraduationCap, Lock, Plus, Trash2, Unlock } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { addQuestionBankItem, confirmQuestionBank, deleteQuestionBankItem, getProject, listQuestionBank, listQuestionGroups, QuestionBankItem, QuestionGroup, unlockQuestionBank, updateQuestionBankItem } from "../api/client";
import { errorMessage } from "../ui";

export default function QuestionBankSetup() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [items, setItems] = useState<QuestionBankItem[]>([]);
  const [groups, setGroups] = useState<QuestionGroup[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [warning, setWarning] = useState<string | null>(null);
  const [structureStatus, setStructureStatus] = useState("unresolved");
  const [effectiveTotal, setEffectiveTotal] = useState<number | null>(null);
  const [rawTotal, setRawTotal] = useState<number | null>(null);
  const [statedTotal, setStatedTotal] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [newQuestionNumber, setNewQuestionNumber] = useState("");
  const [savedQuestion, setSavedQuestion] = useState<string | null>(null);

  const load = () => {
    if (!projectId) return;
    setLoading(true); setError("");
    Promise.all([listQuestionBank(projectId), listQuestionGroups(projectId), getProject(projectId)]).then(([bank, groupData, project]) => {
      setItems(bank.items); setGroups(groupData); setConfirmed(bank.confirmed); setWarning(project.question_bank_marks_warning ?? null); setStructureStatus(project.question_bank_structure_status ?? "unresolved"); setEffectiveTotal(project.question_bank_effective_total ?? null); setRawTotal(project.question_bank_raw_total ?? null); setStatedTotal(project.question_bank_stated_total ?? null);
    }).catch((err) => setError(errorMessage(err))).finally(() => setLoading(false));
  };
  useEffect(load, [projectId]);

  const updateLocalField = (questionNumber: string, field: "marks_possible" | "key_points", value: string) => {
    setItems((prev) => prev.map((item) => item.question_number === questionNumber ? { ...item, [field]: field === "marks_possible" ? (value === "" ? null : Number(value)) : value } : item));
    setSavedQuestion(null);
  };

  const resizeElement = (element: HTMLTextAreaElement | null) => { if (!element) return; element.style.height = "0px"; element.style.height = `${Math.max(element.scrollHeight, 70)}px`; };
  const resize = (event: FormEvent<HTMLTextAreaElement>) => resizeElement(event.currentTarget);

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
      setConfirmed(true); setWarning(result.marks_mismatch_warning ?? null); setStructureStatus(result.structure_status ?? "unresolved"); setEffectiveTotal(result.effective_total ?? null); setRawTotal(result.total_marks_extracted); setStatedTotal(result.total_marks_on_paper); setMessage(result.marks_mismatch_warning ? "Question bank locked, but paper structure still needs review." : "Question bank confirmed and locked.");
      if (!result.marks_mismatch_warning) navigate(`/projects/${projectId}`);
    } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  const unlock = async () => {
    if (!projectId) return;
    setError(""); setMessage(""); setSaving(true);
    try { const data = await unlockQuestionBank(projectId); setConfirmed(data.confirmed); setWarning(null); setStructureStatus("unresolved"); setEffectiveTotal(null); setRawTotal(null); setStatedTotal(null); setMessage("Question bank unlocked for re-editing."); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  if (!projectId) return null;
  if (loading) return <div className="loading-state" role="status">Loading question bank…</div>;
  const totalMarks = items.reduce((sum, item) => sum + (item.marks_possible ?? 0), 0);
  const structureResolved = structureStatus === "resolved" || structureStatus === "resolved_without_stated_total";

  return <div>
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Question bank</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Assessment setup</div><div className="title-with-badges"><h1>Question bank</h1><span className={`badge ${confirmed ? "badge-success" : "badge-warning"}`}>{confirmed ? <><CheckCircle2 size={12} /> Confirmed and locked</> : "Draft · review before locking"}</span></div><p>Review extracted questions and criteria before grading. {items.length} question{items.length === 1 ? "" : "s"} · {rawTotal ?? totalMarks} raw marks{effectiveTotal !== null ? ` · ${effectiveTotal} effective marks` : ""}.</p></div>{!confirmed ? <button type="button" className="btn btn-success" onClick={confirmAndLock} disabled={saving || items.length === 0}><Lock size={16} /> Confirm and lock</button> : <button type="button" className="btn btn-secondary" onClick={unlock} disabled={saving}><Unlock size={16} /> Unlock to edit</button>}</div>
    {error && <div className="alert alert-error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>}
    {message && !warning && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>{message}</span></div>}
    {warning && <div className="alert alert-warning" role="alert"><AlertTriangle size={17} /><span><strong>Paper structure needs review.</strong> {warning}</span><Link to={`/projects/${projectId}/question-groups`} className="alert-action">Review choice groups</Link></div>}
    <div className={`structure-summary ${structureResolved ? "is-resolved" : ""}`}><div><span className="eyebrow">Assessment structure</span><strong>{structureResolved ? "Candidate maximum is resolved" : "Candidate maximum needs confirmation"}</strong><p>{effectiveTotal !== null ? `${effectiveTotal} marks count toward a candidate’s maximum` : "Confirm the question groups to calculate the candidate maximum."}{statedTotal !== null ? ` · Paper states ${statedTotal} marks.` : ""}</p></div><div className="structure-metrics"><span><b>{rawTotal ?? totalMarks}</b> raw</span><span><b>{statedTotal ?? "—"}</b> stated</span><span><b>{effectiveTotal ?? "—"}</b> effective</span><Link to={`/projects/${projectId}/question-groups`} className="btn btn-secondary btn-sm"><GraduationCap size={14} /> {groups.length ? "Review groups" : "Configure groups"}</Link></div></div>
    <div className="info-panel"><strong>Before locking</strong><p>Check question numbers, maximum marks, and key points. Optional sections are calculated from selectable groups, so raw extracted marks may be higher than the candidate’s effective maximum.</p></div>
    {items.length === 0 ? <div className="empty-state"><div className="empty-state-icon"><AlertTriangle size={28} /></div><h3>No question-bank items available</h3><p>The rubric may be scanned or have no extractable text. Add a question manually below.</p></div> : <div className="table-container"><table className="table question-bank-table"><thead><tr><th>Question</th><th className="marks-column">Marks</th><th>Key points and marking criteria</th>{!confirmed && <th>Actions</th>}</tr></thead><tbody>{items.map((item) => <tr key={item.question_number}><td><strong>{item.question_number}</strong></td><td><input type="number" min={0} step={1} className="form-input compact-input" value={item.marks_possible ?? ""} disabled={confirmed} onChange={(event) => updateLocalField(item.question_number, "marks_possible", event.target.value)} onBlur={() => saveRow(item)} aria-label={`Marks for question ${item.question_number}`} /></td><td><textarea className="form-input auto-grow-textarea" rows={2} ref={resizeElement} value={item.key_points ?? ""} disabled={confirmed} onInput={resize} onChange={(event) => updateLocalField(item.question_number, "key_points", event.target.value)} aria-label={`Key points for question ${item.question_number}`} /><div className="row-meta">{savedQuestion === item.question_number && <span className="saved-note"><Check size={13} /> Saved</span>}{item.question_image_path && <span>Question image available</span>}</div></td>{!confirmed && <td><button type="button" className="icon-button danger" onClick={() => removeRow(item.question_number)} aria-label={`Remove question ${item.question_number}`}><Trash2 size={15} /></button></td>}</tr>)}</tbody></table></div>}
    {!confirmed && <div className="inline-add card"><div className="form-group"><label className="form-label" htmlFor="new-question">Add question manually</label><input id="new-question" type="text" className="form-input" value={newQuestionNumber} onChange={(event) => setNewQuestionNumber(event.target.value)} placeholder="e.g. 5 or 5a" /></div><button type="button" className="btn btn-secondary" onClick={addRow}><Plus size={16} /> Add question</button></div>}
  </div>;
}
