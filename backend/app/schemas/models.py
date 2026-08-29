from datetime import datetime

from pydantic import BaseModel, Field


class BBox(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int

    def as_list(self) -> list[int]:
        return [self.x1, self.y1, self.x2, self.y2]

    @classmethod
    def from_list(cls, values: list[int]) -> "BBox":
        return cls(x1=values[0], y1=values[1], x2=values[2], y2=values[3])


class TemplateRegion(BaseModel):
    question_number: str
    part_label: str = ""
    bbox: BBox


class TemplateRegionInput(BaseModel):
    page_number: int
    question_number: str
    part_label: str = ""
    bbox: list[int] = Field(min_length=4, max_length=4)


class TemplateMapUpdateRequest(BaseModel):
    regions: list[TemplateRegionInput]


class TemplateMapPageResponse(BaseModel):
    page_number: int
    page_image_url: str
    regions: list[TemplateRegion]


class TemplateMapResponse(BaseModel):
    project_id: str
    confirmed: bool
    status: str
    pages: list[TemplateMapPageResponse]


class ProjectSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    deleted_at: datetime | None = None
    template_map_confirmed: bool
    template_map_status: str
    rubric_locked: bool
    question_bank_confirmed: bool = False

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    rubric_file_path: str
    question_paper_file_path: str
    blank_booklet_file_path: str
    question_bank_marks_warning: str | None = None
    question_bank_raw_total: int | None = None
    question_bank_stated_total: int | None = None
    question_bank_effective_total: int | None = None
    question_bank_structure_status: str = "unresolved"
    rubric_source_mode: str = "uploaded"
    rubric_studio_status: str = "not_used"
    rubric_download_url: str | None = None
    template_map_error: str | None = None


class RegionRef(BaseModel):
    page_index: int
    bbox: list[int]
    nominal_bbox: list[int] | None = None
    overflow_detected: bool = False
    alignment_method: str = "feature"
    alignment_confidence: str = "high"
    alignment_uncertain: bool = False
    page_correspondence_uncertain: bool = False


class AnswerSheetSummary(BaseModel):
    id: str
    project_id: str
    roll_number: str
    uploaded_at: datetime
    deleted_at: datetime | None = None
    page_count: int
    grading_status: str = "not_graded"
    report_ready: bool = False
    report_download_url: str | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class AnswerSheetDetail(AnswerSheetSummary):
    page_image_urls: list[str]
    question_region_map: dict[str, list[RegionRef]]
    region_preview_urls: dict[str, list[str]]


class AnswerSheetRegionUpdate(BaseModel):
    bbox: list[int] = Field(min_length=4, max_length=4)
    page_index: int | None = Field(default=None, ge=0)


# ============================================================
# Phase 2 — Question Bank
# ============================================================


class QuestionBankItemResponse(BaseModel):
    id: str
    question_number: str
    marks_possible: int | None
    key_points: str | None
    section_label: str | None = None
    question_text: str | None = None
    question_image_path: str | None
    rubric_provenance: str | None = None
    rubric_confidence: str | None = None
    rubric_reviewed: bool = False
    alignment_question_number: str | None = None
    alignment_status: str = "unreviewed"

    model_config = {"from_attributes": True}


class QuestionBankItemUpdate(BaseModel):
    marks_possible: int | None = None
    key_points: str | None = None


class QuestionBankListResponse(BaseModel):
    project_id: str
    confirmed: bool
    items: list[QuestionBankItemResponse]


class RubricStudioCriterionUpdate(BaseModel):
    marks_possible: int | None = None
    key_points: str | None = None
    section_label: str | None = None
    question_text: str | None = None
    rubric_reviewed: bool | None = None


class RubricStudioCriterionDraft(BaseModel):
    question_number: str
    marks_possible: int | None
    key_points: str | None
    section_label: str | None = None
    question_text: str | None = None
    rubric_provenance: str | None = None
    rubric_confidence: str | None = None
    rubric_reviewed: bool = False
    alignment_question_number: str | None = None
    alignment_status: str = "unreviewed"


class RubricStudioCriterionResponse(RubricStudioCriterionDraft):
    id: str


class RubricStudioPreviewResponse(BaseModel):
    status: str
    criteria: list[RubricStudioCriterionDraft] = []
    warning: str | None = None
    manual_upload_available: bool = True
    generated_rubric_download_url: str | None = None


class RubricStudioResponse(BaseModel):
    project_id: str
    status: str
    source_mode: str
    criteria: list[RubricStudioCriterionResponse] = []
    warning: str | None = None
    manual_upload_available: bool = True
    all_criteria_reviewed: bool = False
    all_alignment_reviewed: bool = False
    alignment_candidates: list[dict] = []
    generated_rubric_download_url: str | None = None


class RubricStudioExportRequest(BaseModel):
    project_name: str = "RubricEye Assessment"
    criteria: list[RubricStudioCriterionDraft] = Field(default_factory=list)


class RubricStudioExportResponse(BaseModel):
    download_url: str
    filename: str = "rubric.pdf"


class QuestionBankConfirmResponse(BaseModel):
    project_id: str
    confirmed: bool
    total_marks_extracted: int
    total_marks_on_paper: int | None
    marks_mismatch_warning: str | None
    effective_total: int | None = None
    structure_status: str = "unresolved"
    structure_warning: str | None = None


# ============================================================
# Phase 2 — Question Groups (choice-question structure)
# ============================================================


class QuestionGroupCreate(BaseModel):
    group_name: str
    selection_type: str  # "compulsory" | "choose_n_of_m"
    question_numbers: list[str] = Field(min_length=1)
    n_required: int | None = None
    selection_units: list[list[str]] | None = None


class QuestionGroupResponse(BaseModel):
    id: str
    project_id: str
    group_name: str
    selection_type: str
    question_numbers: list[str]
    n_required: int | None
    selection_units: list[list[str]] = []
    suggestion_confidence: str | None = None
    suggestion_evidence: str | None = None
    suggestion_status: str = "confirmed"


class RubricAlignmentUpdate(BaseModel):
    linked_question_number: str | None = None
    status: str


# ============================================================
# Phase 2 — Grading
# ============================================================


class PartScore(BaseModel):
    part: str
    marks_awarded: int
    marks_possible: int
    rationale: str


class GradingResultResponse(BaseModel):
    id: str
    answer_sheet_id: str
    question_number: str
    ai_score: int | None
    ai_total_possible: int | None
    ai_rationale: str | None
    part_scores: list[PartScore]
    transcription_summary: str | None
    flags: list[str]
    confidence: str
    truncation_flag: bool
    ink_status: str
    ink_density_ratio: float | None
    choice_status: str
    human_confirmed_score: int | None
    human_reviewer_note: str | None
    reviewed: bool
    grading_status: str
    error_message: str | None
    graded_at: datetime | None
    region_preview_urls: list[str] = []
    # Phase 3 audit trail
    model_name: str | None = None
    prompt_version: str | None = None
    raw_response_json: str | None = None
    request_payload_summary: str | None = None


class GradingResultSummary(BaseModel):
    question_number: str
    ai_score: int | None
    ai_total_possible: int | None
    confidence: str
    choice_status: str
    reviewed: bool
    grading_status: str


class SectionSummary(BaseModel):
    section_name: str
    questions: list[GradingResultSummary]
    section_total_awarded: int
    section_total_possible: int


class AnswerSheetResultsSummary(BaseModel):
    answer_sheet_id: str
    sections: list[SectionSummary]
    grand_total_awarded: int
    grand_total_possible: int


class AnswerSheetResultsResponse(BaseModel):
    answer_sheet_id: str
    grading_status: str
    results: list[GradingResultResponse]
    summary: AnswerSheetResultsSummary
    report_ready: bool = False
    report_download_url: str | None = None
    completed_at: datetime | None = None


class ReportResponse(BaseModel):
    answer_sheet_id: str
    report_ready: bool
    report_download_url: str | None = None
    completed_at: datetime | None = None
    blockers: list[str] = []


class ExaminerConfirmRequest(BaseModel):
    human_confirmed_score: int
    human_reviewer_note: str | None = None


class GradeTriggerResponse(BaseModel):
    answer_sheet_id: str
    grading_status: str
    graded: list[str]
    skipped_blank: list[str]
    skipped_beyond_n: list[str]
    flagged_ambiguous: list[str]
    failed: list[str]


class GradeEnqueueResponse(BaseModel):
    """Response from POST …/grade (Phase 1 async): job accepted for background processing."""
    job_id: str
    answer_sheet_id: str


class JobStatusResponse(BaseModel):
    """Response from GET /jobs/{job_id} for polling."""
    job_id: str
    answer_sheet_id: str
    status: str  # pending | in_progress | complete | failed
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
