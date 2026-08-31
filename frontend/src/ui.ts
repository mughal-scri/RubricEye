export type StatusTone = "slate" | "indigo" | "success" | "warning" | "danger";

export function errorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error ?? "");
  const normalized = raw.replace(/\x1b\[[0-9;]*m/g, "").trim();
  if (!normalized) return "This action could not be completed. Your existing data was not changed.";
  if (/traceback|file "[^\"]+", line \d+|exception:/i.test(normalized)) {
    return "The local service encountered an unexpected error. Your existing data was not changed.";
  }
  return normalized.replace(/^Error:\s*/i, "").replace(/^\{.*?detail\s*[:=]\s*[\"']?/i, "").replace(/[\"'}]+$/, "").trim();
}

export function gradingStatusLabel(status: string): { label: string; tone: StatusTone } {
  switch (status) {
    case "in_progress":
      return { label: "Grading in progress", tone: "warning" };
    case "complete":
      return { label: "Finalized after examiner review", tone: "success" };
    case "review_required":
      return { label: "AI grading complete · review required", tone: "indigo" };
    case "failed":
      return { label: "Grading failed · retry available", tone: "danger" };
    case "pending":
    case "not_graded":
      return { label: "Not graded", tone: "slate" };
    default:
      return { label: status.replace(/_/g, " ") || "Status unavailable", tone: "slate" };
  }
}

export function choiceStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    graded: "Included in scoring",
    skipped_blank: "Blank · skipped by rule",
    skipped_beyond_n: "Beyond N · excluded",
    flagged_ambiguous: "Ambiguous · review required",
    no_regions: "No matching region",
  };
  return labels[status] ?? (status.replace(/_/g, " ") || "Status unavailable");
}

export function statusClass(tone: StatusTone): string {
  return `badge badge-${tone}`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function reviewStateBadge(state: string): { label: string; tone: StatusTone } {
  switch (state) {
    case "confirmed":
      return { label: "Confirmed", tone: "success" };
    case "overridden":
      return { label: "Score overridden", tone: "indigo" };
    case "ambiguous":
      return { label: "Ambiguous — needs attention", tone: "danger" };
    case "closed":
      return { label: "Closed", tone: "slate" };
    case "failed":
      return { label: "Failed", tone: "danger" };
    case "ai_draft":
    default:
      return { label: "AI draft", tone: "warning" };
  }
}
