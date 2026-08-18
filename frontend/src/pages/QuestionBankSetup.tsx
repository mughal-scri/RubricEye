import { AlertTriangle, ArrowLeft, CheckCircle2, Lock, Unlock, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  addQuestionBankItem,
  confirmQuestionBank,
  deleteQuestionBankItem,
  listQuestionBank,
  QuestionBankItem,
  unlockQuestionBank,
  updateQuestionBankItem,
} from "../api/client";

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

  const load = () => {
    if (!projectId) return;
    setLoading(true);
    listQuestionBank(projectId)
      .then((data) => {
        setItems(data.items);
        setConfirmed(data.confirmed);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  };

  useEffect(load, [projectId]);

  const updateLocalField = (questionNumber: string, field: "marks_possible" | "key_points", value: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.question_number === questionNumber
          ? { ...item, [field]: field === "marks_possible" ? (value === "" ? null : Number(value)) : value }
          : item
      )
    );
  };

  const saveRow = async (item: QuestionBankItem) => {
    if (!projectId) return;
    setError("");
    try {
      await updateQuestionBankItem(projectId, item.question_number, {
        marks_possible: item.marks_possible,
        key_points: item.key_points,
      });
    } catch (err) {
      setError(String(err));
    }
  };

  const removeRow = async (questionNumber: string) => {
    if (!projectId) return;
    setError("");
    try {
      await deleteQuestionBankItem(projectId, questionNumber);
      setItems((prev) => prev.filter((item) => item.question_number !== questionNumber));
    } catch (err) {
      setError(String(err));
    }
  };

  const addRow = async () => {
    if (!projectId || !newQuestionNumber.trim()) return;
    setError("");
    try {
      const created = await addQuestionBankItem(projectId, newQuestionNumber.trim(), null, null);
      setItems((prev) => [...prev, created]);
      setNewQuestionNumber("");
    } catch (err) {
      setError(String(err));
    }
  };

  const confirmAndLock = async () => {
    if (!projectId) return;
    setError("");
    setMessage("");
    setSaving(true);
    try {
      // Persist any unsaved row edits before locking.
      await Promise.all(items.map((item) => saveRow(item)));
      const result = await confirmQuestionBank(projectId);
      setConfirmed(true);
      setWarning(result.marks_mismatch_warning);
      if (result.marks_mismatch_warning) {
        setMessage("Question bank locked, but a marks mismatch was detected -- see warning below.");
      } else {
        setMessage("Question bank confirmed and locked.");
        navigate(`/projects/${projectId}`);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const unlock = async () => {
    if (!projectId) return;
    setError("");
    setMessage("");
    setSaving(true);
    try {
      const data = await unlockQuestionBank(projectId);
      setConfirmed(data.confirmed);
      setWarning(null);
      setMessage("Question bank unlocked for re-editing.");
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  if (!projectId) return null;
  if (loading) return <div style={{ textAlign: "center", padding: "3rem" }}>Loading question bank...</div>;

  const totalMarks = items.reduce((sum, item) => sum + (item.marks_possible ?? 0), 0);

  return (
    <div>
      <div className="breadcrumb">
        <Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to Project</Link>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1>Question Bank Setup</h1>
            <span className={`badge ${confirmed ? "badge-success" : "badge-warning"}`}>
              {confirmed ? (
                <>
                  <CheckCircle2 size={12} /> Confirmed & Locked
                </>
              ) : (
                "Draft -- review before locking"
              )}
            </span>
          </div>
          <p>
            Auto-extracted from the rubric PDF. Correct marks and key points below, then confirm to
            enable grading. Total: <strong>{totalMarks} marks</strong> across {items.length} question(s).
          </p>
        </div>

        {!confirmed ? (
          <button type="button" onClick={confirmAndLock} disabled={saving || items.length === 0} className="btn btn-success">
            <Lock size={16} /> Confirm & Lock Question Bank
          </button>
        ) : (
          <button type="button" onClick={unlock} disabled={saving} className="btn btn-secondary">
            <Unlock size={16} /> Unlock for Re-editing
          </button>
        )}
      </div>

      {error && <div className="alert alert-error"><AlertTriangle size={18} /> <span>{error}</span></div>}
      {message && !warning && (
        <div className="alert alert-success"><CheckCircle2 size={18} /> <span>{message}</span></div>
      )}
      {warning && (
        <div className="alert alert-warning">
          <AlertTriangle size={18} style={{ flexShrink: 0 }} />
          <span>{warning}</span>
        </div>
      )}

      {items.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <AlertTriangle size={28} />
          </div>
          <h3>No questions extracted</h3>
          <p>
            The rubric may be a scanned PDF with no extractable text layer. Add questions manually
            below before confirming.
          </p>
        </div>
      ) : (
        <div className="table-container">
          <table className="table">
            <thead>
              <tr>
                <th>Question #</th>
                <th style={{ width: "120px" }}>Marks</th>
                <th>Key Points / Rubric Text</th>
                {!confirmed && <th style={{ textAlign: "right" }}>Remove</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.question_number}>
                  <td style={{ fontWeight: 700 }}>{item.question_number}</td>
                  <td>
                    <input
                      type="number"
                      className="form-input"
                      value={item.marks_possible ?? ""}
                      disabled={confirmed}
                      onChange={(e) => updateLocalField(item.question_number, "marks_possible", e.target.value)}
                      onBlur={() => saveRow(item)}
                    />
                  </td>
                  <td>
                    <textarea
                      className="form-input"
                      rows={2}
                      value={item.key_points ?? ""}
                      disabled={confirmed}
                      onChange={(e) => updateLocalField(item.question_number, "key_points", e.target.value)}
                      onBlur={() => saveRow(item)}
                    />
                  </td>
                  {!confirmed && (
                    <td style={{ textAlign: "right" }}>
                      <button type="button" className="btn btn-danger" style={{ padding: "0.35rem 0.6rem" }} onClick={() => removeRow(item.question_number)}>
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!confirmed && (
        <div className="card" style={{ marginTop: "1.25rem", padding: "1.25rem", display: "flex", gap: "0.75rem", alignItems: "flex-end" }}>
          <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
            <label className="form-label">Add question manually (e.g. "5" or "5a")</label>
            <input
              type="text"
              className="form-input"
              value={newQuestionNumber}
              onChange={(e) => setNewQuestionNumber(e.target.value)}
              placeholder="Question number"
            />
          </div>
          <button type="button" className="btn btn-secondary" onClick={addRow}>
            <Plus size={16} /> Add
          </button>
        </div>
      )}
    </div>
  );
}
