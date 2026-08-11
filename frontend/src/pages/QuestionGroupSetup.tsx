import { ArrowLeft, CheckCircle2, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  createQuestionGroup,
  deleteQuestionGroup,
  listQuestionBank,
  listQuestionGroups,
  QuestionBankItem,
  QuestionGroup,
} from "../api/client";

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
  const [nRequired, setNRequired] = useState<number>(1);

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    Promise.all([listQuestionGroups(projectId), listQuestionBank(projectId)])
      .then(([groupData, bankData]) => {
        setGroups(groupData);
        setQuestionBank(bankData.items);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  };

  useEffect(load, [projectId]);

  const alreadyGrouped = new Set(groups.flatMap((g) => g.question_numbers));

  const toggleQuestion = (questionNumber: string) => {
    setSelectedQuestions((prev) =>
      prev.includes(questionNumber) ? prev.filter((q) => q !== questionNumber) : [...prev, questionNumber]
    );
  };

  const submitGroup = async () => {
    if (!projectId || !groupName.trim() || selectedQuestions.length === 0) return;
    setError("");
    setMessage("");
    try {
      if (selectionType === "choose_n_of_m" && nRequired > selectedQuestions.length) {
        setError("N required cannot exceed the number of selected questions.");
        return;
      }
      await createQuestionGroup(projectId, {
        group_name: groupName.trim(),
        selection_type: selectionType,
        question_numbers: selectedQuestions,
        n_required: selectionType === "choose_n_of_m" ? nRequired : undefined,
      });
      setGroupName("");
      setSelectedQuestions([]);
      setNRequired(1);
      setMessage("Question group created.");
      load();
    } catch (err) {
      setError(String(err));
    }
  };

  const removeGroup = async (groupId: string) => {
    if (!projectId) return;
    setError("");
    try {
      await deleteQuestionGroup(projectId, groupId);
      load();
    } catch (err) {
      setError(String(err));
    }
  };

  if (!projectId) return null;
  if (loading) return <div style={{ textAlign: "center", padding: "3rem" }}>Loading question groups...</div>;

  return (
    <div>
      <div className="breadcrumb">
        <Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to Project</Link>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <h1>Question Group Setup</h1>
          <p>
            Define which questions are compulsory and which are choice groups (e.g. "choose any 2 of Q2-Q4").
            Any question not placed in a group is treated as compulsory by default during grading.
          </p>
        </div>
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      {message && <div className="alert alert-success"><CheckCircle2 size={18} /> <span>{message}</span></div>}

      <div className="card" style={{ padding: "1.5rem", marginBottom: "1.5rem" }}>
        <h3 style={{ marginTop: 0, marginBottom: "1rem", fontFamily: "var(--font-display)" }}>New Group</h3>

        <div className="form-group">
          <label className="form-label">Group name</label>
          <input
            type="text"
            className="form-input"
            value={groupName}
            onChange={(e) => setGroupName(e.target.value)}
            placeholder='e.g. "Section B" or "Q4 Choice Group"'
          />
        </div>

        <div className="form-group">
          <label className="form-label">Selection type</label>
          <select
            className="form-input"
            value={selectionType}
            onChange={(e) => setSelectionType(e.target.value as "compulsory" | "choose_n_of_m")}
          >
            <option value="compulsory">Compulsory (all selected questions graded)</option>
            <option value="choose_n_of_m">Choose N of M (first N attempted, ascending order)</option>
          </select>
        </div>

        {selectionType === "choose_n_of_m" && (
          <div className="form-group">
            <label className="form-label">N required</label>
            <input
              type="number"
              min={1}
              className="form-input"
              style={{ maxWidth: "120px" }}
              value={nRequired}
              onChange={(e) => setNRequired(Number(e.target.value))}
            />
          </div>
        )}

        <div className="form-group">
          <label className="form-label">Questions in this group</label>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            {questionBank.map((item) => {
              const isSelected = selectedQuestions.includes(item.question_number);
              const isTakenByOtherGroup = alreadyGrouped.has(item.question_number);
              return (
                <button
                  key={item.question_number}
                  type="button"
                  onClick={() => toggleQuestion(item.question_number)}
                  className={`badge ${isSelected ? "badge-indigo" : "badge-slate"}`}
                  style={{
                    cursor: "pointer",
                    border: isSelected ? "1px solid var(--color-brand-500)" : undefined,
                    opacity: isTakenByOtherGroup && !isSelected ? 0.5 : 1,
                  }}
                  title={isTakenByOtherGroup ? "Already assigned to another group" : undefined}
                >
                  {item.question_number}
                </button>
              );
            })}
          </div>
        </div>

        <button type="button" className="btn btn-primary" onClick={submitGroup} disabled={!groupName.trim() || selectedQuestions.length === 0}>
          <Plus size={16} /> Create Group
        </button>
      </div>

      <h3 style={{ fontFamily: "var(--font-display)" }}>Existing Groups</h3>
      {groups.length === 0 ? (
        <div className="empty-state">
          <h3>No groups defined yet</h3>
          <p>Ungrouped questions are graded as compulsory by default.</p>
        </div>
      ) : (
        <div className="card-grid">
          {groups.map((group) => (
            <div key={group.id} className="card" style={{ padding: "1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: "1rem" }}>{group.group_name}</div>
                  <span className={`badge ${group.selection_type === "compulsory" ? "badge-slate" : "badge-indigo"}`} style={{ marginTop: "0.4rem" }}>
                    {group.selection_type === "compulsory"
                      ? "Compulsory"
                      : `Choose ${group.n_required} of ${group.question_numbers.length}`}
                  </span>
                </div>
                <button type="button" className="btn btn-danger" style={{ padding: "0.35rem 0.6rem" }} onClick={() => removeGroup(group.id)}>
                  <Trash2 size={14} />
                </button>
              </div>
              <p style={{ fontSize: "0.85rem", color: "var(--color-slate-500)", marginTop: "0.75rem" }}>
                Questions: {group.question_numbers.join(", ")}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
