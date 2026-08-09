export const API_BASE = "http://127.0.0.1:8765";

export interface ProjectSummary {
  id: string;
  name: string;
  created_at: string;
  template_map_confirmed: boolean;
  template_map_status: string;
  rubric_locked: boolean;
}

export interface ProjectDetail extends ProjectSummary {
  rubric_file_path: string;
  question_paper_file_path: string;
  blank_booklet_file_path: string;
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
