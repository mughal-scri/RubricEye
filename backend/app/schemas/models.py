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
    template_map_confirmed: bool
    template_map_status: str
    rubric_locked: bool

    model_config = {"from_attributes": True}


class ProjectDetail(ProjectSummary):
    rubric_file_path: str
    question_paper_file_path: str
    blank_booklet_file_path: str


class RegionRef(BaseModel):
    page_index: int
    bbox: list[int]


class AnswerSheetSummary(BaseModel):
    id: str
    project_id: str
    roll_number: str
    uploaded_at: datetime
    page_count: int

    model_config = {"from_attributes": True}


class AnswerSheetDetail(AnswerSheetSummary):
    page_image_urls: list[str]
    question_region_map: dict[str, list[RegionRef]]
    region_preview_urls: dict[str, list[str]]
