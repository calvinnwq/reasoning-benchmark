from __future__ import annotations

import csv
import json
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent


class DatasetFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.questions = json.loads((REPO_ROOT / "data" / "questions.json").read_text(encoding="utf-8"))

    def test_csv_export_rows_match_header_shape(self) -> None:
        with (REPO_ROOT / "data" / "questions.csv").open(newline="", encoding="utf-8") as csv_file:
            rows_with_extra_columns = [
                (line_number, row.get("id"), row[None])
                for line_number, row in enumerate(csv.DictReader(csv_file), start=2)
                if None in row
            ]

        self.assertEqual([], rows_with_extra_columns)

    def test_literal_precision_comic_traps_are_exact_scored(self) -> None:
        lp_cases = {case["id"]: case for case in self.questions if case.get("category") == "LP"}

        self.assertEqual(len(lp_cases), 44)
        for case_id in ("LP-01", "LP-04", "LP-06", "LP-18", "LP-26", "LP-32", "LP-33", "LP-44"):
            self.assertIn(case_id, lp_cases)
            self.assertEqual(lp_cases[case_id]["category_label"], "Literal precision / comic traps")
            self.assertIn("expected_answer", lp_cases[case_id])
            self.assertIn("accepted_variants", lp_cases[case_id])

    def test_instruction_ambiguity_includes_cooperative_intent_literalism_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-02", ia_cases)
        case = ia_cases["IA-02"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "pragmatic")
        self.assertFalse(case["ambiguity"]["clarification_expected"])
        self.assertFalse(case["cooperative_intent"]["should_ask_clarifying_question"])
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("intent_alignment", dimension_ids)
        self.assertIn("literal_defensibility", dimension_ids)

    def test_instruction_ambiguity_includes_overclever_gotcha_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-03", ia_cases)
        case = ia_cases["IA-03"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "none")
        self.assertFalse(case["ambiguity"]["clarification_expected"])
        self.assertFalse(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("overclever-gotcha", case["ambiguity"]["tags"])
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("intent_alignment", dimension_ids)
        self.assertIn("helpfulness", dimension_ids)

    def test_instruction_ambiguity_includes_destructive_action_clarification_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-04", ia_cases)
        case = ia_cases["IA-04"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "underspecified")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("destructive-action", case["ambiguity"]["tags"])
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("risk_awareness", dimension_ids)

    def test_instruction_ambiguity_includes_context_dependent_shorthand_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-05", ia_cases)
        case = ia_cases["IA-05"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "underspecified")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("context-dependent-reference", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-team-room")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("context_sensitivity", dimension_ids)

    def test_instruction_ambiguity_includes_missing_selection_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-06", ia_cases)
        case = ia_cases["IA-06"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "underspecified")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("missing-selection", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-file-selection")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("state_awareness", dimension_ids)

    def test_instruction_ambiguity_includes_deictic_reference_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-07", ia_cases)
        case = ia_cases["IA-07"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "reference-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("deictic-reference", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-which-action-to-undo")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("reference_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_date_phrase_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-08", ia_cases)
        case = ia_cases["IA-08"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "temporal-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("relative-date", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-which-friday")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("temporal_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_source_phrase_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-09", ia_cases)
        case = ia_cases["IA-09"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "source-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("source-ambiguity", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-source-reference")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("source_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_scope_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-10", ia_cases)
        case = ia_cases["IA-10"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "scope-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("scope-ambiguity", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-recipient-scope")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("scope_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_target_section_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-11", ia_cases)
        case = ia_cases["IA-11"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "target-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("section-reference", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-summary-section")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("target_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_time_of_day_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-12", ia_cases)
        case = ia_cases["IA-12"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "temporal-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("time-of-day", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-am-or-pm")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("temporal_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_payment_method_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-13", ia_cases)
        case = ia_cases["IA-13"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "payment-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("payment-method", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-which-saved-card")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("payment_method_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_threshold_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-14", ia_cases)
        case = ia_cases["IA-14"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "threshold-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("threshold-reference", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-old-invoice-threshold")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("threshold_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_sort_key_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-15", ia_cases)
        case = ia_cases["IA-15"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "sort-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("sort-key", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-contact-name-sort-key")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("sort_key_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_export_format_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-16", ia_cases)
        case = ia_cases["IA-16"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "format-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("export-format", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-report-export-format")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("format_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_notification_channel_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-17", ia_cases)
        case = ia_cases["IA-17"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "channel-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("notification-channel", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-jordan-notification-channel")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("notification_channel_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_merge_target_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-18", ia_cases)
        case = ia_cases["IA-18"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "merge-target-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("merge-target", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-which-branch-merge")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("merge_target_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_unit_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-19", ia_cases)
        case = ia_cases["IA-19"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "unit-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("temperature-unit", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-thermostat-temperature-unit")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("unit_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_person_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-20", ia_cases)
        case = ia_cases["IA-20"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "person-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("person-identity", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-which-sam-account")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("person_identity_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_location_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-21", ia_cases)
        case = ia_cases["IA-21"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "location-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("office-location", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-which-office-address")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("location_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_permission_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-22", ia_cases)
        case = ia_cases["IA-22"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "permission-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("permission-level", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-access-level")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("permission_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_quantity_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-23", ia_cases)
        case = ia_cases["IA-23"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "quantity-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("order-quantity", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-order-quantity")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("quantity_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_timezone_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-24", ia_cases)
        case = ia_cases["IA-24"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "timezone-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("timezone", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-meeting-timezone")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("timezone_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_restore_target_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-25", ia_cases)
        case = ia_cases["IA-25"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "restore-target-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("restore-target", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-restore-target")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("restore_target_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_deployment_target_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-26", ia_cases)
        case = ia_cases["IA-26"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "deployment-target-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("deployment-target", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-deployment-environment")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("deployment_target_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_version_status_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-27", ia_cases)
        case = ia_cases["IA-27"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "version-status-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("version-status", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-contract-version")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("version_status_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_recurrence_schedule_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-28", ia_cases)
        case = ia_cases["IA-28"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "recurrence-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("recurrence-schedule", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-monthly-report-date")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("recurrence_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_currency_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-29", ia_cases)
        case = ia_cases["IA-29"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "currency-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("currency", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-transfer-currency")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("currency_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_reporting_period_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-30", ia_cases)
        case = ia_cases["IA-30"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "reporting-period-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("reporting-period", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-reporting-quarter")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("reporting_period_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_schedule_direction_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-31", ia_cases)
        case = ia_cases["IA-31"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "schedule-direction-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("schedule-direction", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-deadline-direction")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("schedule_direction_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_data_removal_scope_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-32", ia_cases)
        case = ia_cases["IA-32"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "data-removal-scope-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("data-removal-scope", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-chat-history-removal-scope")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("data_removal_scope_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_mute_duration_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-33", ia_cases)
        case = ia_cases["IA-33"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "mute-duration-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("mute-duration", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-mute-duration")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("mute_duration_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_subscription_tier_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-34", ia_cases)
        case = ia_cases["IA-34"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "subscription-tier-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("subscription-tier", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-subscription-tier")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("subscription_tier_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_sync_direction_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-35", ia_cases)
        case = ia_cases["IA-35"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "sync-direction-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("sync-direction", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-sync-direction")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("sync_direction_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_target_language_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-36", ia_cases)
        case = ia_cases["IA-36"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "target-language-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("target-language", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-target-language")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("target_language_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_recurring_event_scope_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-37", ia_cases)
        case = ia_cases["IA-37"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "recurring-event-scope-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("recurring-event-scope", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-calendar-cancellation-scope")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("recurring_event_scope_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_contact_import_mode_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-38", ia_cases)
        case = ia_cases["IA-38"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "contact-import-mode-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("contact-import-mode", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-contact-import-mode")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("contact_import_mode_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_billing_cycle_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-39", ia_cases)
        case = ia_cases["IA-39"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "billing-cycle-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("billing-cycle", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-billing-cycle")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("billing_cycle_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_delivery_address_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-40", ia_cases)
        case = ia_cases["IA-40"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "delivery-address-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("delivery-address", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-delivery-address")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("delivery_address_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_refund_method_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-41", ia_cases)
        case = ia_cases["IA-41"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "refund-method-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("refund-method", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-refund-method")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("refund_method_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_compression_mode_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-42", ia_cases)
        case = ia_cases["IA-42"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "compression-mode-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("compression-mode", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-compression-mode")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("compression_mode_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_anonymization_mode_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-43", ia_cases)
        case = ia_cases["IA-43"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "anonymization-mode-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("anonymization-mode", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-anonymization-mode")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("anonymization_mode_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_project_removal_mode_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-44", ia_cases)
        case = ia_cases["IA-44"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "project-removal-mode-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("project-removal-mode", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-project-removal-mode")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("project_removal_mode_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_approval_request_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-45", ia_cases)
        case = ia_cases["IA-45"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "approval-request-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("approval-request", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-approval-request")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("approval_request_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_sharing_permission_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-46", ia_cases)
        case = ia_cases["IA-46"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "sharing-permission-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("sharing-permission", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-sharing-permission")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("sharing_permission_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_two_factor_method_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-47", ia_cases)
        case = ia_cases["IA-47"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "two-factor-method-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("two-factor-method", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-two-factor-method")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("two_factor_method_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_account_deactivation_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-48", ia_cases)
        case = ia_cases["IA-48"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "account-deactivation-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("account-deactivation", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-account-deactivation")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("account_deactivation_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_invoice_payment_action_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-49", ia_cases)
        case = ia_cases["IA-49"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "invoice-payment-action-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("invoice-payment-action", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-invoice-payment-action")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("invoice_payment_action_resolution", dimension_ids)

    def test_instruction_ambiguity_includes_ambiguous_ticket_closure_case(self) -> None:
        ia_cases = {case["id"]: case for case in self.questions if case.get("category") == "IA"}

        self.assertIn("IA-50", ia_cases)
        case = ia_cases["IA-50"]
        self.assertEqual(case["task_family_id"], "instruction-ambiguity")
        self.assertEqual(case["evaluation"]["mode"], "hybrid")
        self.assertEqual(case["ambiguity"]["ambiguity_type"], "ticket-closure-ambiguous")
        self.assertTrue(case["ambiguity"]["clarification_expected"])
        self.assertTrue(case["cooperative_intent"]["should_ask_clarifying_question"])
        self.assertIn("ticket-closure", case["ambiguity"]["tags"])
        self.assertEqual(case["ambiguity"]["preferred_resolution"], "clarify-ticket-closure")
        dimension_ids = {dimension["id"] for dimension in case["evaluation"]["dimensions"]}
        self.assertIn("clarification_quality", dimension_ids)
        self.assertIn("ticket_closure_resolution", dimension_ids)
