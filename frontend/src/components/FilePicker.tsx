import { CheckCircle2, FileText } from "lucide-react";

interface FilePickerProps {
  id: string;
  file: File | null;
  emptyLabel: string;
  emptyHint: string;
  readyHint: string;
  onChange: (file: File | null) => void;
  accept?: string;
}

export default function FilePicker({ id, file, emptyLabel, emptyHint, readyHint, onChange, accept = "application/pdf,.pdf" }: FilePickerProps) {
  return (
    <label className={`file-dropzone single-file ${file ? "has-file" : ""}`} htmlFor={id}>
      <span className={`file-icon ${file ? "is-ready" : ""}`} aria-hidden="true">
        {file ? <CheckCircle2 size={22} /> : <FileText size={22} />}
      </span>
      <span className="file-copy">
        <strong>{file?.name ?? emptyLabel}</strong>
        <small>{file ? `${(file.size / 1024).toFixed(1)} KB · ${readyHint}` : emptyHint}</small>
      </span>
      <span className="btn btn-secondary btn-sm" aria-hidden="true">{file ? "Replace file" : "Choose file"}</span>
      <input id={id} type="file" accept={accept} onChange={(event) => onChange(event.target.files?.[0] ?? null)} />
    </label>
  );
}
