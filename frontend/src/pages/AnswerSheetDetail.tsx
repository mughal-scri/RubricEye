import { ArrowLeft, CheckCircle2, FileText, Layers, ZoomIn } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AnswerSheetDetail, fileUrl, getAnswerSheet } from "../api/client";

export default function AnswerSheetDetailPage() {
  const { projectId, sheetId } = useParams();
  const [sheet, setSheet] = useState<AnswerSheetDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedPreviewUrl, setSelectedPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId || !sheetId) return;
    getAnswerSheet(projectId, sheetId)
      .then((data) => {
        setSheet(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(String(err));
        setLoading(false);
      });
  }, [projectId, sheetId]);

  if (!projectId || !sheetId) return null;
  if (error) return <div className="alert alert-error">Error: {error}</div>;
  if (loading || !sheet) return <div style={{ textAlign: "center", padding: "3rem" }}>Loading segmentation details...</div>;

  return (
    <div>
      <div className="breadcrumb">
        <Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to Project</Link>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1>Candidate Roll #{sheet.roll_number}</h1>
            <span className="badge badge-success">
              <CheckCircle2 size={12} /> Alignment & Segmentation Complete
            </span>
          </div>
          <p>
            Processed {sheet.page_count} page(s) • Sheet ID: <code style={{ fontFamily: "var(--font-mono)" }}>{sheet.id}</code>
          </p>
        </div>
      </div>

      {/* Lightbox Preview Modal */}
      {selectedPreviewUrl && (
        <div
          onClick={() => setSelectedPreviewUrl(null)}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(15, 23, 42, 0.85)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 100,
            padding: "2rem",
            cursor: "pointer",
          }}
        >
          <div style={{ maxWidth: "90vw", maxHeight: "90vh", background: "white", borderRadius: "12px", overflow: "hidden", padding: "1rem" }}>
            <img src={fileUrl(selectedPreviewUrl)} alt="Enlarged Region Preview" style={{ maxWidth: "100%", maxHeight: "80vh", display: "block" }} />
            <div style={{ textAlign: "center", marginTop: "0.5rem", color: "var(--color-slate-600)", fontSize: "0.85rem" }}>
              Click anywhere to close lightbox
            </div>
          </div>
        </div>
      )}

      {/* Grid: Full Pages & Segmented Question Regions */}
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "1.5rem", alignItems: "start" }}>
        {/* Left Column: Aligned Booklet Pages */}
        <div className="card" style={{ padding: "1.25rem" }}>
          <h3 style={{ fontSize: "1rem", fontWeight: 700, fontFamily: "var(--font-display)", marginBottom: "1rem", display: "flex", alignItems: "center", gap: "8px" }}>
            <FileText size={18} /> Scanned Pages ({sheet.page_image_urls.length})
          </h3>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {sheet.page_image_urls.map((url, index) => (
              <div key={url} style={{ position: "relative" }}>
                <img
                  src={fileUrl(url)}
                  alt={`Page ${index + 1}`}
                  onClick={() => setSelectedPreviewUrl(url)}
                  className="region-crop-img"
                  style={{ cursor: "pointer" }}
                />
                <div style={{ position: "absolute", bottom: "8px", left: "8px", background: "rgba(15, 23, 42, 0.75)", color: "white", padding: "2px 8px", borderRadius: "4px", fontSize: "0.75rem", fontWeight: 600 }}>
                  Page {index + 1}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Question Region Segmentation */}
        <div>
          <div style={{ marginBottom: "1rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h3 style={{ fontSize: "1.2rem", fontWeight: 800, fontFamily: "var(--font-display)", color: "var(--color-slate-900)" }}>
              Question Region Segmentation Map
            </h3>
            <span className="badge badge-indigo">
              <Layers size={12} /> {Object.keys(sheet.question_region_map).length} Question Bounding Regions
            </span>
          </div>

          {Object.keys(sheet.question_region_map).length === 0 ? (
            <div className="empty-state">
              <p>No bounding regions were mapped to questions for this sheet.</p>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              {Object.entries(sheet.question_region_map).map(([questionKey, refs]) => {
                const previewUrls = sheet.region_preview_urls[questionKey] ?? [];

                return (
                  <div key={questionKey} className="region-preview-card">
                    <div className="region-preview-header">
                      <span style={{ fontSize: "1.05rem", color: "var(--color-brand-700)" }}>
                        Question {questionKey}
                      </span>
                      <span style={{ fontSize: "0.8rem", color: "var(--color-slate-500)", fontWeight: 500 }}>
                        {refs.length} region slice(s)
                      </span>
                    </div>

                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "1rem" }}>
                      {previewUrls.map((url, idx) => (
                        <div key={url} style={{ position: "relative" }}>
                          <img
                            src={fileUrl(url)}
                            alt={`Region ${questionKey} slice ${idx + 1}`}
                            onClick={() => setSelectedPreviewUrl(url)}
                            className="region-crop-img"
                            style={{ cursor: "pointer" }}
                          />
                          <div style={{ position: "absolute", top: "6px", right: "6px", background: "rgba(255, 255, 255, 0.9)", borderRadius: "50%", padding: "4px", boxShadow: "var(--shadow-sm)" }}>
                            <ZoomIn size={14} color="var(--color-slate-700)" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
