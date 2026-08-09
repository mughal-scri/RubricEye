import { Plus, Trash2 } from "lucide-react";
import { TemplateRegionInput } from "../api/client";

interface Props {
  rows: TemplateRegionInput[];
  onChange: (rows: TemplateRegionInput[]) => void;
  hoveredIndex?: number | null;
  onHoverRow?: (index: number | null) => void;
}

export default function RegionEditorTable({ rows, onChange, hoveredIndex, onHoverRow }: Props) {
  const updateRow = (index: number, field: keyof TemplateRegionInput, value: string | number) => {
    const next = [...rows];
    if (field === "bbox") return;
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

  const addRow = () => {
    onChange([
      ...rows,
      {
        page_number: rows[0]?.page_number ?? 1,
        question_number: String(rows.length + 1),
        part_label: "a",
        bbox: [50, 50, 450, 200],
      },
    ]);
  };

  const removeRow = (index: number) => {
    onChange(rows.filter((_, i) => i !== index));
  };

  return (
    <div className="card" style={{ padding: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h3 style={{ fontSize: "1rem", fontWeight: 700, fontFamily: "var(--font-display)" }}>
          Region Coordinates ({rows.length})
        </h3>
        <button type="button" onClick={addRow} className="btn btn-secondary" style={{ padding: "0.4rem 0.8rem", fontSize: "0.8rem" }}>
          <Plus size={14} /> Add Region
        </button>
      </div>

      <div className="table-container">
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: "50px" }}>Page</th>
              <th style={{ width: "65px" }}>Q #</th>
              <th style={{ width: "60px" }}>Part</th>
              <th style={{ width: "70px" }}>X1</th>
              <th style={{ width: "70px" }}>Y1</th>
              <th style={{ width: "70px" }}>X2</th>
              <th style={{ width: "70px" }}>Y2</th>
              <th style={{ width: "40px" }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: "center", color: "var(--color-slate-500)", padding: "1.5rem" }}>
                  No region bboxes defined for this page yet.
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr
                  key={index}
                  className={hoveredIndex === index ? "highlighted" : ""}
                  onMouseEnter={() => onHoverRow?.(index)}
                  onMouseLeave={() => onHoverRow?.(null)}
                >
                  <td>
                    <input
                      type="number"
                      className="form-input"
                      style={{ padding: "4px 6px", fontSize: "0.85rem", textAlign: "center" }}
                      value={row.page_number}
                      onChange={(e) => updateRow(index, "page_number", Number(e.target.value))}
                    />
                  </td>
                  <td>
                    <input
                      className="form-input"
                      style={{ padding: "4px 6px", fontSize: "0.85rem", fontWeight: 600 }}
                      value={row.question_number}
                      placeholder="1"
                      onChange={(e) => updateRow(index, "question_number", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="form-input"
                      style={{ padding: "4px 6px", fontSize: "0.85rem" }}
                      value={row.part_label}
                      placeholder="a"
                      onChange={(e) => updateRow(index, "part_label", e.target.value)}
                    />
                  </td>
                  {row.bbox.map((value, coordIndex) => (
                    <td key={coordIndex}>
                      <input
                        type="number"
                        className="form-input"
                        style={{ padding: "4px 6px", fontSize: "0.8rem", fontFamily: "var(--font-mono)" }}
                        value={value}
                        onChange={(e) => updateBBox(index, coordIndex, e.target.value)}
                      />
                    </td>
                  ))}
                  <td>
                    <button
                      type="button"
                      onClick={() => removeRow(index)}
                      className="btn btn-danger"
                      style={{ padding: "4px 8px" }}
                      title="Remove region"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
