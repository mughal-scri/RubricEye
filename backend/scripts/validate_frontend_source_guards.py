#!/usr/bin/env python3
"""Static no-cost guards for UI sizing and hardcoding regressions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    question_bank = (ROOT / "frontend/src/pages/QuestionBankSetup.tsx").read_text(encoding="utf-8")
    question_grouping = (ROOT / "backend/app/services/question_grouping.py").read_text(encoding="utf-8")
    studio_editor = (ROOT / "frontend/src/components/RubricCriteriaEditor.tsx").read_text(encoding="utf-8")
    structure = (ROOT / "backend/app/services/paper_structure.py").read_text(encoding="utf-8")
    styles = (ROOT / "frontend/src/styles.css").read_text(encoding="utf-8")
    answer_upload = (ROOT / "frontend/src/pages/UploadAnswerSheet.tsx").read_text(encoding="utf-8")
    answer_detail = (ROOT / "frontend/src/pages/AnswerSheetDetail.tsx").read_text(encoding="utf-8")
    api_client = (ROOT / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    studio_page = (ROOT / "frontend/src/pages/RubricStudio.tsx").read_text(encoding="utf-8")
    template_page = (ROOT / "frontend/src/pages/TemplateMapReview.tsx").read_text(encoding="utf-8")
    region_editor = (ROOT / "frontend/src/components/RegionEditorTable.tsx").read_text(encoding="utf-8")
    region_overlay = (ROOT / "frontend/src/components/RegionOverlay.tsx").read_text(encoding="utf-8")

    assert "ref={resizeElement}" in question_bank, "Question Bank criteria editor must resize on mount"
    assert "scrollHeight" in question_bank, "Question Bank criteria editor must use content height"
    assert 'element.style.height = "0px"' in question_bank, "Question Bank editor must reset height before measuring"
    assert "ref={resizeElement}" in studio_editor and "scrollHeight" in studio_editor, "Rubric Studio criteria editor must also be content-sized"
    assert ".auto-grow-textarea" in styles and "overflow: hidden" in styles, "Auto-grow textarea styling is missing"
    assert "SECTION C" not in structure, "Paper structure must not contain a paper-specific SECTION C anchor"
    assert 'import FilePicker from "../components/FilePicker"' in answer_upload, "Answer-sheet intake must use the shared FilePicker"
    assert 'className="file-choice"' not in answer_upload, "Answer-sheet intake must not duplicate legacy file-choice markup"
    assert "Manual review required before grading." in answer_detail, "Answer-sheet inspection must explain uncertain correspondence before grading"
    assert "page_correspondence_uncertain?: boolean" in api_client, "Frontend region type must carry page correspondence uncertainty"
    assert 'Approved rubric is locked.' in studio_page, "Approved Studio projects need explicit locked-state copy"
    assert 'readOnly={status === "approved"}' in studio_page, "Approved Studio projects must render criteria read-only"
    assert 'status !== "approved" && <button' in studio_page, "Studio mutation controls must be hidden for approved projects"
    assert 'import RegionEditorTable from "../components/RegionEditorTable"' in template_page, "Template review must mount the region editor"
    assert 'import RegionOverlay from "../components/RegionOverlay"' in template_page, "Template review must mount the region overlay"
    assert "onHoverRow={setHoveredIndex}" in template_page and "onSelectRegion={setHoveredIndex}" in template_page, "Template review must synchronize table and overlay selection"
    assert "readOnly={templateMap.confirmed}" in template_page and "readOnly?: boolean" in region_editor, "Confirmed template maps must be read-only"
    assert "onKeyDown" in region_overlay and "role=\"button\"" in region_overlay, "Overlay regions must be keyboard accessible"
    assert "35" not in structure, "Paper structure service must not contain the supplied paper's fixed total"
    assert "Abdullah" not in question_grouping and "Testanswerbook" not in question_grouping, "Production grouping logic must not reference supplied fixtures"
    print("Frontend/source guard regression passed: Question Bank and Rubric Studio editors are content-sized and paper-structure logic has no fixed supplied-paper anchor or total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
