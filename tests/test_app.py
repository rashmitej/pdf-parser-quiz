import unittest
from pathlib import Path

import pymupdf
from streamlit.testing.v1 import AppTest


class QuizAppTests(unittest.TestCase):
    def click_button(self, app: AppTest, label: str, occurrence: int = 0) -> None:
        matching = [button for button in app.button if button.label == label]
        matching[occurrence].click().run()

    def test_pdf_questions_are_read_in_visual_order(self) -> None:
        pdf = pymupdf.open()
        page = pdf.new_page()
        page.insert_textbox(
            pymupdf.Rect(40, 400, 550, 750),
            """Question: 2
Second question?
A. Second choice
B. Another choice
Answer: B
Explanation: Second explanation.""",
        )
        page.insert_textbox(
            pymupdf.Rect(40, 40, 550, 350),
            """Question: 1
First question?
A. First choice
B. Another choice
Answer: A
Explanation: First explanation.""",
        )

        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_path)).run()
        app.file_uploader[0].set_value(("quiz.pdf", pdf.tobytes(), "application/pdf")).run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.subheader[0].value, "First question?")
        self.assertEqual(len(app.session_state["questions"]), 2)
        self.assertEqual(app.session_state["questions"][1].prompt, "Second question?")

    def test_upload_answer_feedback_and_score(self) -> None:
        pdf = pymupdf.open()
        pdf.new_page().insert_textbox(
            pymupdf.Rect(40, 40, 550, 750),
            """Question 1: Choose one answer.
A) Alpha
B) Beta
Correct Answer: B
Explanation: Beta is correct.

Question 2: Choose both answers.
A) First
B) Second
C) Third
D) Fourth
E) Fifth
Correct Answers: B, E
Explanation: Second and fifth are correct.""",
        )
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_path)).run()
        app.file_uploader[0].set_value(("quiz.pdf", pdf.tobytes(), "application/pdf")).run()

        self.assertEqual(len(app.exception), 0)
        self.assertIsNone(app.radio[0].value)
        app.button[0].click().run()
        self.assertTrue(any("Choose at least one answer" in item.value for item in app.warning))

        app.radio[0].set_value("B")
        app.button[0].click().run()
        self.assertTrue(any(item.value == "Correct!" for item in app.success))
        self.assertTrue(any("Beta is correct." in item.value for item in app.markdown))

        app.button[1].click().run()
        self.assertEqual(len(app.checkbox), 5)
        self.assertTrue(any("Choose all 2 correct answers" in item.value for item in app.markdown))
        app.checkbox[1].set_value(True)
        app.checkbox[4].set_value(True)
        app.button[0].click().run()
        self.assertTrue(any(item.value == "Correct!" for item in app.success))
        self.assertEqual(app.session_state["score"], 2)

        app.button[1].click().run()
        self.assertTrue(
            any("Quiz complete! Your score: 2 / 2" in item.value for item in app.success)
        )

    def test_wrong_answer_shows_correct_answer_and_explanation(self) -> None:
        pdf = pymupdf.open()
        pdf.new_page().insert_textbox(
            pymupdf.Rect(40, 40, 550, 750),
            """Question 1: Which choice is correct?
A) Alpha
B) Beta
Correct Answer: B
Explanation: Beta matches the rule.""",
        )
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_path)).run()
        app.file_uploader[0].set_value(("quiz.pdf", pdf.tobytes(), "application/pdf")).run()
        app.radio[0].set_value("A")
        app.button[0].click().run()

        self.assertTrue(any(item.value == "Not quite." for item in app.error))
        self.assertTrue(
            any("Correct answer:** B — B. Beta" in item.value for item in app.markdown)
        )
        self.assertTrue(any("Beta matches the rule." in item.value for item in app.markdown))

    def test_back_skip_review_and_reattempt(self) -> None:
        pdf = pymupdf.open()
        pdf.new_page().insert_textbox(
            pymupdf.Rect(40, 40, 550, 750),
            """Question 1: Which answer is correct?
A) Alpha
B) Beta
Correct Answer: B
Explanation: Beta is correct.

Question 2: Which answer is correct?
A) First
B) Second
Correct Answer: A
Explanation: First is correct.""",
        )
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        app = AppTest.from_file(str(app_path)).run()
        app.file_uploader[0].set_value(("quiz.pdf", pdf.tobytes(), "application/pdf")).run()

        app.radio[0].set_value("A")
        self.click_button(app, "Check answer")
        self.assertEqual(app.session_state["question_states"][0]["status"], "missed")

        self.click_button(app, "Next question")
        self.assertEqual(app.session_state["question_index"], 1)
        self.click_button(app, "Back")
        self.assertEqual(app.session_state["question_index"], 0)
        self.assertTrue(any(item.value == "Not quite." for item in app.error))

        self.click_button(app, "Next question")
        self.click_button(app, "Skip")
        self.assertTrue(app.session_state["review_page"])
        self.assertTrue(any("Missed (1)" in item.value for item in app.markdown))
        self.assertTrue(any("Skipped (1)" in item.value for item in app.markdown))

        self.click_button(app, "Reattempt this question")
        self.assertEqual(app.session_state["question_index"], 0)
        self.assertFalse(app.session_state["review_page"])
        app.radio[0].set_value("B")
        self.click_button(app, "Check answer")
        self.assertEqual(app.session_state["question_states"][0]["status"], "correct")
        self.assertEqual(app.session_state["score"], 1)


if __name__ == "__main__":
    unittest.main()
