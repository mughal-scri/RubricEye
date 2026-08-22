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
    template_map_error: str | None = None


class RegionRef(BaseModel):
    page_index: int
    bbox: list[int]


class AnswerSheetSummary(BaseModel):
    id: str
    project_id: str
    roll_number: str
    uploaded_at: datetime
    page_count: int
    grading_status: str = "not_graded"

    model_config = {"from_attributes": True}


class AnswerSheetDetail(AnswerSheetSummary):
    page_image_urls: list[str]
    question_region_map: dict[str, list[RegionRef]]
    region_preview_urls: dict[str, list[str]]


# ============================================================
# Phase 2 — Question Bank
# ============================================================


class QuestionBankItemResponse(BaseModel):
    id: str
    question_number: str
    marks_possible: int | None
    key_points: str | None
    question_image_path: str | None

    model_config = {"from_attributes": True}


class QuestionBankItemUpdate(BaseModel):
    marks_possible: int | None = None
    key_points: str | None = None


class QuestionBankListResponse(BaseModel):
    project_id: str
    confirmed: bool
    items: list[QuestionBankItemResponse]


class QuestionBankConfirmResponse(BaseModel):
    project_id: str
    confirmed: bool
    total_marks_extracted: int
    total_marks_on_paper: int | None
    marks_mismatch_warning: str | None


# ============================================================
# Phase 2 — Question Groups (choice-question structure)
# ============================================================


class QuestionGroupCreate(BaseModel):
    group_name: str
    selection_type: str  # "compulsory" | "choose_n_of_m"
    question_numbers: list[str] = Field(min_length=1)
    n_required: int | None = None


class QuestionGroupResponse(BaseModel):
    id: str
    project_id: str
    group_name: str
    selection_type: str
    question_numbers: list[str]
    n_required: int | None


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
