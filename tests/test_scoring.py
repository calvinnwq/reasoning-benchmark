from __future__ import annotations

import json
import sys
from pathlib import Path
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
sys.path.append(str(REPO_ROOT / "scripts"))

import score_run


class ScoringNormalizationTests(unittest.TestCase):
    def test_normalize_text(self) -> None:
        self.assertEqual(
            score_run.normalize_text("  No, The cat’s   at the door. "),
            "no the cat s at the door",
        )

    def test_normalize_text_handles_common_contractions_and_spelling(self) -> None:
        self.assertEqual(
            score_run.normalize_text("They're signalling they won't leave in 100 metres."),
            "they are signaling they will not leave in 100 meters",
        )

    def test_missing_answer_scores_zero(self) -> None:
        result = score_run.score_single_answer("", "Yes. Carry the object.", [])
        self.assertEqual(result.score, 0)
        self.assertEqual(result.matched_by, "missing")
        self.assertEqual(result.reason, "missing_answer")

    def test_yes_no_binary_match(self) -> None:
        result = score_run.score_single_answer(
            "No.",
            "No. They are asking you to hand it over.",
            [],
        )
        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "binary_match")

    def test_yes_no_mismatch(self) -> None:
        result = score_run.score_single_answer(
            "Yes, you should.",
            "No. It is not requested.",
            [],
        )
        self.assertEqual(result.score, 0)
        self.assertEqual(result.matched_by, "binary_mismatch")

    def test_accepted_variant_match_counts(self) -> None:
        result = score_run.score_single_answer(
            "Take the coat with you.",
            "Bring the coat with you now.",
            ["Take the coat with you.", "Bring the coat on the first trip."],
        )
        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "exact")

    def test_short_prefix_match_counts_as_heuristic(self) -> None:
        result = score_run.score_single_answer(
            "Drive",
            "Drive there. The car is the thing that needs to reach the car wash.",
            ["Drive there.", "Take the car there."],
        )
        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "heuristic_prefix")
        self.assertTrue(result.heuristic)

    def test_exact_variant_policy_disables_heuristic_prefix_matches(self) -> None:
        result = score_run.score_single_answer(
            "Three.",
            "In the fictional premise, three horns; in reality, none.",
            [
                "Three in the fictional premise; none in reality.",
                "Fictionally three, literally none.",
                "Three if accepting the premise, none in reality.",
            ],
            accepted_variant_policy=score_run.NORMALIZED_EXACT_ACCEPTED_VARIANT_POLICY,
        )
        self.assertEqual(result.score, 0)
        self.assertEqual(result.matched_by, "none")
        self.assertFalse(result.heuristic)

    def test_exact_variant_policy_rejects_leading_yes_no_prefixes(self) -> None:
        result = score_run.score_single_answer(
            "Yes, no thanks",
            "No thanks",
            [],
            accepted_variant_policy=score_run.NORMALIZED_EXACT_ACCEPTED_VARIANT_POLICY,
        )
        self.assertEqual(result.score, 0)
        self.assertEqual(result.matched_by, "none")
        self.assertFalse(result.heuristic)

    def test_exact_variant_policy_rejects_prefillers(self) -> None:
        result = score_run.score_single_answer(
            "The answer is gremlin, ogre, raccoon",
            "gremlin, ogre, raccoon",
            [],
            accepted_variant_policy=score_run.NORMALIZED_EXACT_ACCEPTED_VARIANT_POLICY,
        )
        self.assertEqual(result.score, 0)
        self.assertEqual(result.matched_by, "none")
        self.assertFalse(result.heuristic)

    def test_binary_match_rejects_longer_conflicting_no_answers(self) -> None:
        for answer, expected in [
            ("No, it is.", "No. A toaster is not a creature."),
            ("No, after landing.", "No. That would not test its useful function."),
            ("No, soup bowl.", "No. It is still an umbrella, not a soup bowl."),
            ("No, book a window seat anyway.", "No. The request was to sit by the aisle."),
            ("No, try it after landing when it is safer.", "No. You still cannot use it during takeoff."),
            ("No, a toaster is covered by that rule.", "No. A toaster is not allowed in carry-on luggage."),
        ]:
            with self.subTest(answer=answer):
                result = score_run.score_single_answer(answer, expected, [])
                self.assertEqual(result.score, 0)
                self.assertNotEqual(result.matched_by, "binary_match")

    def test_binary_overlap_accepts_aligned_longer_explanations(self) -> None:
        for answer, expected in [
            ("No, they are asking you to hand them the salt.", "No. They are asking you to hand it over."),
            ("Yes, ovens stay hot after being turned off.", "Yes. It can still be hot after being turned off."),
        ]:
            with self.subTest(answer=answer):
                result = score_run.score_single_answer(answer, expected, [])
                self.assertEqual(result.score, 1)
                self.assertEqual(result.matched_by, "binary_overlap")
                self.assertTrue(result.heuristic)

    def test_binary_overlap_rejects_shared_prefix_contradictions(self) -> None:
        for answer, expected in [
            ("No, they are asking you to keep it.", "No. They are asking you to hand it over."),
            ("No, they are asking you to hand it back.", "No. They are asking you to hand it over."),
            ("No, it is still hot after being turned on.", "No. It is still hot after being turned off."),
        ]:
            with self.subTest(answer=answer):
                result = score_run.score_single_answer(answer, expected, [])
                self.assertEqual(result.score, 0)
                self.assertNotEqual(result.matched_by, "binary_overlap")

    def test_binary_overlap_rejects_contradictory_trailing_clause(self) -> None:
        for answer, expected in [
            (
                "No, a toaster is not a creature, so yes, it is covered by the rule.",
                "No. A toaster is not a creature.",
            ),
            (
                "No, they are asking you to hand it over, but actually keep it.",
                "No. They are asking you to hand it over.",
            ),
        ]:
            with self.subTest(answer=answer):
                result = score_run.score_single_answer(answer, expected, [])
                self.assertEqual(result.score, 0)
                self.assertNotEqual(result.matched_by, "binary_overlap")

    def test_binary_overlap_rejects_contradictory_long_shared_span_with_dueling_tails(self) -> None:
        result = score_run.score_single_answer(
            "No, it is still hot after being turned off, but it is safe to grab immediately.",
            "No. It is still hot after being turned off until it cools.",
            [],
        )
        self.assertEqual(result.score, 0)
        self.assertNotEqual(result.matched_by, "binary_overlap")

    def test_binary_overlap_rejects_non_contrastive_late_divergence(self) -> None:
        result = score_run.score_single_answer(
            "No, it is still hot after being turned off until dinner, so grab it now.",
            "No. It is still hot after being turned off until dinner, so wait to touch it.",
            [],
        )
        self.assertEqual(result.score, 0)
        self.assertNotEqual(result.matched_by, "binary_overlap")

    def test_binary_overlap_rejects_contradictory_leading_clause(self) -> None:
        for answer, expected in [
            (
                "No, keep it; they are asking you to hand them the salt.",
                "No. They are asking you to hand it over.",
            ),
            (
                "No, use it to collect soup; it is still an umbrella, not a soup bowl.",
                "No. It is still an umbrella, not a soup bowl.",
            ),
        ]:
            with self.subTest(answer=answer):
                result = score_run.score_single_answer(answer, expected, [])
                self.assertEqual(result.score, 0)
                self.assertNotEqual(result.matched_by, "binary_overlap")

    def test_single_token_contiguous_span_does_not_accept_longer_answers(self) -> None:
        for answer, expected, variants in [
            ("None, $10 cash is missing from my wallet.", "None.", ["None"]),
            ("8 letters if you ignore soup, but 12 in total.", "8", ["8"]),
            ("Three, actually I cannot continue the joke.", "Three", ["Three"]),
        ]:
            with self.subTest(answer=answer):
                result = score_run.score_single_answer(answer, expected, variants)
                self.assertEqual(result.score, 0)
                self.assertNotEqual(result.matched_by, "heuristic_subsequence")

    def test_leading_no_does_not_block_variant_match(self) -> None:
        result = score_run.score_single_answer(
            "No, bring the coat on your first trip.",
            "Bring the coat with you now.",
            ["Take the coat with you.", "Bring the coat on the first trip."],
        )
        self.assertEqual(result.score, 1)
        self.assertIn(result.matched_by, {"exact", "heuristic_subsequence"})

    def test_expected_no_token_does_not_block_exact_expected_match(self) -> None:
        result = score_run.score_single_answer(
            "Nothing. There is no S in ChatGPT.",
            "Nothing. There is no S in ChatGPT.",
            [
                "It does not stand for anything; ChatGPT has no S.",
                "There is no letter S in ChatGPT.",
            ],
        )
        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "exact")

    def test_expected_no_token_does_not_block_exact_variant_match(self) -> None:
        result = score_run.score_single_answer(
            "Nothing.",
            "Nothing. There is no Q in banana.",
            [
                "It stands for nothing; banana has no Q.",
                "There is no Q in banana.",
                "Nothing.",
            ],
        )
        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "exact")

    def test_contraction_variant_counts_for_survivor_riddle(self) -> None:
        result = score_run.score_single_answer(
            "You don't bury survivors — they're alive.",
            "You do not bury the survivors.",
            ["Nowhere, because survivors are alive.", "You wouldn't bury survivors."],
        )
        self.assertEqual(result.score, 1)
        self.assertIn(result.matched_by, {"exact", "heuristic_subsequence"})

    def test_number_word_equivalence_accepts_same_number_and_unit(self) -> None:
        for answer, expected, variants in [
            ("3 paws", "Three paws.", ["3", "Three.", "Three paws."]),
            ("5 coins", "Five coins.", ["5", "Five.", "Five coins."]),
        ]:
            with self.subTest(answer=answer):
                result = score_run.score_single_answer(answer, expected, variants)
                self.assertEqual(result.score, 1)
                self.assertEqual(result.matched_by, "heuristic_numeric_word_equivalence")

    def test_number_word_equivalence_rejects_different_units(self) -> None:
        result = score_run.score_single_answer("3 legs", "Three paws.", ["3", "Three.", "Three paws."])

        self.assertEqual(result.score, 0)
        self.assertNotEqual(result.matched_by, "heuristic_numeric_word_equivalence")

    def test_literal_absence_accepts_optional_letter_word(self) -> None:
        result = score_run.score_single_answer(
            'Nothing — there is no letter "Q" in "banana".',
            "Nothing. There is no Q in banana.",
            ["It stands for nothing; banana has no Q.", "There is no Q in banana.", "Nothing."],
            task_family_id="literal-precision",
        )

        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "heuristic_literal_absence")

    def test_literal_absence_rejects_invented_acronym_meaning(self) -> None:
        result = score_run.score_single_answer(
            "Q stands for quality.",
            "Nothing. There is no Q in banana.",
            ["It stands for nothing; banana has no Q.", "There is no Q in banana.", "Nothing."],
            task_family_id="literal-precision",
        )

        self.assertEqual(result.score, 0)
        self.assertNotEqual(result.matched_by, "heuristic_literal_absence")

    def test_temporal_binary_leading_answer_accepts_explanation(self) -> None:
        result = score_run.score_single_answer(
            "Yes. Five minutes is far too short for a well-insulated oven to cool down.",
            "Yes.",
            ["Yes, it could still be hot.", "Yes, ovens stay hot after being turned off."],
            task_family_id="temporal-state",
        )

        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "heuristic_binary_leading_answer")

    def test_temporal_binary_leading_answer_rejects_later_opposite(self) -> None:
        result = score_run.score_single_answer(
            "Yes, but actually no, it is safe now.",
            "Yes.",
            ["Yes, it could still be hot."],
            task_family_id="temporal-state",
        )

        self.assertEqual(result.score, 0)
        self.assertNotEqual(result.matched_by, "heuristic_binary_leading_answer")

    def test_action_phrase_containment_accepts_practical_action_with_explanation(self) -> None:
        result = score_run.score_single_answer(
            "No—just take the coat with you, since the cleaner is right across the street.",
            "Bring the coat with you now.",
            ["Take the coat with you.", "Bring the coat on the first trip."],
            task_family_id="goal-grounding",
        )

        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "heuristic_action_phrase_containment")

    def test_survivor_alive_trap_accepts_no_bury_without_repeating_bury(self) -> None:
        result = score_run.score_single_answer(
            "You don't — survivors are alive, so they aren't buried.",
            "You do not bury the survivors.",
            ["Nowhere, because survivors are alive.", "You wouldn't bury survivors.", "You don't bury survivors."],
            task_family_id="classic-riddle-override",
        )

        self.assertEqual(result.score, 1)
        self.assertEqual(result.matched_by, "heuristic_survivor_alive_trap")


class ScoringFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dataset = score_run.load_dataset(score_run.DEFAULT_DATASET_PATH)
        self.input_payload = {
            "results": [
                {
                    "id": "GG-01",
                    "answer": "Drive there.",
                    "score_answer": None,
                    "score_reasoning": None,
                    "score_constraint_extraction": None,
                    "penalties": None,
                    "notes": "",
                },
                {
                    "id": "ZZ-99",
                    "answer": "No.",
                },
            ]
        }

    def test_unknown_question_id_is_marked(self) -> None:
        meta, records = score_run.normalize_run_payload(self.input_payload)
        scored = [score_run.score_record(record, self.dataset) for record in records]
        self.assertEqual(scored[1]["score_answer"], None)
        status = scored[1]["scoring_status"]
        self.assertEqual(status["reason"], "unknown_question_id")
        self.assertTrue(status["heuristic_flags"][0]["is_heuristic"])

    def test_unknown_question_id_status_keeps_default_evaluation_fields(self) -> None:
        scored = score_run.score_record({"id": "ZZ-99", "answer": "No."}, self.dataset)

        status = scored["scoring_status"]
        self.assertEqual(status["answer_field"], "answer")
        self.assertEqual(status["reasoning_field"], "reasoning")
        self.assertEqual(status["accepted_variant_policy"], "normalized_exact_or_configured_heuristic")
        self.assertEqual(status["dimensions"], [])

    def test_case_id_alias_is_scored(self) -> None:
        scored = score_run.score_record({"case_id": "GG-01", "answer": "Drive there."}, self.dataset)
        self.assertEqual(scored["score_answer"], 1)
        self.assertEqual(scored["evaluation_mode"], "exact")
        self.assertEqual(scored["task_family_id"], "goal-grounding")
        self.assertEqual(
            scored["failure_mode"],
            "Optimises for human walking distance instead of the task goal.",
        )
        self.assertEqual(scored["scoring_status"]["reason"], "exact_normalized_match")

    def test_scored_record_adds_codex_normalized_and_billing_usage(self) -> None:
        scored = score_run.score_record(
            {
                "case_id": "GG-01",
                "model": "gpt-5.5-xhigh",
                "answer": "Drive there.",
                "usage": {
                    "provider": "codex",
                    "input_tokens": 100,
                    "cache_read_input_tokens": 25,
                    "output_tokens": 10,
                    "reasoning_output_tokens": 7,
                    "duration_ms": 1200,
                },
            },
            self.dataset,
        )

        self.assertEqual(scored["normalized_usage"]["input_tokens"], 100)
        self.assertEqual(scored["normalized_usage"]["output_tokens"], 10)
        self.assertEqual(scored["normalized_usage"]["reasoning_output_tokens"], 7)
        self.assertTrue(scored["normalized_usage"]["reasoning_output_tokens_included"])
        self.assertAlmostEqual(scored["normalized_usage"]["cost_usd"], 0.0006875)
        self.assertEqual(scored["normalized_usage"]["cost_source"], "estimated_api_equivalent")
        self.assertEqual(scored["billing_usage"]["uncached_input_tokens"], 75)
        self.assertEqual(scored["billing_usage"]["cache_read_input_tokens"], 25)
        self.assertAlmostEqual(scored["billing_usage"]["estimated_codex_credits"], 0.0171875)

    def test_scored_record_adds_claude_normalized_and_billing_usage(self) -> None:
        scored = score_run.score_record(
            {
                "case_id": "GG-01",
                "model": "opus-4.8-max",
                "answer": "Drive there.",
                "usage": {
                    "provider": "claude",
                    "input_tokens": 100,
                    "cache_read_input_tokens": 25,
                    "cache_creation_input_tokens": 50,
                    "output_tokens": 10,
                    "provider_reported_cost_usd": 0.0123,
                },
            },
            self.dataset,
        )

        self.assertEqual(scored["normalized_usage"]["input_tokens"], 175)
        self.assertEqual(scored["normalized_usage"]["output_tokens"], 10)
        self.assertEqual(scored["normalized_usage"]["cost_usd"], 0.0123)
        self.assertEqual(scored["normalized_usage"]["cost_source"], "provider_reported")
        self.assertEqual(scored["billing_usage"]["uncached_input_tokens"], 100)
        self.assertEqual(scored["billing_usage"]["cache_read_input_tokens"], 25)
        self.assertEqual(scored["billing_usage"]["cache_creation_input_tokens"], 50)

    def test_usage_run_false_negative_regressions_score_correctly(self) -> None:
        cases = {
            "CR-02": "Race all six horses together in a single race; the winner is the fastest.",
            "MC-02": "No—keep your arm steady and minimize movement.",
            "MC-04": "No, test them in bright glare conditions.",
            "LP-24": "No. Test or inspect it before jumping, not after landing.",
            "LP-25": "The ice cream melts.",
            "LP-27": "3 paws",
            "TW-04": (
                "No. Since there is only one empty chamber and it was just fired, "
                "the next chamber is certainly loaded (0% chance of being empty)."
            ),
            "SP-05": "Open the window (a literal 'no, I don't mind' means you agree, so go ahead and open it).",
            "LP-19": "terse",
            "LP-38": "5 coins",
            "GG-03": "No—just take the coat with you, since the cleaner is right across the street.",
            "GG-04": "No—bring the key with you; the locksmith can't copy a key that's left at home.",
            "CR-08": "You don't — survivors are alive, so they aren't buried.",
            "TW-01": (
                "Yes. Five minutes is far too short for a well-insulated oven to cool down; "
                "the interior and racks are likely still hundreds of degrees and can easily burn you."
            ),
            "LP-07": 'Nothing — there is no letter "Q" in "banana".',
            "LP-11": "No, it's not being rude.",
        }

        for case_id, answer in cases.items():
            with self.subTest(case_id=case_id):
                scored = score_run.score_record({"id": case_id, "answer": answer}, self.dataset)
                self.assertEqual(scored["score_answer"], 1)

    def test_scored_record_includes_v2_scored_at_timestamp(self) -> None:
        scored = score_run.score_record({"case_id": "GG-01", "answer": "Drive there."}, self.dataset)

        self.assertIsInstance(scored["scored_at"], str)
        self.assertTrue(scored["scored_at"])

    def test_scored_record_includes_ambiguity_metadata(self) -> None:
        dataset = {
            "IA-01": {
                "id": "IA-01",
                "expected_answer": "Ask which account to use.",
                "accepted_variants": ["Ask for clarification."],
                "ambiguity": {
                    "ambiguity_type": "underspecified",
                    "clarification_expected": True,
                },
            }
        }

        scored = score_run.score_record({"id": "IA-01", "answer": "Ask for clarification."}, dataset)

        self.assertEqual(scored["ambiguity_type"], "underspecified")
        self.assertTrue(scored["clarification_expected"])

    def test_scored_record_preserves_ambiguity_review_context(self) -> None:
        dataset = {
            "IA-02": {
                "id": "IA-02",
                "expected_answer": "Open the window.",
                "accepted_variants": ["Open it."],
                "accepted_interpretations": [
                    {
                        "id": "cooperative-request",
                        "label": "Treat the utterance as a polite request",
                        "preferred": True,
                        "answer_requirements": ["opens the window"],
                    }
                ],
                "cooperative_intent": {
                    "expected_behavior": "answer the intended practical request",
                    "literal_trap": "answering only the literal yes/no question",
                    "helpfulness_target": "open the window",
                    "should_ask_clarifying_question": False,
                },
            }
        }

        scored = score_run.score_record({"id": "IA-02", "answer": "Open it."}, dataset)

        self.assertEqual(scored["accepted_interpretations"], dataset["IA-02"]["accepted_interpretations"])
        self.assertEqual(scored["cooperative_intent"], dataset["IA-02"]["cooperative_intent"])

    def test_scored_record_preserves_detailed_ambiguity_review_context(self) -> None:
        dataset = {
            "IA-03": {
                "id": "IA-03",
                "expected_answer": "Ask which file to delete.",
                "accepted_variants": ["Ask for clarification."],
                "ambiguity": {
                    "ambiguity_type": "underspecified",
                    "tags": ["missing-selection", "destructive-action"],
                    "clarification_expected": True,
                    "literal_reading_defensible": False,
                    "preferred_resolution": "clarify-file-selection",
                    "notes": "The prompt omits which file should be deleted.",
                },
            }
        }

        scored = score_run.score_record({"id": "IA-03", "answer": "Ask for clarification."}, dataset)

        self.assertEqual(scored.get("ambiguity_tags"), ["missing-selection", "destructive-action"])
        self.assertFalse(scored.get("literal_reading_defensible"))
        self.assertEqual(scored.get("preferred_resolution"), "clarify-file-selection")
        self.assertEqual(scored.get("ambiguity_notes"), "The prompt omits which file should be deleted.")

    def test_scored_record_includes_calibration_metadata(self) -> None:
        dataset = {
            "CAL-01": {
                "id": "CAL-01",
                "expected_answer": "Ask a clarifying question.",
                "accepted_variants": ["Ask for clarification."],
                "calibration": {
                    "difficulty": "starter",
                    "split": "holdout",
                    "gold_confidence": "medium",
                    "human_disagreement_risk": "high",
                    "review_status": "reviewed",
                },
            }
        }

        scored = score_run.score_record({"id": "CAL-01", "answer": "Ask for clarification."}, dataset)

        self.assertEqual(scored["calibration_difficulty"], "starter")
        self.assertEqual(scored["calibration_split"], "holdout")
        self.assertEqual(scored["gold_confidence"], "medium")
        self.assertEqual(scored["human_disagreement_risk"], "high")
        self.assertEqual(scored["review_status"], "reviewed")

    def test_instruction_ambiguity_category_has_v2_defaults(self) -> None:
        dataset = {
            "IA-01": {
                "id": "IA-01",
                "category": "IA",
                "expected_answer": "Ask which Alex to send it to.",
                "accepted_variants": ["Ask which Alex."],
            }
        }

        scored = score_run.score_record({"id": "IA-01", "answer": "Ask which Alex."}, dataset)

        self.assertEqual(scored["task_family_id"], "instruction-ambiguity")
        self.assertEqual(scored["ambiguity_type"], "underspecified")

    def test_hybrid_evaluation_mode_keeps_exact_answer_scoring(self) -> None:
        dataset = {
            "HY-01": {
                "id": "HY-01",
                "expected_answer": "Help the user directly.",
                "accepted_variants": ["Help directly."],
                "evaluation": {"mode": "hybrid", "dimensions": ["answer_correctness", "helpfulness"]},
            }
        }

        scored = score_run.score_record({"id": "HY-01", "answer": "Help directly."}, dataset)

        self.assertEqual(scored["evaluation_mode"], "hybrid")
        self.assertEqual(scored["score_answer"], 1)
        self.assertEqual(scored["scoring_status"]["reason"], "exact_normalized_match")

    def test_evaluation_answer_field_selects_scored_response_field(self) -> None:
        dataset = {
            "AF-01": {
                "id": "AF-01",
                "expected_answer": "Open the window.",
                "accepted_variants": ["Open it."],
                "evaluation": {"mode": "exact", "answer_field": "final_answer"},
            }
        }

        scored = score_run.score_record(
            {"id": "AF-01", "answer": "Leave it closed.", "final_answer": "Open it."},
            dataset,
        )

        self.assertEqual(scored["score_answer"], 1)
        self.assertEqual(scored["scoring_status"]["answer_field"], "final_answer")
        self.assertEqual(scored["score_answer_normalized"]["answer"], "Open it.")

    def test_evaluation_reasoning_field_is_recorded_for_review(self) -> None:
        dataset = {
            "RF-01": {
                "id": "RF-01",
                "expected_answer": "Ask for the room.",
                "accepted_variants": ["Ask which room."],
                "evaluation": {
                    "mode": "hybrid",
                    "answer_field": "final_answer",
                    "reasoning_field": "scratchpad",
                },
            }
        }

        scored = score_run.score_record(
            {
                "id": "RF-01",
                "answer": "Book the room.",
                "final_answer": "Ask which room.",
                "scratchpad": "There is not enough context.",
            },
            dataset,
        )

        self.assertEqual(scored["score_answer"], 1)
        self.assertEqual(scored["scoring_status"]["answer_field"], "final_answer")
        self.assertEqual(scored["scoring_status"]["reasoning_field"], "scratchpad")

    def test_evaluation_accepted_variant_policy_is_recorded_for_review(self) -> None:
        dataset = {
            "AV-01": {
                "id": "AV-01",
                "expected_answer": "Ask which file they mean.",
                "accepted_variants": ["Clarify the file first."],
                "evaluation": {
                    "mode": "hybrid",
                    "accepted_variant_policy": "normalized_exact_or_configured_heuristic",
                },
            }
        }

        scored = score_run.score_record({"id": "AV-01", "answer": "Clarify the file first."}, dataset)

        self.assertEqual(
            scored["scoring_status"]["accepted_variant_policy"],
            "normalized_exact_or_configured_heuristic",
        )

    def test_hybrid_evaluation_dimensions_preserve_weights_and_manual_statuses(self) -> None:
        dataset = {
            "HY-02": {
                "id": "HY-02",
                "expected_answer": "Open the window.",
                "accepted_variants": ["Open it."],
                "evaluation": {
                    "mode": "hybrid",
                    "dimensions": [
                        {
                            "id": "answer_correctness",
                            "label": "Final answer correctness",
                            "type": "binary",
                            "weight": 0.6,
                            "auto_scored": True,
                        },
                        {
                            "id": "intent_alignment",
                            "label": "Intent alignment",
                            "type": "rubric",
                            "weight": 0.4,
                            "auto_scored": False,
                        },
                    ],
                },
            }
        }

        scored = score_run.score_record({"id": "HY-02", "answer": "Open it."}, dataset)

        dimensions = scored["scoring_status"]["dimensions"]
        self.assertEqual(
            dimensions,
            [
                {
                    "id": "answer_correctness",
                    "label": "Final answer correctness",
                    "type": "binary",
                    "weight": 0.6,
                    "auto_scored": True,
                    "score": 1,
                    "status": "auto_scored",
                },
                {
                    "id": "intent_alignment",
                    "label": "Intent alignment",
                    "type": "rubric",
                    "weight": 0.4,
                    "auto_scored": False,
                    "score": None,
                    "status": "manual_review_required",
                },
            ],
        )

    def test_rubric_evaluation_mode_requires_manual_review(self) -> None:
        dataset = {
            "RB-01": {
                "id": "RB-01",
                "expected_answer": "A helpful response.",
                "accepted_variants": ["A helpful response."],
                "evaluation": {"mode": "rubric", "dimensions": ["helpfulness", "clarification_quality"]},
            }
        }

        scored = score_run.score_record({"id": "RB-01", "answer": "A helpful response."}, dataset)

        self.assertEqual(scored["evaluation_mode"], "rubric")
        self.assertIsNone(scored["score_answer"])
        self.assertEqual(scored["scoring_status"]["score"], None)
        self.assertEqual(scored["scoring_status"]["reason"], "rubric_manual_review_required")

    def test_rubric_evaluation_dimensions_preserve_weights_as_manual(self) -> None:
        dataset = {
            "RB-02": {
                "id": "RB-02",
                "expected_answer": "A helpful response.",
                "accepted_variants": ["A helpful response."],
                "evaluation": {
                    "mode": "rubric",
                    "dimensions": [
                        {
                            "id": "helpfulness",
                            "label": "Helpfulness",
                            "type": "rubric",
                            "weight": 0.7,
                            "auto_scored": False,
                        }
                    ],
                },
            }
        }

        scored = score_run.score_record({"id": "RB-02", "answer": "A helpful response."}, dataset)

        self.assertEqual(
            scored["scoring_status"]["dimensions"],
            [
                {
                    "id": "helpfulness",
                    "label": "Helpfulness",
                    "type": "rubric",
                    "weight": 0.7,
                    "auto_scored": False,
                    "score": None,
                    "status": "manual_review_required",
                }
            ],
        )

    def test_scored_payload_building(self) -> None:
        _, records = score_run.normalize_run_payload(self.input_payload)
        scored = [score_run.score_record(item, self.dataset) for item in records]
        output = score_run.build_output_payload(
            {},
            scored,
            str(score_run.DEFAULT_DATASET_PATH),
            "runs/example-run.json",
        )
        parsed_json = json.dumps(output)
        parsed = json.loads(parsed_json)
        self.assertEqual(parsed["schema_version"], "2.0.0")
        self.assertIn("summary", parsed)
        self.assertIn("auto_scored", parsed["summary"])
        self.assertIn("manual_only", parsed["summary"])
        self.assertEqual(parsed["summary"]["overall"]["question_count"], 2)

    def test_summary_rolls_up_normalized_usage_by_model(self) -> None:
        scored = [
            score_run.score_record(
                {
                    "id": "GG-01",
                    "model": "gpt-5.5-xhigh",
                    "answer": "Drive there.",
                    "usage": {
                        "provider": "codex",
                        "input_tokens": 100,
                        "cache_read_input_tokens": 25,
                        "output_tokens": 10,
                    },
                },
                self.dataset,
            ),
            score_run.score_record(
                {
                    "id": "GG-02",
                    "model": "gpt-5.5-xhigh",
                    "answer": "Bring the suit.",
                    "usage": {
                        "provider": "codex",
                        "input_tokens": 200,
                        "cache_read_input_tokens": 50,
                        "output_tokens": 20,
                    },
                },
                self.dataset,
            ),
        ]

        summary = score_run.build_summary(scored)
        usage = summary["by_model"]["gpt-5.5-xhigh"]["normalized_usage"]

        self.assertEqual(usage["input_tokens"], 300)
        self.assertEqual(usage["output_tokens"], 30)
        self.assertAlmostEqual(usage["cost_usd"], 0.0020625)
        self.assertEqual(usage["cost_unknown_count"], 0)

    def test_checked_in_example_run_includes_v2_raw_aliases(self) -> None:
        example_path = REPO_ROOT / "runs" / "example-run.json"
        payload = json.loads(example_path.read_text(encoding="utf-8"))

        self.assertEqual(payload.get("schema_version"), "2.0.0")
        self.assertEqual(payload.get("suite_id"), "example")
        self.assertEqual(payload.get("case_count"), payload["question_count"])
        self.assertEqual(
            [item["case_id"] for item in payload["results"]],
            [item["id"] for item in payload["results"]],
        )

    def test_checked_in_scored_example_matches_v2_raw_aliases(self) -> None:
        scored_path = REPO_ROOT / "runs" / "example-run.scored.json"
        payload = json.loads(scored_path.read_text(encoding="utf-8"))

        self.assertEqual(payload.get("schema_version"), "2.0.0")
        self.assertEqual(payload["input_meta"]["schema_version"], "2.0.0")
        self.assertEqual(payload["input_meta"]["suite_id"], "example")
        self.assertEqual(payload["input_meta"]["case_count"], 4)
        self.assertEqual(payload["summary"]["suite_id"], "example")

    def test_score_record_emits_v2_identity_fields_for_legacy_input(self) -> None:
        scored = score_run.score_record({"id": "GG-01", "answer": "Drive there."}, self.dataset)

        self.assertEqual(scored["schema_version"], "2.0.0")
        self.assertEqual(scored["case_id"], "GG-01")
        self.assertEqual(scored["id"], "GG-01")

    def test_score_record_defaults_missing_model_for_v2_contract(self) -> None:
        scored = score_run.score_record({"id": "GG-01", "answer": "Drive there."}, self.dataset)

        self.assertEqual(scored["model"], "unknown")

    def test_summary_groups_scores_by_evaluation_mode(self) -> None:
        dataset = {
            "EX-01": {
                "id": "EX-01",
                "expected_answer": "Open the window.",
                "accepted_variants": ["Open it."],
            },
            "HY-01": {
                "id": "HY-01",
                "expected_answer": "Help directly.",
                "accepted_variants": ["Help directly."],
                "evaluation": {"mode": "hybrid", "dimensions": ["answer_correctness", "intent_alignment"]},
            },
            "RB-01": {
                "id": "RB-01",
                "expected_answer": "A helpful response.",
                "accepted_variants": ["A helpful response."],
                "evaluation": {"mode": "rubric", "dimensions": ["helpfulness"]},
            },
        }
        scored = [
            score_run.score_record({"id": "EX-01", "answer": "Open it."}, dataset),
            score_run.score_record({"id": "HY-01", "answer": "Wrong."}, dataset),
            score_run.score_record({"id": "RB-01", "answer": "A helpful response."}, dataset),
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_evaluation_mode"],
            {
                "exact": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 1,
                    "correct": 1,
                    "incorrect": 0,
                    "accuracy": 1.0,
                    "manual_review_required": 0,
                },
                "hybrid": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 1,
                    "correct": 0,
                    "incorrect": 1,
                    "accuracy": 0.0,
                    "manual_review_required": 1,
                },
                "rubric": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "accuracy": 0.0,
                    "manual_review_required": 1,
                },
            },
        )

    def test_summary_groups_scores_by_model(self) -> None:
        scored = [
            {
                "model": "gpt-5.4",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "model": "gpt-5.4",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "model": "sonnet-4.6",
                "answer": "needs review",
                "scoring_status": {
                    "score": None,
                    "dimensions": [{"status": "manual_review_required"}],
                },
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_model"],
            {
                "gpt-5.4": {
                    "total": 2,
                    "case_count": 2,
                    "auto_scored": 2,
                    "correct": 1,
                    "incorrect": 1,
                    "accuracy": 0.5,
                    "manual_review_required": 0,
                },
                "sonnet-4.6": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "accuracy": 0.0,
                    "manual_review_required": 1,
                },
            },
        )

    def test_summary_groups_scores_by_task_family(self) -> None:
        scored = [
            {
                "task_family_id": "goal-grounding",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "task_family_id": "goal-grounding",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "task_family_id": "social-pragmatics",
                "answer": "needs review",
                "scoring_status": {
                    "score": None,
                    "dimensions": [{"status": "manual_review_required"}],
                },
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_task_family"],
            {
                "goal-grounding": {
                    "total": 2,
                    "case_count": 2,
                    "auto_scored": 2,
                    "correct": 1,
                    "incorrect": 1,
                    "accuracy": 0.5,
                    "manual_review_required": 0,
                },
                "social-pragmatics": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "accuracy": 0.0,
                    "manual_review_required": 1,
                },
            },
        )

    def test_summary_groups_scores_by_failure_mode(self) -> None:
        scored = [
            {
                "failure_mode": "literal trap",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "failure_mode": "literal trap",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "failure_mode": "ambiguous instruction",
                "answer": "needs review",
                "scoring_status": {
                    "score": None,
                    "dimensions": [{"status": "manual_review_required"}],
                },
            },
            {
                "answer": "missing metadata",
                "scoring_status": {"score": 1, "dimensions": []},
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_failure_mode"],
            {
                "literal trap": {
                    "total": 2,
                    "case_count": 2,
                    "auto_scored": 2,
                    "correct": 1,
                    "incorrect": 1,
                    "accuracy": 0.5,
                    "manual_review_required": 0,
                },
                "ambiguous instruction": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "accuracy": 0.0,
                    "manual_review_required": 1,
                },
                "unknown": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 1,
                    "correct": 1,
                    "incorrect": 0,
                    "accuracy": 1.0,
                    "manual_review_required": 0,
                },
            },
        )

    def test_summary_groups_scores_by_ambiguity_type(self) -> None:
        scored = [
            {
                "ambiguity_type": "pragmatic",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "ambiguity_type": "pragmatic",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "ambiguity_type": "underspecified",
                "answer": "needs review",
                "scoring_status": {
                    "score": None,
                    "dimensions": [{"status": "manual_review_required"}],
                },
            },
            {
                "answer": "missing metadata",
                "scoring_status": {"score": 1, "dimensions": []},
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_ambiguity_type"],
            {
                "pragmatic": {
                    "total": 2,
                    "case_count": 2,
                    "auto_scored": 2,
                    "correct": 1,
                    "incorrect": 1,
                    "accuracy": 0.5,
                    "manual_review_required": 0,
                },
                "underspecified": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "accuracy": 0.0,
                    "manual_review_required": 1,
                },
                "unknown": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 1,
                    "correct": 1,
                    "incorrect": 0,
                    "accuracy": 1.0,
                    "manual_review_required": 0,
                },
            },
        )

    def test_summary_groups_scores_by_calibration_split(self) -> None:
        scored = [
            {
                "calibration_split": "starter",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "calibration_split": "starter",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "calibration_split": "holdout",
                "answer": "needs review",
                "scoring_status": {
                    "score": None,
                    "dimensions": [{"status": "manual_review_required"}],
                },
            },
            {
                "answer": "missing metadata",
                "scoring_status": {"score": 1, "dimensions": []},
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_calibration_split"],
            {
                "starter": {
                    "total": 2,
                    "case_count": 2,
                    "auto_scored": 2,
                    "correct": 1,
                    "incorrect": 1,
                    "accuracy": 0.5,
                    "manual_review_required": 0,
                },
                "holdout": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 0,
                    "correct": 0,
                    "incorrect": 0,
                    "accuracy": 0.0,
                    "manual_review_required": 1,
                },
                "full": {
                    "total": 1,
                    "case_count": 1,
                    "auto_scored": 1,
                    "correct": 1,
                    "incorrect": 0,
                    "accuracy": 1.0,
                    "manual_review_required": 0,
                },
            },
        )

    def test_summary_overall_includes_v2_case_count_alias(self) -> None:
        summary = score_run.build_summary(
            [
                {"answer": "right", "scoring_status": {"score": 1}},
                {"answer": "", "scoring_status": {"score": 0}},
            ]
        )

        self.assertEqual(summary["overall"]["case_count"], 2)
        self.assertEqual(summary["overall"]["question_count"], 2)

    def test_summary_answered_count_uses_configured_answer_field_trace(self) -> None:
        scored = [
            {
                "answer": "",
                "final_answer": "Open it.",
                "score_answer_normalized": {"answer": "Open it."},
                "scoring_status": {"score": 1, "answer_field": "final_answer"},
            }
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(summary["overall"]["answered_count"], 1)
        self.assertEqual(summary["overall"]["missing_count"], 0)

    def test_summary_includes_v2_schema_version(self) -> None:
        summary = score_run.build_summary([])

        self.assertEqual(summary["schema_version"], "2.0.0")

    def test_output_payload_summary_includes_v2_report_identity(self) -> None:
        output = score_run.build_output_payload(
            {"benchmark": "reasoning-benchmark", "run_mode": "smoke"},
            [],
            str(score_run.DEFAULT_DATASET_PATH),
            "runs/example-run.json",
            source_bundles=["runs/baseline/gpt-5-4.smoke.manifest.json"],
        )

        summary = output["summary"]
        self.assertEqual(summary["benchmark"], "reasoning-benchmark")
        self.assertEqual(summary["suite_id"], "smoke")
        self.assertEqual(summary["source_bundles"], ["runs/baseline/gpt-5-4.smoke.manifest.json"])
        self.assertIsInstance(summary["generated_at"], str)
        self.assertTrue(summary["generated_at"])

    def test_summary_breakdown_buckets_include_v2_case_count_alias(self) -> None:
        summary = score_run.build_summary(
            [
                {
                    "model": "gpt-5.4",
                    "evaluation_mode": "hybrid",
                    "task_family_id": "social-pragmatics",
                    "failure_mode": "literalism",
                    "ambiguity_type": "pragmatic",
                    "calibration_split": "starter",
                    "answer": "right",
                    "scoring_status": {"score": 1, "dimensions": []},
                },
                {
                    "model": "gpt-5.4",
                    "evaluation_mode": "hybrid",
                    "task_family_id": "social-pragmatics",
                    "failure_mode": "literalism",
                    "ambiguity_type": "pragmatic",
                    "calibration_split": "starter",
                    "answer": "wrong",
                    "scoring_status": {"score": 0, "dimensions": []},
                },
            ]
        )

        buckets = [
            summary["by_model"]["gpt-5.4"],
            summary["by_evaluation_mode"]["hybrid"],
            summary["by_task_family"]["social-pragmatics"],
            summary["by_failure_mode"]["literalism"],
            summary["by_ambiguity_type"]["pragmatic"],
            summary["by_calibration_split"]["starter"],
        ]
        for bucket in buckets:
            self.assertEqual(bucket["case_count"], 2)
            self.assertEqual(bucket["total"], 2)

    def test_summary_emits_v2_manual_review_aggregate(self) -> None:
        scored = [
            {
                "answer": "right",
                "score_reasoning": 3,
                "score_constraint_extraction": None,
                "notes": "",
                "scoring_status": {
                    "score": 1,
                    "heuristic_flags": [
                        {"name": "normalized_punctuation", "is_heuristic": True},
                        {"name": "exact", "is_heuristic": False},
                    ],
                },
            },
            {
                "answer": "needs review",
                "score_reasoning": None,
                "score_constraint_extraction": 2,
                "notes": "Check intent alignment.",
                "scoring_status": {"score": None, "heuristic_flags": []},
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["manual_review"],
            {
                "reasoning_scores_present": 1,
                "constraint_scores_present": 1,
                "notes_present": 1,
                "heuristic_flags_total": 1,
            },
        )
        self.assertEqual(summary["manual_review"], summary["manual_only"])

    def test_summary_manual_only_and_manual_review_are_independent(self) -> None:
        scored = [
            {
                "answer": "right",
                "score_reasoning": 3,
                "scoring_status": {"score": 1, "heuristic_flags": []},
            },
        ]

        summary = score_run.build_summary(scored)

        summary["manual_only"]["reasoning_scores_present"] = 999

        self.assertEqual(summary["manual_review"]["reasoning_scores_present"], 1)

    def test_summary_cross_tabs_models_against_task_family(self) -> None:
        scored = [
            {
                "model": "gpt-5.4",
                "task_family_id": "social-pragmatics",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "model": "gpt-5.4",
                "task_family_id": "social-pragmatics",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "model": "gpt-5.4",
                "task_family_id": "goal-grounding",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "model": "sonnet-4.6",
                "task_family_id": "social-pragmatics",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "model": "sonnet-4.6",
                "task_family_id": "social-pragmatics",
                "answer": "needs review",
                "scoring_status": {
                    "score": None,
                    "dimensions": [{"status": "manual_review_required"}],
                },
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_model_task_family"],
            {
                "gpt-5.4": {
                    "social-pragmatics": {
                        "total": 2,
                        "case_count": 2,
                        "auto_scored": 2,
                        "correct": 1,
                        "incorrect": 1,
                        "accuracy": 0.5,
                        "manual_review_required": 0,
                    },
                    "goal-grounding": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 1,
                        "correct": 1,
                        "incorrect": 0,
                        "accuracy": 1.0,
                        "manual_review_required": 0,
                    },
                },
                "sonnet-4.6": {
                    "social-pragmatics": {
                        "total": 2,
                        "case_count": 2,
                        "auto_scored": 1,
                        "correct": 1,
                        "incorrect": 0,
                        "accuracy": 1.0,
                        "manual_review_required": 1,
                    },
                },
            },
        )

    def test_summary_cross_tabs_models_against_failure_mode(self) -> None:
        scored = [
            {
                "model": "gpt-5.4",
                "failure_mode": "literalism",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "model": "gpt-5.4",
                "failure_mode": "literalism",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "model": "sonnet-4.6",
                "failure_mode": "literalism",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_model_failure_mode"],
            {
                "gpt-5.4": {
                    "literalism": {
                        "total": 2,
                        "case_count": 2,
                        "auto_scored": 2,
                        "correct": 1,
                        "incorrect": 1,
                        "accuracy": 0.5,
                        "manual_review_required": 0,
                    },
                },
                "sonnet-4.6": {
                    "literalism": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 1,
                        "correct": 1,
                        "incorrect": 0,
                        "accuracy": 1.0,
                        "manual_review_required": 0,
                    },
                },
            },
        )

    def test_summary_cross_tabs_models_against_ambiguity_type(self) -> None:
        scored = [
            {
                "model": "gpt-5.4",
                "ambiguity_type": "pragmatic",
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            },
            {
                "model": "gpt-5.4",
                "ambiguity_type": "none",
                "answer": "wrong",
                "scoring_status": {"score": 0, "dimensions": []},
            },
            {
                "model": "sonnet-4.6",
                "ambiguity_type": "pragmatic",
                "answer": "needs review",
                "scoring_status": {
                    "score": None,
                    "dimensions": [{"status": "manual_review_required"}],
                },
            },
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_model_ambiguity_type"],
            {
                "gpt-5.4": {
                    "pragmatic": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 1,
                        "correct": 1,
                        "incorrect": 0,
                        "accuracy": 1.0,
                        "manual_review_required": 0,
                    },
                    "none": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 1,
                        "correct": 0,
                        "incorrect": 1,
                        "accuracy": 0.0,
                        "manual_review_required": 0,
                    },
                },
                "sonnet-4.6": {
                    "pragmatic": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 0,
                        "correct": 0,
                        "incorrect": 0,
                        "accuracy": 0.0,
                        "manual_review_required": 1,
                    },
                },
            },
        )

    def test_summary_cross_tabs_use_unknown_for_missing_metadata(self) -> None:
        scored = [
            {
                "answer": "right",
                "scoring_status": {"score": 1, "dimensions": []},
            }
        ]

        summary = score_run.build_summary(scored)

        self.assertEqual(
            summary["by_model_task_family"],
            {
                "unknown": {
                    "unknown": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 1,
                        "correct": 1,
                        "incorrect": 0,
                        "accuracy": 1.0,
                        "manual_review_required": 0,
                    },
                },
            },
        )
        self.assertEqual(
            summary["by_model_failure_mode"],
            {
                "unknown": {
                    "unknown": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 1,
                        "correct": 1,
                        "incorrect": 0,
                        "accuracy": 1.0,
                        "manual_review_required": 0,
                    },
                },
            },
        )
        self.assertEqual(
            summary["by_model_ambiguity_type"],
            {
                "unknown": {
                    "unknown": {
                        "total": 1,
                        "case_count": 1,
                        "auto_scored": 1,
                        "correct": 1,
                        "incorrect": 0,
                        "accuracy": 1.0,
                        "manual_review_required": 0,
                    },
                },
            },
        )


class ScoreToFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = CURRENT_DIR / "tmp" / "score-to-file"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        for item in self.tmp_dir.glob("*.json"):
            item.unlink()

    def test_score_to_file_writes_scored_artifact(self) -> None:
        dataset_path = self.tmp_dir / "dataset.json"
        dataset_path.write_text(
            json.dumps(
                [
                    {
                        "id": "GG-01",
                        "prompt": "Is the sky blue?",
                        "expected_answer": "yes",
                        "accepted_variants": [],
                    }
                ]
            ),
            encoding="utf-8",
        )

        input_path = self.tmp_dir / "raw.json"
        input_path.write_text(
            json.dumps(
                {
                    "input_meta": {"benchmark": "reasoning-benchmark", "suite_id": "smoke"},
                    "results": [{"id": "GG-01", "answer": "yes"}],
                }
            ),
            encoding="utf-8",
        )

        output_path = self.tmp_dir / "scored.json"
        score_run.score_to_file(
            input_path=input_path,
            output_path=output_path,
            dataset_path=dataset_path,
        )

        scored = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(scored["schema_version"], "2.0.0")
        self.assertEqual(scored["summary"]["auto_scored"]["correct"], 1)
        self.assertEqual(len(scored["results"]), 1)


if __name__ == "__main__":
    unittest.main()
