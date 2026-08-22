import { AlertTriangle, Plus, Trash2 } from "lucide-react";
import { TemplateRegionInput } from "../api/client";

interface Props {
  rows: TemplateRegionInput[];
  onChange: (rows: TemplateRegionInput[]) => void;
  hoveredIndex?: number | null;
  onHoverRow?: (index: number | null) => void;
}

export default function RegionEditorTable({ rows, onChange, hoveredIndex, onHoverRow }: Props) {
  const updateRow = (index: number, field: keyof TemplateRegionInput, value: string | number) => {
    if (field === "bbox") return;
    const next = [...rows];
    next[index] = { ...next[index], [field]: value };
    onChange(next);
  };

  const updateBBox = (index: number, coordIndex: number, value: string) => {
    const next = [...rows];
    const bbox = [...next[index].bbox];
    bbox[coordIndex] = Math.max(0, Number(value));
    next[index] = { ...next[index], bbox };
    onChange(next);
  };

  const addRow = () => onChange([...rows, { page_number: rows[0]?.page_number ?? 1, question_number: "", part_label: "", bbox: [0, 0, 0, 0] }]);
  const removeRow = (index: number) => onChange(rows.filter((_, rowIndex) => rowIndex !== index));

  return <div className="card region-editor-card">
    <div className="section-heading compact"><div><h3>Detected regions</h3><p>{rows.length} region{rows.length === 1 ? "" : "s"} on this page · edit coordinates only when needed.</p></div><button type="button" onClick={addRow} className="btn btn-secondary btn-sm"><Plus size={14} /> Add region</button></div>
    <div className="table-container"><table className="table compact-table"><thead><tr><th>Page</th><th>Question</th><th>Part</th><th>X1</th><th>Y1</th><th>X2</th><th>Y2</th><th aria-label="Actions" /></tr></thead><tbody>{rows.length === 0 ? <tr><td colSpan={8} className="table-empty">No regions defined for this page.</td></tr> : rows.map((row, index) => { const unresolved = !row.question_number.trim() || row.bbox[2] <= row.bbox[0] || row.bbox[3] <= row.bbox[1]; return <tr key={`${row.page_number}-${index}`} className={`${hoveredIndex === index ? "highlighted" : ""} ${unresolved ? "row-warning" : ""}`} onMouseEnter={() => onHoverRow?.(index)} onMouseLeave={() => onHoverRow?.(null)}><td><input type="number" min={1} className="form-input compact-input" value={row.page_number} onChange={(event) => updateRow(index, "page_number", Number(event.target.value))} aria-label={`Page for region ${index + 1}`} /></td><td><input className={`form-input compact-input ${!row.question_number.trim() ? "input-warning" : ""}`} value={row.question_number} placeholder="Unmapped" onChange={(event) => updateRow(index, "question_number", event.target.value)} aria-label={`Question number for region ${index + 1}`} /></td><td><input className="form-input compact-input" value={row.part_label} placeholder="—" onChange={(event) => updateRow(index, "part_label", event.target.value)} aria-label={`Part for region ${index + 1}`} /></td>{row.bbox.map((value, coordIndex) => <td key={coordIndex}><input type="number" min={0} className="form-input compact-input mono-input" value={value} onChange={(event) => updateBBox(index, coordIndex, event.target.value)} aria-label={`Coordinate ${coordIndex + 1} for region ${index + 1}`} /></td>)}<td><button type="button" onClick={() => removeRow(index)} className="icon-button danger" title="Remove region" aria-label={`Remove region ${index + 1}`}><Trash2 size={14} /></button></td></tr>; })}</tbody></table></div>
    {rows.some((row) => !row.question_number.trim()) && <div className="table-note"><AlertTriangle size={14} /> Unmapped regions cannot be confirmed until a question is assigned or the region is removed.</div>}
  </div>;
}
