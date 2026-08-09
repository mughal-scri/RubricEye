import { ArrowLeft, CheckCircle2, Save, Lock, AlertCircle, Layers } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  confirmTemplateMap,
  fileUrl,
  getTemplateMap,
  TemplateMapResponse,
  TemplateRegionInput,
  updateTemplateMap,
} from "../api/client";
import RegionEditorTable from "../components/RegionEditorTable";
import RegionOverlay from "../components/RegionOverlay";

export default function TemplateMapReview() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [templateMap, setTemplateMap] = useState<TemplateMapResponse | null>(null);
  const [rows, setRows] = useState<TemplateRegionInput[]>([]);
  const [selectedPage, setSelectedPage] = useState(1);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    getTemplateMap(projectId)
      .then((data) => {
        setTemplateMap(data);
        const flattened: TemplateRegionInput[] = [];
        data.pages.forEach((page) => {
          page.regions.forEach((region) => {
            flattened.push({
              page_number: page.page_number,
              question_number: region.question_number,
              part_label: region.part_label,
              bbox: [region.bbox.x1, region.bbox.y1, region.bbox.x2, region.bbox.y2],
            });
          });
        });
        setRows(flattened);
        setSelectedPage(data.pages[0]?.page_number ?? 1);
      })
      .catch((err) => setError(String(err)));
  }, [projectId]);

  const currentPage = useMemo(
    () => templateMap?.pages.find((page) => page.page_number === selectedPage),
    [templateMap, selectedPage]
  );

  const currentPageRows = useMemo(
    () => rows.filter((row) => row.page_number === selectedPage),
    [rows, selectedPage]
  );

  const currentRegions = useMemo(
    () =>
      currentPageRows.map((row) => ({
        question_number: row.question_number,
        part_label: row.part_label,
        bbox: { x1: row.bbox[0], y1: row.bbox[1], x2: row.bbox[2], y2: row.bbox[3] },
      })),
    [currentPageRows]
  );

  const saveEdits = async () => {
    if (!projectId) return;
    setError("");
    setMessage("");
    setSaving(true);
    try {
      const updated = await updateTemplateMap(projectId, rows);
      setTemplateMap(updated);
      setMessage("Template map saved successfully.");
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const confirm = async () => {
    if (!projectId) return;
    setError("");
    setMessage("");
    setSaving(true);
    try {
      await updateTemplateMap(projectId, rows);
      const updated = await confirmTemplateMap(projectId);
      setTemplateMap(updated);
      setMessage("Template map confirmed and locked.");
      navigate(`/projects/${projectId}`);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  if (!projectId) return null;
  if (error) return <div className="alert alert-error">Error: {error}</div>;
  if (!templateMap || !currentPage) return <div style={{ textAlign: "center", padding: "3rem" }}>Loading template map...</div>;

  return (
    <div>
      <div className="breadcrumb">
        <Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to Project</Link>
      </div>

      <div className="page-header">
        <div className="page-title-group">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1>Template Map Review & Numeric Edit</h1>
            <span className={`badge ${templateMap.confirmed ? "badge-success" : "badge-warning"}`}>
              {templateMap.confirmed ? (
                <>
                  <CheckCircle2 size={12} /> Confirmed & Locked
                </>
              ) : (
                <>
                  <Layers size={12} /> Status: {templateMap.status}
                </>
              )}
            </span>
          </div>
          <p>Verify detected question bounding boxes on the blank booklet. Modify coordinates if needed.</p>
        </div>

        {!templateMap.confirmed && (
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button type="button" onClick={saveEdits} disabled={saving} className="btn btn-secondary">
              <Save size={16} /> Save Draft Edits
            </button>
            <button type="button" onClick={confirm} disabled={saving} className="btn btn-success">
              <Lock size={16} /> Confirm & Lock Template Map
            </button>
          </div>
        )}
      </div>

      {message && (
        <div className="alert alert-success">
          <CheckCircle2 size={18} style={{ flexShrink: 0 }} />
          <span>{message}</span>
        </div>
      )}

      {/* Page Tabs */}
      <div className="tab-pills">
        {templateMap.pages.map((page) => (
          <button
            key={page.page_number}
            type="button"
            className={`tab-pill ${page.page_number === selectedPage ? "active" : ""}`}
            onClick={() => {
              setSelectedPage(page.page_number);
              setHoveredIndex(null);
            }}
          >
            Page {page.page_number}
          </button>
        ))}
      </div>

      {/* Split Review Layout */}
      <div className="template-review-container">
        {/* Left Panel: Overlay Canvas */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--color-slate-600)" }}>
            Booklet Page {selectedPage} Preview (SVG BBox Overlay)
          </div>
          <RegionOverlay
            imageUrl={fileUrl(currentPage.page_image_url)}
            regions={currentRegions}
            hoveredIndex={hoveredIndex}
            onSelectRegion={(idx) => setHoveredIndex(idx)}
          />
        </div>

        {/* Right Panel: Numeric Region Table */}
        <div>
          <RegionEditorTable
            rows={currentPageRows}
            hoveredIndex={hoveredIndex}
            onHoverRow={(idx) => setHoveredIndex(idx)}
            onChange={(pageRows) => {
              const otherRows = rows.filter((row) => row.page_number !== selectedPage);
              setRows([...otherRows, ...pageRows]);
            }}
          />
        </div>
      </div>
    </div>
  );
}
