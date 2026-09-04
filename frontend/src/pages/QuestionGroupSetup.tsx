import { AlertTriangle, ArrowLeft, CheckCircle2, Info, Plus, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { confirmQuestionGroup, createQuestionGroup, deleteQuestionGroup, listQuestionBank, listQuestionGroups, QuestionBankItem, QuestionGroup } from "../api/client";
import { errorMessage } from "../ui";

export default function QuestionGroupSetup() {
  const { projectId } = useParams();
  const [groups, setGroups] = useState<QuestionGroup[]>([]);
  const [questionBank, setQuestionBank] = useState<QuestionBankItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [groupName, setGroupName] = useState("");
  const [selectionType, setSelectionType] = useState<"compulsory" | "choose_n_of_m">("compulsory");
  const [selectedQuestions, setSelectedQuestions] = useState<string[]>([]);
  const [nRequired, setNRequired] = useState(1);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = () => {
    if (!projectId) return;
    setLoading(true); setError("");
    Promise.all([listQuestionGroups(projectId), listQuestionBank(projectId)])
      .then(([groupData, bankData]) => { setGroups(groupData); setQuestionBank(bankData.items); })
      .catch((err) => setError(errorMessage(err)))
      .finally(() => setLoading(false));
  };
  useEffect(load, [projectId]);

  const assignedTo = useMemo(() => {
    const map = new Map<string, string>();
    groups.forEach((group) => group.question_numbers.forEach((question) => map.set(question, group.group_name)));
    return map;
  }, [groups]);

  const toggleQuestion = (questionNumber: string) => {
    if (assignedTo.has(questionNumber) && !selectedQuestions.includes(questionNumber)) return;
    setSelectedQuestions((prev) => prev.includes(questionNumber) ? prev.filter((question) => question !== questionNumber) : [...prev, questionNumber]);
  };

  const submitGroup = async () => {
    if (!projectId || !groupName.trim() || selectedQuestions.length === 0) { setError("Enter a group name and select at least one question."); return; }
    if (selectionType === "choose_n_of_m" && (!Number.isInteger(nRequired) || nRequired < 1 || nRequired > selectedQuestions.length)) { setError("Required number must be between 1 and the number of selected questions."); return; }
    setError(""); setMessage("");
    try {
      await createQuestionGroup(projectId, { group_name: groupName.trim(), selection_type: selectionType, question_numbers: selectedQuestions, n_required: selectionType === "choose_n_of_m" ? nRequired : undefined });
      setGroupName(""); setSelectedQuestions([]); setNRequired(1); setMessage("Question group created."); load();
    } catch (err) { setError(errorMessage(err)); }
  };

  const confirmGroup = async (group: QuestionGroup) => {
    if (!projectId) return;
    setError(""); setMessage("");
    try {
      const confirmed = await confirmQuestionGroup(projectId, group.id);
      setGroups((prev) => prev.map((item) => item.id === confirmed.id ? confirmed : item));
      setMessage(`${group.group_name} confirmed.`);
    } catch (err) { setError(errorMessage(err)); }
  };

  const removeGroup = async (group: QuestionGroup) => {
    if (!projectId || !window.confirm(`Delete the “${group.group_name}” question group?`)) return;
    setDeletingId(group.id); setError("");
    try { await deleteQuestionGroup(projectId, group.id); setGroups((prev) => prev.filter((item) => item.id !== group.id)); } catch (err) { setError(errorMessage(err)); } finally { setDeletingId(null); }
  };

  if (!projectId) return null;
  if (loading) return <div className="loading-state" role="status">Loading question groups…</div>;

  return <div>
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span aria-hidden="true">/</span><span>Question groups</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Assessment setup</div><h1>Question groups</h1><p>Review detected choice structures, then define or confirm the rules used for scoring.</p></div></div>
    {error && <div className="alert alert-error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>}
    {message && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>{message}</span></div>}
    <div className="info-panel"><Info size={17} /><div><strong>How choice questions work</strong><p>For a choose-N-of-M group, the first N attempted items in ascending question order are scored. A crossed-out answer counts as an attempt and consumes a slot. Suggested groups remain provisional until you confirm them.</p></div></div>
    <section className="card form-card"><div className="section-heading"><div><h2>Add question group</h2><p>Create a rule that matches the paper’s scoring structure.</p></div></div><div className="form-grid"><div className="form-group"><label className="form-label" htmlFor="group-name">Group name</label><input id="group-name" type="text" className="form-input" value={groupName} onChange={(event) => setGroupName(event.target.value)} placeholder="e.g. Section B" /></div><div className="form-group"><label className="form-label" htmlFor="selection-type">Selection type</label><select id="selection-type" className="form-input" value={selectionType} onChange={(event) => setSelectionType(event.target.value as "compulsory" | "choose_n_of_m")}><option value="compulsory">Compulsory · all selected questions count</option><option value="choose_n_of_m">Choose N of M · first N attempts count</option></select></div>{selectionType === "choose_n_of_m" && <div className="form-group narrow-field"><label className="form-label" htmlFor="n-required">N required</label><input id="n-required" type="number" min={1} max={selectedQuestions.length || undefined} className="form-input" value={nRequired} onChange={(event) => setNRequired(Number(event.target.value))} /></div>}</div><div className="form-group"><span className="form-label">Questions in this group</span><div className="question-chip-list">{questionBank.map((item) => { const selected = selectedQuestions.includes(item.question_number); const group = assignedTo.get(item.question_number); return <button key={item.question_number} type="button" className={`question-chip ${selected ? "is-selected" : ""} ${group && !selected ? "is-disabled" : ""}`} onClick={() => toggleQuestion(item.question_number)} disabled={Boolean(group && !selected)} title={group ? `Already assigned to ${group}` : undefined}>{item.question_number}{group && !selected && <small>Assigned</small>}</button>; })}</div></div><div className="form-actions"><span className="field-help">{selectedQuestions.length} question{selectedQuestions.length === 1 ? "" : "s"} selected</span><button type="button" className="btn btn-primary" onClick={submitGroup} disabled={!groupName.trim() || selectedQuestions.length === 0}><Plus size={16} /> Create group</button></div></section>
    <div className="section-heading"><div><h2>Detected and confirmed groups</h2><p>Provisional suggestions are editable decisions, never binding grading rules.</p></div></div>
    {groups.length === 0 ? <div className="empty-state"><h3>No question groups configured</h3><p>Add a compulsory group or choose-N-of-M group if the paper needs one.</p></div> : <div className="card-grid">{groups.map((group) => <article className="card group-card" key={group.id}><div className="group-card-header"><div><h3>{group.group_name}</h3><span className={`badge ${group.suggestion_status === "provisional" ? "badge-warning" : group.selection_type === "compulsory" ? "badge-slate" : "badge-indigo"}`}>{group.suggestion_status === "provisional" ? `Suggested · ${group.suggestion_confidence ?? "medium"} confidence` : group.selection_type === "compulsory" ? "Compulsory" : `Choose ${group.n_required} of ${group.selection_units?.length ?? group.question_numbers.length}`}</span></div><div className="button-row">{group.suggestion_status === "provisional" && <button type="button" className="btn btn-success btn-sm" onClick={() => void confirmGroup(group)}>Confirm</button>}<button type="button" className="icon-button danger" onClick={() => removeGroup(group)} disabled={deletingId === group.id} aria-label={`Delete ${group.group_name}`}><Trash2 size={15} /></button></div></div><p className="group-question-list">{group.selection_type === "choose_n_of_m" ? "Selectable choices" : "Questions"}: {(group.selection_units?.length ? group.selection_units : group.question_numbers.map((question) => [question])).map((unit) => unit.join(" + ")).join(", ")}</p>{group.selection_type === "choose_n_of_m" && <p className="field-help">First {group.n_required} attempted items count in ascending order.</p>}{group.suggestion_evidence && <p className="field-help">Detected from: {group.suggestion_evidence}</p>}</article>)}</div>}
  </div>;
}
