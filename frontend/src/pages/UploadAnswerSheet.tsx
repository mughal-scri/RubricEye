import { AlertCircle, ArrowLeft, ShieldAlert, Upload, FileText } from "lucide-react";
import { FormEvent, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { uploadAnswerSheet } from "../api/client";

export default function UploadAnswerSheet() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [rollNumber, setRollNumber] = useState("");
  const [pdf, setPdf] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!projectId) return;
    if (!rollNumber.trim()) {
      setError("Please enter candidate roll number.");
      return;
    }
    if (!pdf) {
      setError("Please select candidate answer sheet PDF.");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const sheet = await uploadAnswerSheet(projectId, rollNumber, pdf);
      navigate(`/projects/${projectId}/answer-sheets/${sheet.id}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  };

  if (!projectId) return null;

  return (
    <div style={{ maxWidth: "680px", margin: "0 auto" }}>
      <div className="breadcrumb">
        <Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to Project</Link>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <h1>Upload Candidate Answer Sheet</h1>
          <p>Structural alignment and question region segmentation will be executed automatically.</p>
        </div>
      </div>

      {/* Privacy Defense Alert */}
      <div className="alert alert-warning" style={{ marginBottom: "1.5rem" }}>
        <ShieldAlert size={20} style={{ flexShrink: 0 }} />
        <div>
          <strong>Privacy Defense Active:</strong> Identity cover pages (containing bubble grids, candidate names, or roll numbers) are detected and rejected at upload to ensure zero candidate identity data reaches the evaluation engine.
        </div>
      </div>

      {error && (
        <div className="alert alert-error">
          <AlertCircle size={20} style={{ flexShrink: 0 }} />
          <div>
            <strong>Upload Failed:</strong> {error}
          </div>
        </div>
      )}

      <form onSubmit={onSubmit} className="card">
        <div className="form-group">
          <label className="form-label" htmlFor="roll-number">Candidate Roll Number</label>
          <input
            id="roll-number"
            className="form-input"
            placeholder="e.g. 109283"
            value={rollNumber}
            onChange={(e) => setRollNumber(e.target.value)}
            required
          />
        </div>

        <div className="form-group" style={{ marginTop: "1rem" }}>
          <label className="form-label">Answer Sheet PDF</label>
          <div className={`file-dropzone ${pdf ? "has-file" : ""}`}>
            <label style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "1rem" }}>
              <div style={{ padding: "10px", background: pdf ? "var(--color-emerald-100)" : "var(--color-slate-200)", borderRadius: "var(--radius-md)", color: pdf ? "var(--color-emerald-700)" : "var(--color-slate-600)" }}>
                <FileText size={22} />
              </div>
              <div style={{ flex: 1, textAlign: "left" }}>
                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                  Select Scanned Answer Sheet PDF
                </div>
                <div style={{ fontSize: "0.8rem", color: "var(--color-slate-500)" }}>
                  {pdf ? `Selected: ${pdf.name} (${(pdf.size / 1024).toFixed(1)} KB)` : "Upload scanned answer booklet PDF for processing"}
                </div>
              </div>
              <input
                type="file"
                accept="application/pdf"
                style={{ display: "none" }}
                onChange={(e) => setPdf(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "1rem", marginTop: "1.5rem" }}>
          <Link to={`/projects/${projectId}`} className="btn btn-secondary">Cancel</Link>
          <button type="submit" disabled={loading} className="btn btn-primary">
            {loading ? "Processing Alignment & Segmentation..." : (
              <>
                <Upload size={18} /> Upload & Segment Answer Sheet
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
