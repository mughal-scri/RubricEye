export const API_BASE = "http://127.0.0.1:8765";

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
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
  page_count: number;
  grading_status: string;
}

export interface RegionRef {
  page_index: number;
  bbox: number[];
}

export interface AnswerSheetDetail extends AnswerSheetSummary {
  page_image_urls: string[];
  question_region_map: Record<string, RegionRef[]>;
  region_preview_urls: Record<string, string[]>;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
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
  return `${API_BASE}${path}`;
}

// ============================================================
// Phase 2 — Question Bank
// ============================================================

export interface QuestionBankItem {
  id: string;
  question_number: string;
  marks_possible: number | null;
  key_points: string | null;
  question_image_path: string | null;
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
}

export interface QuestionGroupCreate {
  group_name: string;
  selection_type: "compulsory" | "choose_n_of_m";
  question_numbers: string[];
  n_required?: number | null;
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

export function gradeAnswerSheet(projectId: string, sheetId: string): Promise<GradeTriggerResponse> {
  return request(`/projects/${projectId}/answer-sheets/${sheetId}/grade`, { method: "POST" });
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
