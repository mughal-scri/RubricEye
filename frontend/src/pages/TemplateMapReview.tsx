import { AlertTriangle, ArrowLeft, CheckCircle2, FileText, Layers, Lock, RotateCcw, Unlock } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { confirmTemplateMap, fileUrl, getTemplateMap, TemplateMapResponse, TemplateRegion, TemplateRegionInput, unlockTemplateMap, updateTemplateMap } from "../api/client";
import RegionEditorTable from "../components/RegionEditorTable";
import RegionOverlay from "../components/RegionOverlay";
import { errorMessage } from "../ui";

function rowsFromMap(map: TemplateMapResponse): TemplateRegionInput[] {
  return map.pages.flatMap((page) => page.regions.map((region) => ({
    page_number: page.page_number,
    question_number: region.question_number ?? "",
    part_label: region.part_label ?? "",
    bbox: [region.bbox.x1, region.bbox.y1, region.bbox.x2, region.bbox.y2],
  })));
}

function regionFromRow(row: TemplateRegionInput): TemplateRegion {
  const [x1, y1, x2, y2] = row.bbox;
  return { question_number: row.question_number, part_label: row.part_label, bbox: { x1, y1, x2, y2 } };
}

export default function TemplateMapReview() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [templateMap, setTemplateMap] = useState<TemplateMapResponse | null>(null);
  const [rows, setRows] = useState<TemplateRegionInput[]>([]);
  const [selectedPageNumber, setSelectedPageNumber] = useState<number | null>(null);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const load = async () => {
    if (!projectId) return;
    setLoading(true);
    setError("");
    try {
      const nextMap = await getTemplateMap(projectId);
      const nextRows = rowsFromMap(nextMap);
      setTemplateMap(nextMap);
      setRows(nextRows);
      setSelectedPageNumber((current) => current ?? nextMap.pages[0]?.page_number ?? null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [projectId]);

  const pagesWithRegions = templateMap?.pages.filter((page) => rows.some((row) => row.page_number === page.page_number)) ?? [];
  const selectedPage = templateMap?.pages.find((page) => page.page_number === selectedPageNumber) ?? templateMap?.pages[0] ?? null;
  const selectedRows = rows.filter((row) => row.page_number === selectedPage?.page_number);
  const selectedRegions = selectedRows.map(regionFromRow);
  const invalid = rows.filter((row) => !row.question_number.trim() || row.bbox.length !== 4 || row.bbox[2] <= row.bbox[0] || row.bbox[3] <= row.bbox[1]);

  const updateSelectedRows = (nextRows: TemplateRegionInput[]) => {
    if (!selectedPage) return;
    let cursor = 0;
    const merged = rows.flatMap((row) => {
      if (row.page_number !== selectedPage.page_number) return [row];
      const replacement = nextRows[cursor++];
      return replacement ? [replacement] : [];
    });
    setRows([...merged, ...nextRows.slice(cursor)]);
  };

  const confirm = async () => {
    if (!projectId || !templateMap) return;
    if (!rows.length || invalid.length) {
      setError("Resolve every unmapped or invalid region before confirming the template map.");
      return;
    }
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const updated = await updateTemplateMap(projectId, rows);
      setTemplateMap(updated);
      setRows(rowsFromMap(updated));
      const confirmed = await confirmTemplateMap(projectId);
      setTemplateMap(confirmed);
      setRows(rowsFromMap(confirmed));
      navigate(`/projects/${projectId}/question-bank`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const unlock = async () => {
    if (!projectId) return;
    setSaving(true);
    setError("");
    try {
      const unlocked = await unlockTemplateMap(projectId);
      setTemplateMap(unlocked);
      setRows(rowsFromMap(unlocked));
      setMessage("Booklet reading unlocked for diagnostic correction.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const rowCountByPage = useMemo(() => new Map(templateMap?.pages.map((page) => [page.page_number, rows.filter((row) => row.page_number === page.page_number).length]) ?? []), [templateMap, rows]);

  if (!projectId) return null;
  if (loading) return <div className="loading-state" role="status">Loading booklet reading…</div>;
  if (error && !templateMap) return <div className="empty-state"><h3>Booklet reading could not be loaded</h3><p>{error}</p><button type="button" className="btn btn-primary" onClick={() => void load()}><RotateCcw size={15} /> Retry</button></div>;
  if (!templateMap) return null;

  return <div className="template-summary-page">
    <div className="breadcrumb"><Link to={`/projects/${projectId}`}><ArrowLeft size={14} /> Back to project</Link><span>/</span><span>Booklet reading</span></div>
    <div className="page-header"><div className="page-title-group"><div className="eyebrow">Step 1 · Booklet understanding</div><div className="title-with-badges"><h1>Booklet reading</h1><span className={`badge ${templateMap.confirmed ? "badge-success" : "badge-warning"}`}>{templateMap.confirmed ? <><CheckCircle2 size={12} /> Confirmed</> : <><Layers size={12} /> Ready for review</>}</span></div><p>Inspect the page image and correct labels or regions before the map is locked for grading.</p></div><div className="button-row">{templateMap.confirmed ? <button type="button" className="btn btn-secondary" onClick={() => void unlock()} disabled={saving}><Unlock size={16} /> Unlock diagnostics</button> : <button type="button" className="btn btn-success" onClick={() => void confirm()} disabled={saving || rows.length === 0 || invalid.length > 0}><Lock size={16} /> Confirm and continue</button>}</div></div>
    {error && <div className="alert alert-error" role="alert"><AlertTriangle size={17} /><span>{error}</span></div>}
    {message && <div className="alert alert-success" role="status"><CheckCircle2 size={17} /><span>{message}</span></div>}
    <div className="reading-hero"><div className="reading-hero-icon"><Layers size={24} /></div><div><strong>{rows.length} answer region{rows.length === 1 ? "" : "s"} understood across {pagesWithRegions.length} page{pagesWithRegions.length === 1 ? "" : "s"}.</strong><p>{templateMap.confirmed ? "This map is confirmed. Unlock diagnostics to correct it only before any answer sheets are uploaded." : "Select a page, inspect the image overlays, and correct any label or boundary before confirming."}</p></div></div>
    {templateMap.pages.length === 0 ? <div className="empty-state"><FileText size={26} /><h3>No booklet pages were understood</h3><p>Retry preparation or check that the blank booklet is readable before continuing.</p></div> : <>
      <div className="tab-pills" role="tablist" aria-label="Booklet pages">{templateMap.pages.map((page) => <button type="button" role="tab" aria-selected={selectedPage?.page_number === page.page_number} className={`tab-pill ${selectedPage?.page_number === page.page_number ? "active" : ""}`} key={page.page_number} onClick={() => { setSelectedPageNumber(page.page_number); setHoveredIndex(null); }}>{`Page ${page.page_number} · ${rowCountByPage.get(page.page_number) ?? 0} regions`}</button>)}</div>
      {selectedPage && <div className="template-review-container"><div className="card"><div className="section-heading compact"><div><h3>Page {selectedPage.page_number} image</h3><p>Click a highlighted region or hover a table row to cross-check the mapping.</p></div></div><RegionOverlay imageUrl={fileUrl(selectedPage.page_image_url)} regions={selectedRegions} hoveredIndex={hoveredIndex} onSelectRegion={setHoveredIndex} /></div><RegionEditorTable rows={selectedRows} onChange={updateSelectedRows} hoveredIndex={hoveredIndex} onHoverRow={setHoveredIndex} readOnly={templateMap.confirmed} /></div>}
    </>}
    <details className="diagnostic-details"><summary>Show technical details</summary><p>Coordinates are editable only before confirmation. The server validates labels, duplicate identities, page bounds, and coordinates before locking the map.</p><span>{templateMap.pages.length} source pages · {rows.length} mapped regions · {invalid.length} unresolved regions</span></details>
  </div>;
}
