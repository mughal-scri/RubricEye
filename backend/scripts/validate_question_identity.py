from app.services.question_grouping import canonical_question_label, group_question_bank_by_group, resolve_region_keys_for_question


def main() -> int:
    equivalent = ["Q2(i)", "Q.2(i)", "Question 2(i)", "2(i)", "2i"]
    assert {canonical_question_label(label) for label in equivalent} == {"2i"}
    keys = ["2", "2i", "2ii", "2iii"]
    assert resolve_region_keys_for_question("Q2", keys) == keys
    assert resolve_region_keys_for_question("Q.2(ii)", keys) == ["2ii"]
    membership = group_question_bank_by_group(["2i", "2ii"], [{"id": "g", "question_numbers": ["Q2"], "selection_units": []}])
    assert membership == {"2i": "g", "2ii": "g"}, membership
    print("Question identity regression passed: equivalent labels normalize and bare questions aggregate all parts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
