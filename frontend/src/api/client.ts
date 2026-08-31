export const API_BASE = "http://127.0.0.1:8765";

// Phase 2: local API token — fetched from /config on first request and
// included in all subsequent requests as a Bearer token.
let _apiToken: string | null = null;

async function ensureToken(): Promise<string> {
  if (_apiToken) return _apiToken;
  const res = await fetch(`${API_BASE}/config`);
  if (!res.ok) throw new Error("Failed to fetch API config.");
  const cfg = await res.json();
  const token: string = cfg.api_token || "";
  _apiToken = token;
  return token;
}

/** Override the API token (used by tests or pre-configured environments). */
export function setApiToken(token: string): void {
  _apiToken = token;
}

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  deleted_at?: string | null;
  template_map_confirmed: boolean;
  template_map_status: string;
  rubric_locked: boolean;
  question_bank_confirmed: boolean;
}

export interface ProjectDetail extends ProjectSummary {
  rubric_file_path: string;
  question_paper_file_path: string;
  blank_booklet_file_path: string;
  question_bank_marks_warning: string | null;
  question_bank_raw_total?: number | null;
  question_bank_stated_total?: number | null;
  question_bank_effective_total?: number | null;
  question_bank_structure_status?: string;
  rubric_source_mode?: "uploaded" | "text" | "studio";
  rubric_studio_status?: string;
  rubric_download_url?: string | null;
  template_map_error?: string | null;
}

export interface BBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface TemplateRegion {
  question_number: string;
  part_label: string;
  bbox: BBox;
}

export interface TemplateMapPage {
  page_number: number;
  page_image_url: string;
  regions: TemplateRegion[];
}

export interface TemplateMapResponse {
  project_id: string;
  confirmed: boolean;
  status: string;
  pages: TemplateMapPage[];
}

export interface TemplateRegionInput {
  page_number: number;
  question_number: string;
  part_label: string;
  bbox: number[];
}

export interface AnswerSheetSummary {
  id: string;
  project_id: string;
  roll_number: string;
  uploaded_at: string;
  deleted_at?: string | null;
  page_count: number;
  grading_status: string;
  report_ready?: boolean;
  report_download_url?: string | null;
  completed_at?: string | null;
}

export interface RegionRef {
  page_index: number;
  bbox: number[];
  nominal_bbox?: number[] | null;
  overflow_detected?: boolean;
  alignment_method?: string;
  alignment_confidence?: string;
  alignment_uncertain?: boolean;
  page_correspondence_uncertain?: boolean;
}

export interface AnswerSheetDetail extends AnswerSheetSummary {
  page_image_urls: string[];
  question_region_map: Record<string, RegionRef[]>;
  region_preview_urls: Record<string, string[]>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await ensureToken();
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new Error("RubricEye cannot reach the local processing service. Your project files remain on this device.");
  }
  if (!response.ok) {
    const text = await response.text();
    let detail = text || response.statusText;
    try {
      const parsed = JSON.parse(text);
      detail = parsed.detail ?? parsed.message ?? detail;
    } catch {
      // Keep the plain response when it is not JSON.
    }
    if (/traceback|file \".*\", line \d+|exception:/i.test(detail)) {
      detail = "The local service encountered an unexpected error. Your existing data was not changed.";
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function listProjects(): Promise<ProjectSummary[]> {
  return request("/projects");
}

export function getProject(id: string): Promise<ProjectDetail> {
  return request(`/projects/${id}`);
}

export function createProject(formData: FormData): Promise<ProjectDetail> {
  return request("/projects", { method: "POST", body: formData });
}

export function deleteProject(projectId: string): Promise<void> {
  return request(`/projects/${projectId}`, { method: "DELETE" });
}

export function listTrash(): Promise<ProjectSummary[]> {
  return request("/projects/trash");
}

export function restoreProject(projectId: string): Promise<ProjectSummary> {
  return request(`/projects/${projectId}/restore`, { method: "POST" });
}

export function hardDeleteProject(projectId: string): Promise<void> {
  return request(`/projects/${projectId}/hard`, { method: "DELETE" });
}

export function retryTemplateMap(projectId: string): Promise<TemplateMapResponse> {
  return request(`/projects/${projectId}/template-map/retry`, { method: "POST" });
}

export function getTemplateMap(projectId: string): Promise<TemplateMapResponse> {
  return request(`/projects/${projectId}/template-map`);
}

export function updateTemplateMap(
  projectId: string,
  regions: TemplateRegionInput[]
): Promise<TemplateMapResponse> {
  return request(`/projects/${projectId}/template-map`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regions }),
  });
}

export function confirmTemplateMap(projectId: string): Promise<TemplateMapResponse> {
  return request(`/projects/${projectId}/template-map/confirm`, { method: "POST" });
}

export function unlockTemplateMap(projectId: string): Promise<TemplateMapResponse> {
  return request(`/projects/${projectId}/template-map/unlock`, { method: "POST" });
}

export function listAnswerSheets(projectId: string): Promise<AnswerSheetSummary[]> {
  return request(`/projects/${projectId}/answer-sheets`);
}

export function listDeletedAnswerSheets(projectId: string): Promise<AnswerSheetSummary[]> {
  return request(`/projects/${projectId}/answer-sheets/trash`);
}

export function deleteAnswerSheet(projectId: string, sheetId: string): Promise<void> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}`, { method: "DELETE" });
}

export function restoreAnswerSheet(projectId: string, sheetId: string): Promise<AnswerSheetSummary> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/restore`, { method: "POST" });
}

export function hardDeleteAnswerSheet(projectId: string, sheetId: string): Promise<void> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/permanent`, { method: "DELETE" });
}

export function updateAnswerSheetRegion(
  projectId: string,
  sheetId: string,
  questionKey: string,
  bbox: number[],
  pageIndex?: number
): Promise<AnswerSheetDetail> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/regions/${encodeURIComponent(questionKey)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ bbox, ...(pageIndex === undefined ? {} : { page_index: pageIndex }) }),
  });
}

export function confirmAnswerSheetRegionOverflow(
  projectId: string,
  sheetId: string,
  questionKey: string,
  pageIndex?: number,
): Promise<AnswerSheetDetail> {
  const suffix = pageIndex === undefined ? "" : `?page_index=${pageIndex}`;
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/regions/${encodeURIComponent(questionKey)}/confirm-overflow${suffix}`, { method: "POST" });
}

export function confirmAnswerSheetAlignment(projectId: string, sheetId: string): Promise<AnswerSheetDetail> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/alignment/confirm`, { method: "POST" });
}

export function getAnswerSheet(projectId: string, sheetId: string): Promise<AnswerSheetDetail> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}`);
}

export function uploadAnswerSheet(
  projectId: string,
  rollNumber: string,
  pdf: File
): Promise<AnswerSheetDetail> {
  const formData = new FormData();
  formData.append("roll_number", rollNumber);
  formData.append("pdf", pdf);
  return request(`/projects/${projectId}/answer-sheets`, { method: "POST", body: formData });
}

export function fileUrl(path: string): string {
  const base = `${API_BASE}${path}`;
  if (_apiToken) {
    const sep = path.includes("?") ? "&" : "?";
    return `${base}${sep}token=${encodeURIComponent(_apiToken)}`;
  }
  return base;
}

// ============================================================
// Phase 2 — Question Bank
// ============================================================

export interface QuestionBankItem {
  id: string;
  question_number: string;
  marks_possible: number | null;
  key_points: string | null;
  section_label?: string | null;
  question_text?: string | null;
  question_image_path: string | null;
  rubric_provenance?: string | null;
  rubric_confidence?: "high" | "medium" | "low" | null;
  rubric_reviewed?: boolean;
  alignment_question_number?: string | null;
  alignment_status?: "unreviewed" | "linked" | "not_applicable";
}

export interface QuestionBankListResponse {
  project_id: string;
  confirmed: boolean;
  items: QuestionBankItem[];
}

export interface QuestionBankItemUpdate {
  marks_possible?: number | null;
  key_points?: string | null;
}

export interface QuestionBankConfirmResponse {
  project_id: string;
  confirmed: boolean;
  total_marks_extracted: number;
  total_marks_on_paper: number | null;
  marks_mismatch_warning: string | null;
  effective_total?: number | null;
  structure_status?: string;
  structure_warning?: string | null;
}

export interface RubricStudioCriterion extends QuestionBankItem {
  rubric_provenance: string | null;
  rubric_confidence: "high" | "medium" | "low" | null;
  rubric_reviewed?: boolean;
  section_label?: string | null;
  question_text?: string | null;
}

export interface RubricStudioResponse {
  project_id: string;
  status: string;
  source_mode: string;
  criteria: RubricStudioCriterion[];
  warning: string | null;
  manual_upload_available: boolean;
  all_criteria_reviewed: boolean;
  all_alignment_reviewed: boolean;
  alignment_candidates: Array<{ question_number: string; marks_possible: number | null; question_text?: string | null }>;
  generated_rubric_download_url?: string | null;
}

export interface RubricStudioPreviewResponse {
  status: string;
  criteria: RubricStudioCriterionDraft[];
  warning: string | null;
  manual_upload_available: boolean;
  generated_rubric_download_url?: string | null;
}

export interface RubricStudioExportResponse {
  download_url: string;
  filename: string;
}

export function listQuestionBank(projectId: string): Promise<QuestionBankListResponse> {
  return request(`/projects/${projectId}/question-bank`);
}

export function addQuestionBankItem(
  projectId: string,
  questionNumber: string,
  marksPossible: number | null,
  keyPoints: string | null
): Promise<QuestionBankItem> {
  const params = new URLSearchParams({ question_number: questionNumber });
  if (marksPossible !== null) params.set("marks_possible", String(marksPossible));
  if (keyPoints !== null) params.set("key_points", keyPoints);
  return request(`/projects/${projectId}/question-bank?${params.toString()}`, { method: "POST" });
}

export function updateQuestionBankItem(
  projectId: string,
  questionNumber: string,
  payload: QuestionBankItemUpdate
): Promise<QuestionBankItem> {
  return request(`/projects/${projectId}/question-bank/${questionNumber}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function deleteQuestionBankItem(projectId: string, questionNumber: string): Promise<void> {
  return request(`/projects/${projectId}/question-bank/${questionNumber}`, { method: "DELETE" });
}

export function confirmQuestionBank(projectId: string): Promise<QuestionBankConfirmResponse> {
  return request(`/projects/${projectId}/question-bank/confirm`, { method: "POST" });
}

export interface RubricStudioCriterionDraft {
  question_number: string;
  marks_possible: number | null;
  key_points: string | null;
  section_label?: string | null;
  question_text?: string | null;
  rubric_provenance: string | null;
  rubric_confidence: "high" | "medium" | "low" | null;
  rubric_reviewed: boolean;
}

export function previewRubricStudio(questionPaper: File): Promise<RubricStudioPreviewResponse> {
  const formData = new FormData();
  formData.append("question_paper", questionPaper);
  return request("/projects/rubric-studio/preview", { method: "POST", body: formData });
}

export function exportRubricStudioPdf(projectName: string, criteria: RubricStudioCriterionDraft[]): Promise<RubricStudioExportResponse> {
  return request("/projects/rubric-studio/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_name: projectName, criteria }),
  });
}

export function getRubricStudio(projectId: string): Promise<RubricStudioResponse> {
  return request(`/projects/${projectId}/rubric-studio`);
}

export function generateRubricStudio(projectId: string): Promise<RubricStudioResponse> {
  return request(`/projects/${projectId}/rubric-studio/generate`, { method: "POST" });
}

export function updateRubricStudioCriterion(projectId: string, questionNumber: string, payload: { marks_possible?: number | null; key_points?: string | null; section_label?: string | null; question_text?: string | null; rubric_reviewed?: boolean }): Promise<RubricStudioCriterion> {
  return request(`/projects/${projectId}/rubric-studio/${encodeURIComponent(questionNumber)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function updateRubricAlignment(projectId: string, questionNumber: string, payload: { linked_question_number?: string | null; status: "linked" | "not_applicable" | "unreviewed" }): Promise<RubricStudioResponse> {
  return request(`/projects/${projectId}/rubric-studio/alignment/${encodeURIComponent(questionNumber)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function approveRubricStudio(projectId: string): Promise<RubricStudioResponse> {
  return request(`/projects/${projectId}/rubric-studio/approve`, { method: "POST" });
}

export function uploadManualRubric(projectId: string, rubric: File): Promise<RubricStudioResponse> {
  const formData = new FormData();
  formData.append("rubric", rubric);
  return request(`/projects/${projectId}/rubric-studio/manual-upload`, { method: "POST", body: formData });
}

export function unlockQuestionBank(projectId: string): Promise<QuestionBankListResponse> {
  return request(`/projects/${projectId}/question-bank/unlock`, { method: "POST" });
}

// ============================================================
// Phase 2 — Question Groups
// ============================================================

export interface QuestionGroup {
  id: string;
  project_id: string;
  group_name: string;
  selection_type: "compulsory" | "choose_n_of_m";
  question_numbers: string[];
  n_required: number | null;
  selection_units?: string[][];
  suggestion_confidence?: "high" | "medium" | "low" | null;
  suggestion_evidence?: string | null;
  suggestion_status: "provisional" | "confirmed";
}

export interface QuestionGroupCreate {
  group_name: string;
  selection_type: "compulsory" | "choose_n_of_m";
  question_numbers: string[];
  n_required?: number | null;
  selection_units?: string[][];
}

export function listQuestionGroups(projectId: string): Promise<QuestionGroup[]> {
  return request(`/projects/${projectId}/question-groups`);
}

export function createQuestionGroup(
  projectId: string,
  payload: QuestionGroupCreate
): Promise<QuestionGroup> {
  return request(`/projects/${projectId}/question-groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function confirmQuestionGroup(projectId: string, groupId: string): Promise<QuestionGroup> {
  return request(`/projects/${projectId}/question-groups/${groupId}/confirm`, { method: "POST" });
}

export function deleteQuestionGroup(projectId: string, groupId: string): Promise<void> {
  return request(`/projects/${projectId}/question-groups/${groupId}`, { method: "DELETE" });
}

// ============================================================
// Phase 2 — Grading
// ============================================================

export interface PartScore {
  part: string;
  marks_awarded: number;
  marks_possible: number;
  rationale: string;
}

export interface GradingResult {
  id: string;
  answer_sheet_id: string;
  question_number: string;
  ai_score: number | null;
  ai_total_possible: number | null;
  ai_rationale: string | null;
  part_scores: PartScore[];
  transcription_summary: string | null;
  flags: string[];
  confidence: "high" | "medium" | "low";
  truncation_flag: boolean;
  ink_status: "attempted" | "blank" | "ambiguous";
  ink_density_ratio: number | null;
  choice_status: "graded" | "skipped_blank" | "skipped_beyond_n" | "flagged_ambiguous" | "no_regions";
  human_confirmed_score: number | null;
  human_reviewer_note: string | null;
  reviewed: boolean;
  grading_status: "pending" | "in_progress" | "complete" | "failed";
  error_message: string | null;
  graded_at: string | null;
  region_preview_urls: string[];
  // Phase 5/6 review state and question context
  question_text: string | null;
  key_points: string | null;
  review_state: "ai_draft" | "confirmed" | "overridden" | "ambiguous" | "closed" | "failed";
}

export interface GradingResultSummary {
  question_number: string;
  ai_score: number | null;
  ai_total_possible: number | null;
  confidence: string;
  choice_status: string;
  reviewed: boolean;
  grading_status: string;
}

export interface SectionSummary {
  section_name: string;
  questions: GradingResultSummary[];
  section_total_awarded: number;
  section_total_possible: number;
}

export interface AnswerSheetResultsSummary {
  answer_sheet_id: string;
  sections: SectionSummary[];
  grand_total_awarded: number;
  grand_total_possible: number;
}

export interface AnswerSheetResultsResponse {
  answer_sheet_id: string;
  grading_status: string;
  results: GradingResult[];
  summary: AnswerSheetResultsSummary;
  report_ready?: boolean;
  report_download_url?: string | null;
  completed_at?: string | null;
}

export interface ReportResponse {
  answer_sheet_id: string;
  report_ready: boolean;
  report_download_url: string | null;
  completed_at: string | null;
  blockers: string[];
}

export interface ExaminerConfirmRequest {
  human_confirmed_score: number;
  human_reviewer_note?: string | null;
}

export interface GradeTriggerResponse {
  answer_sheet_id: string;
  grading_status: string;
  graded: string[];
  skipped_blank: string[];
  skipped_beyond_n: string[];
  flagged_ambiguous: string[];
  failed: string[];
}

export interface GradeEnqueueResponse {
  job_id: string;
  answer_sheet_id: string;
}

export interface JobStatusResponse {
  job_id: string;
  answer_sheet_id: string;
  status: "pending" | "in_progress" | "complete" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export function gradeAnswerSheet(projectId: string, sheetId: string): Promise<GradeEnqueueResponse> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/grade`, { method: "POST" });
}

export function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  return request(`/jobs/${jobId}`);
}

/** Poll a grading job until it reaches a terminal state (complete or failed). */
export async function pollGradingJob(jobId: string, intervalMs = 3000, timeoutMs = 600000): Promise<JobStatusResponse> {
  const start = Date.now();
  while (true) {
    const status = await getJobStatus(jobId);
    if (status.status === "complete" || status.status === "failed") return status;
    if (Date.now() - start > timeoutMs) throw new Error("Grading timed out. Please retry from the answer sheet page.");
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export function createExaminerReport(projectId: string, sheetId: string): Promise<ReportResponse> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/report`, { method: "POST" });
}

export function listGradingResults(
  projectId: string,
  sheetId: string
): Promise<AnswerSheetResultsResponse> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/results`);
}

export function getGradingResult(
  projectId: string,
  sheetId: string,
  questionNumber: string
): Promise<GradingResult> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/results/${questionNumber}`);
}

export function confirmGradingResult(
  projectId: string,
  sheetId: string,
  questionNumber: string,
  payload: ExaminerConfirmRequest
): Promise<GradingResult> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/results/${questionNumber}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ============================================================
// Phase 5 — Review Queue
// ============================================================

export interface ReviewQueueItem {
  question_number: string;
  ai_score: number | null;
  ai_total_possible: number | null;
  confidence: string;
  choice_status: string;
  grading_status: string;
  truncation_flag: boolean;
  ink_status: string;
  ink_density_ratio: number | null;
  review_state: string;
  question_text: string | null;
  key_points: string | null;
}

export interface ReviewQueueSheet {
  answer_sheet_id: string;
  roll_number: string;
  grading_status: string;
  total_reviewable: number;
  reviewed_count: number;
  pending_count: number;
  pending_items: ReviewQueueItem[];
}

export interface ProjectReviewQueueResponse {
  project_id: string;
  total_pending: number;
  sheets: ReviewQueueSheet[];
}

export function getProjectReviewQueue(projectId: string): Promise<ProjectReviewQueueResponse> {
  return request(`/projects/${projectId}/review-queue`);
}
