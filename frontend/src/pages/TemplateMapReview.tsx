import { AlertTriangle, ArrowLeft, CheckCircle2, Layers, Lock, Save, Unlock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { confirmTemplateMap, fileUrl, getTemplateMap, TemplateMapResponse, TemplateRegionInput, unlockTemplateMap, updateTemplateMap } from "../api/client";
import { errorMessage } from "../ui";
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
    getTemplateMap(projectId).then((data) => {
      setTemplateMap(data);
      const flattened: TemplateRegionInput[] = [];
      data.pages.forEach((page) => page.regions.forEach((region) => flattened.push({ page_number: page.page_number, question_number: region.question_number ?? "", part_label: region.part_label ?? "", bbox: [region.bbox.x1, region.bbox.y1, region.bbox.x2, region.bbox.y2] })));
      setRows(flattened);
      setSelectedPage(data.pages[0]?.page_number ?? 1);
    }).catch((err) => setError(errorMessage(err)));
  }, [projectId]);

  const currentPage = useMemo(() => templateMap?.pages.find((page) => page.page_number === selectedPage), [templateMap, selectedPage]);
  const currentPageRows = useMemo(() => rows.filter((row) => row.page_number === selectedPage), [rows, selectedPage]);
  const currentRegions = useMemo(() => currentPageRows.map((row) => ({ question_number: row.question_number, part_label: row.part_label, bbox: { x1: row.bbox[0] ?? 0, y1: row.bbox[1] ?? 0, x2: row.bbox[2] ?? 0, y2: row.bbox[3] ?? 0 } })), [currentPageRows]);
  const invalidRows = rows.filter((row) => !row.question_number.trim() || row.bbox.length !== 4 || row.bbox.some((value) => !Number.isFinite(value)));
  const mappedCount = rows.filter((row) => row.question_number.trim()).length;

  const saveEdits = async () => {
    if (!projectId) return;
    setError(""); setMessage(""); setSaving(true);
    try { const updated = await updateTemplateMap(projectId, rows); setTemplateMap(updated); setMessage("Template map draft saved."); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  const confirm = async () => {
    if (!projectId) return;
    if (rows.length === 0) { setError("No answer regions were detected. Review the blank booklet or retry preparation before locking the template map."); return; }
    if (invalidRows.length > 0) { setError("Resolve or remove every unmapped or invalid region before locking the template map."); return; }
    setError(""); setMessage(""); setSaving(true);
    try { await updateTemplateMap(projectId, rows); const updated = await confirmTemplateMap(projectId); setTemplateMap(updated); setMessage("Template map confirmed and locked."); navigate(`/projects/${projectId}`); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  const unlock = async () => {
    if (!projectId) return;
    setError(""); setMessage(""); setSaving(true);
    try { const updated = await unlockTemplateMap(projectId); setTemplateMap(updated); setMessage("Template map unlocked for re-editing."); } catch (err) { setError(errorMessage(err)); } finally { setSaving(false); }
  };

  if (!projectId) return null;
  if (!templateMap) return error ? <div className="empty-state"><h3>Template map could not be loaded</h3><p>{error}</p></div> : <div className="loading-state" role="status">Loading template map…</div>;
  if (!currentPage) return <div className="empty-state"><h3>No booklet pages available</h3><p>The project does not contain a usable template-map page yet.</p><Link to={`/projects/${projectId}`} className="btn btn-secondary">Back to project</Link></div>;

  return <div>
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Template map</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Assessment setup</div><div className="title-with-badges"><h1>Template map</h1><span className={`badge ${templateMap.confirmed ? "badge-success" : "badge-warning"}`}>{templateMap.confirmed ? <><CheckCircle2 size={12} /> Confirmed and locked</> : <><Layers size={12} /> {templateMap.status || "Needs review"}</>}</span></div><p>Review the detected answer regions before using this booklet structure.</p></div>{!templateMap.confirmed ? <div className="button-row"><button type="button" className="btn btn-secondary" onClick={saveEdits} disabled={saving}><Save size={16} /> Save draft</button><button type="button" className="btn btn-success" onClick={confirm} disabled={saving || rows.length === 0 || invalidRows.length > 0}><Lock size={16} /> Confirm and lock</button></div> : <button type="button" className="btn btn-secondary" onClick={unlock} disabled={saving}><Unlock size={16} /> Unlock to edit</button>}</div>
    {error && <div className="alert alert-error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>}
    {message && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>{message}</span></div>}
    <div className={`readiness-banner ${invalidRows.length ? "is-warning" : "is-ready"}`}><div><strong>{mappedCount} of {rows.length} detected regions mapped</strong><p>{invalidRows.length ? `${invalidRows.length} region${invalidRows.length === 1 ? "" : "s"} need a label or valid coordinates before locking.` : "Review the highlighted page and confirm the map when every region is defensible."}</p></div><span className="badge badge-slate">Page {selectedPage} · {currentPageRows.length} region{currentPageRows.length === 1 ? "" : "s"}</span></div>
    <div className="tab-pills" role="tablist" aria-label="Template pages">{templateMap.pages.map((page) => <button key={page.page_number} type="button" role="tab" aria-selected={page.page_number === selectedPage} className={`tab-pill ${page.page_number === selectedPage ? "active" : ""}`} onClick={() => { setSelectedPage(page.page_number); setHoveredIndex(null); }}>Page {page.page_number}<small>{page.regions.length}</small></button>)}</div>
    <div className="template-review-container"><div className="overlay-panel"><div className="panel-heading"><div><h3>Page {selectedPage} preview</h3><p>Click a region to match it with the editor.</p></div></div><RegionOverlay imageUrl={fileUrl(currentPage.page_image_url)} regions={currentRegions} hoveredIndex={hoveredIndex} onSelectRegion={setHoveredIndex} /></div><div><RegionEditorTable rows={currentPageRows} hoveredIndex={hoveredIndex} onHoverRow={setHoveredIndex} onChange={(pageRows) => { const otherRows = rows.filter((row) => row.page_number !== selectedPage); setRows([...otherRows, ...pageRows]); }} /></div></div>
    <div className="diagnostic-disclosure"><strong>Why this matters</strong><p>This map will be reused to prepare every answer sheet in the project. Unknown labels remain unresolved rather than being assigned placeholder question numbers.</p></div>
  </div>;
}
