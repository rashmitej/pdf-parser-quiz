import unittest
import json
from io import BytesIO
from unittest.mock import patch

from ollama_parser import (
    repair_skipped_questions_with_ollama,
)
from quiz_parser import parse_questions


class ParseQuestionsTests(unittest.TestCase):
    def test_parses_single_and_multiple_answer_questions(self) -> None:
        text = """
        Question 1: Which is correct?
        A) First
        B) Second
        Correct Answer: B
        Explanation: The second choice is correct.

        Question 2: Choose both correct choices.
        A) Alpha
        B) Beta
        C) Gamma
        Correct Answers: A, C
        Explanation: Alpha and gamma are correct.
        """

        result = parse_questions(text)

        self.assertEqual(len(result.questions), 2)
        self.assertEqual(result.questions[0].answers, frozenset({"B"}))
        self.assertEqual(result.questions[0].explanation, "The second choice is correct.")
        self.assertEqual(result.questions[1].answers, frozenset({"A", "C"}))
        self.assertEqual(result.questions[1].options["C"], "Gamma")
        self.assertEqual(result.warnings, [])

    def test_skips_question_when_answer_does_not_match_choices(self) -> None:
        text = """
        Question 1: Which choice?
        A) First
        B) Second
        Correct Answer: C
        """

        result = parse_questions(text)

        self.assertEqual(result.questions, [])
        self.assertIn("do not match any choices", result.warnings[0])

    def test_parses_five_lowercase_choices_with_two_correct_answers(self) -> None:
        text = """
        Question 1: Select two correct answers.
        a) Alpha
        b) Beta
        c) Gamma
        d) Delta
        e) Epsilon
        Correct Answers: b, e
        Explanation: Beta and epsilon are correct.
        """

        result = parse_questions(text)

        self.assertEqual(len(result.questions), 1)
        self.assertEqual(
            list(result.questions[0].options),
            ["A", "B", "C", "D", "E"],
        )
        self.assertEqual(result.questions[0].answers, frozenset({"B", "E"}))
        self.assertEqual(result.warnings, [])

    def test_parses_pdf_question_colon_heading_and_compact_answer_labels(self) -> None:
        text = """
        Question: 4

        A data mesh needs analytics and centralized governance.
        Which combination of services will implement it? (Choose two.)

        A. Use Amazon Aurora for data storage.
        B. Use Amazon S3 for data storage and Amazon Athena for analysis.
        C. Use AWS Glue DataBrew for governance.
        D. Use Amazon RDS and Amazon EMR.
        E. Use AWS Lake Formation for governance.

        Answer: BE
        Explanation:
        B and E are correct because they provide analytics and governance.
        """

        result = parse_questions(text)

        self.assertEqual(len(result.questions), 1)
        self.assertIn("Amazon S3", result.questions[0].options["B"])
        self.assertEqual(result.questions[0].answers, frozenset({"B", "E"}))
        self.assertIn("provide analytics and governance", result.questions[0].explanation)
        self.assertEqual(result.warnings, [])

    def test_parses_all_questions_including_questions_after_ten(self) -> None:
        question_blocks = [
            f"""Question {number}: Prompt {number}?
A) First
B) Second
Correct Answer: A"""
            for number in range(1, 13)
        ]

        result = parse_questions("\n".join(question_blocks))

        self.assertEqual(len(result.questions), 12)
        self.assertEqual(result.questions[0].prompt, "Prompt 1?")
        self.assertEqual(result.questions[-1].prompt, "Prompt 12?")
        self.assertTrue(any(question.prompt == "Prompt 11?" for question in result.questions))

    def test_reports_duplicate_choice_labels(self) -> None:
        text = """
        Question 1: Which choice?
        A) First
        A) Duplicate
        B) Second
        Correct Answer: A
        """

        result = parse_questions(text)

        self.assertEqual(result.questions[0].options["A"], "First")
        self.assertTrue(any("duplicate choice label A" in warning for warning in result.warnings))

    def test_reports_when_no_numbered_questions_exist(self) -> None:
        result = parse_questions("This PDF has no quiz content.")

        self.assertEqual(result.questions, [])
        self.assertTrue(any("No numbered questions" in warning for warning in result.warnings))

    @patch("ollama_parser.urlopen")
    def test_local_model_repairs_skipped_question_in_document_order(self, mock_urlopen) -> None:
        model_question = {
            "question_number": 2,
            "prompt": "Choose the correct answer.",
            "options": {"A": "First", "B": "Second"},
            "correct_answers": ["B"],
            "explanation": "The second choice is correct.",
        }
        mock_urlopen.return_value = BytesIO(
            json.dumps(
                {"message": {"content": json.dumps(model_question)}}
            ).encode()
        )
        text = """
        Question: 1
        A complete question?
        A. First
        B. Second
        Answer: A

        Question: 2
        Choose the correct answer.
        A. First
        Answer: B
        """
        progress: list[tuple[int, int]] = []

        result = repair_skipped_questions_with_ollama(
            text,
            progress_callback=lambda completed, total: progress.append((completed, total)),
        )

        self.assertEqual(result.repaired_count, 1)
        self.assertEqual([question.answers for question in result.parse_result.questions],
                         [frozenset({"A"}), frozenset({"B"})])
        self.assertEqual(result.parse_result.warnings, [])
        self.assertEqual(progress, [(1, 1)])
        request = mock_urlopen.call_args.args[0]
        self.assertIn("localhost:11434/api/chat", request.full_url)

    @patch("ollama_parser.urlopen")
    def test_local_model_rejects_answer_label_not_in_options(self, mock_urlopen) -> None:
        invalid_question = {
            "question_number": 1,
            "prompt": "Choose one.",
            "options": {"A": "First", "B": "Second"},
            "correct_answers": ["C"],
            "explanation": "Explanation.",
        }
        mock_urlopen.return_value = BytesIO(
            json.dumps(
                {"message": {"content": json.dumps(invalid_question)}}
            ).encode()
        )

        result = repair_skipped_questions_with_ollama(
            """Question: 1
            Choose one.
            A. First
            Answer: C""",
        )

        self.assertEqual(result.parse_result.questions, [])
        self.assertTrue(
            any("do not match the choices" in warning for warning in result.parse_result.warnings)
        )

    @patch("ollama_parser.urlopen")
    def test_local_model_must_match_answer_key_in_pdf(self, mock_urlopen) -> None:
        extracted_question = {
            "question_number": 1,
            "prompt": "Choose one.",
            "options": {"A": "First", "B": "Second"},
            "correct_answers": ["A"],
            "explanation": "The first choice is correct.",
        }
        mock_urlopen.return_value = BytesIO(
            json.dumps(
                {"message": {"content": json.dumps(extracted_question)}}
            ).encode()
        )

        result = repair_skipped_questions_with_ollama(
            """Question: 1
            Choose one.
            A. First
            Answer: B""",
        )

        self.assertEqual(result.parse_result.questions, [])
        self.assertTrue(
            any("does not match the answer key" in warning
                for warning in result.parse_result.warnings)
        )


if __name__ == "__main__":
    unittest.main()
