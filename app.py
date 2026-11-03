import hashlib
from io import BytesIO

import fitz
import streamlit as st

from ollama_parser import OllamaParserError, repair_skipped_questions_with_ollama
from quiz_parser import QuizQuestion, parse_questions


st.set_page_config(page_title="PDF Quiz", page_icon="📝", layout="centered")
st.title("PDF Quiz")
st.write("Upload a quiz PDF, answer one question at a time, and get feedback with explanations.")

uploaded_pdf = st.file_uploader("Choose a PDF file", type=["pdf"])
if uploaded_pdf is None:
    st.info("Upload a text-based PDF that includes each question, its choices, the correct answer, and an explanation.")
    st.stop()

with st.sidebar:
    parser_mode = st.selectbox(
        "PDF parser",
        ["Text parser", "Local AI repair (Ollama)"],
        help="Local AI sends only incomplete question text to an Ollama model running on this computer.",
    )
    ollama_model = "qwen2.5:7b"
    if parser_mode == "Local AI repair (Ollama)":
        ollama_model = st.text_input("Ollama model", value=ollama_model).strip()

pdf_bytes = uploaded_pdf.getvalue()
pdf_id = hashlib.sha256(pdf_bytes).hexdigest()
parser_version = 5
parser_config = (parser_mode, ollama_model)
if (
    st.session_state.get("pdf_id") != pdf_id
    or st.session_state.get("parser_version") != parser_version
    or st.session_state.get("parser_config") != parser_config
):
    st.session_state["pdf_id"] = pdf_id
    st.session_state["parser_version"] = parser_version
    st.session_state["parser_config"] = parser_config
    st.session_state["questions"] = None
    st.session_state["warnings"] = []
    st.session_state["ai_repaired_count"] = 0
    st.session_state["question_index"] = 0
    st.session_state["score"] = 0
    st.session_state["submitted"] = False
    st.session_state["question_states"] = {}
    st.session_state["review_page"] = False

if st.session_state["questions"] is None:
    try:
        with fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf") as document:
            pdf_text = "\n".join(page.get_text(sort=True) for page in document)
    except (fitz.FileDataError, RuntimeError) as error:
        st.error(f"Could not read this PDF: {error}")
        st.stop()

    if not pdf_text.strip():
        st.error("No selectable text was found. Scanned PDFs need OCR before they can be used.")
        st.stop()

    if parser_mode == "Local AI repair (Ollama)":
        progress = st.progress(0, text="Checking for incomplete questions...")

        def update_parse_progress(completed: int, total: int) -> None:
            progress.progress(
                completed / total,
                text=f"Local AI repairing skipped questions ({completed}/{total})",
            )

        try:
            with st.spinner("Parsing with the local Ollama model. This may take a while."):
                ai_result = repair_skipped_questions_with_ollama(
                    pdf_text,
                    model=ollama_model or "qwen2.5:7b",
                    progress_callback=update_parse_progress,
                )
        except OllamaParserError as error:
            progress.empty()
            st.error(str(error))
            st.info(
                f"Install Ollama, then run `ollama pull {ollama_model or 'qwen2.5:7b'}` "
                "in PowerShell. "
                "Keep Ollama running and upload the PDF again."
            )
            st.stop()
        progress.empty()
        result = ai_result.parse_result
        st.session_state["ai_repaired_count"] = ai_result.repaired_count
    else:
        result = parse_questions(pdf_text)

    st.session_state["questions"] = result.questions
    st.session_state["warnings"] = result.warnings
    st.session_state["question_index"] = 0
    st.session_state["score"] = 0
    st.session_state["submitted"] = False
    st.session_state["question_states"] = {}
    st.session_state["review_page"] = False

questions: list[QuizQuestion] = st.session_state["questions"]
if st.session_state["ai_repaired_count"]:
    st.info(
        f"Local AI recovered {st.session_state['ai_repaired_count']} questions "
        "that the text parser could not read."
    )
for warning in st.session_state["warnings"]:
    st.warning(warning)

if not questions:
    st.error("No complete questions could be read from this PDF. Check the supported layout below.")
    with st.expander("Supported PDF layout"):
        st.markdown(
            """
            ```text
            Question 1: What is the answer?
            A) First choice
            B) Second choice
            C) Third choice
            Correct Answer: B
            Explanation: The second choice is correct because ...
            ```

            Use `Correct Answers: A, C` for questions with multiple correct choices.
            Numbered headings such as `1.` are also supported. Each question must have
            at least two labeled choices and a correct answer label.
            """
        )
    st.stop()

question_states: dict[int, dict[str, object]] = st.session_state["question_states"]
st.session_state["score"] = sum(
    state.get("status") == "correct" for state in question_states.values()
)

if st.session_state["review_page"]:
    all_reviewed = all(
        question_states.get(index, {}).get("status") in ("correct", "missed", "skipped")
        for index in range(len(questions))
    )
    review_message = f"Your score: {st.session_state['score']} / {len(questions)}"
    if all_reviewed:
        st.success(f"Quiz complete! {review_message}")
    else:
        st.info(f"Quiz review. {review_message}")
    st.subheader("Review and reattempt")
    st.write("Choose any question below to review it and try it again.")

    review_groups = (
        ("Correct", "correct"),
        ("Missed", "missed"),
        ("Skipped", "skipped"),
        ("Not yet answered", "unanswered"),
    )
    for heading, status in review_groups:
        matching = [
            index
            for index in range(len(questions))
            if question_states.get(index, {}).get("status", "unanswered") == status
        ]
        if not matching:
            continue
        st.markdown(f"### {heading} ({len(matching)})")
        for index in matching:
            question = questions[index]
            state = question_states.get(index, {})
            with st.expander(f"Question {index + 1}: {question.prompt}"):
                if state.get("status") in ("correct", "missed"):
                    selected_labels = state.get("selected_labels", set())
                    st.write(f"Your answer: {', '.join(sorted(selected_labels)) or 'None'}")
                correct_labels = ", ".join(sorted(question.answers))
                correct_text = "; ".join(
                    f"{label}. {question.options[label]}"
                    for label in sorted(question.answers)
                )
                st.markdown(f"**Correct answer:** {correct_labels} — {correct_text}")
                st.markdown(
                    f"**Explanation:** "
                    f"{question.explanation or 'No explanation was provided in the PDF.'}"
                )
                if st.button("Reattempt this question", key=f"reattempt_{pdf_id}_{index}"):
                    question_states.pop(index, None)
                    attempts = st.session_state.setdefault("attempt_numbers", {})
                    attempts[index] = attempts.get(index, 0) + 1
                    st.session_state["question_index"] = index
                    st.session_state["review_page"] = False
                    st.rerun()

    if st.button("Start quiz again"):
        st.session_state["question_states"] = {}
        st.session_state["attempt_numbers"] = {}
        st.session_state["question_index"] = 0
        st.session_state["review_page"] = False
        st.rerun()
    st.stop()

index = st.session_state["question_index"]
question = questions[index]
state = question_states.get(index, {})
attempt = st.session_state.setdefault("attempt_numbers", {}).get(index, 0)
st.progress((index + 1) / len(questions), text=f"Question {index + 1} of {len(questions)}")
st.subheader(question.prompt)

if state.get("status") in ("correct", "missed"):
    selected_labels = state.get("selected_labels", set())
    if state["status"] == "correct":
        st.success("Correct!")
    else:
        st.error("Not quite.")
    st.markdown(f"**Your answer:** {', '.join(sorted(selected_labels))}")
    correct_labels = ", ".join(sorted(question.answers))
    correct_text = "; ".join(
        f"{label}. {question.options[label]}" for label in sorted(question.answers)
    )
    st.markdown(f"**Correct answer:** {correct_labels} — {correct_text}")
    st.markdown(f"**Explanation:** {question.explanation or 'No explanation was provided in the PDF.'}")
elif state.get("status") == "skipped":
    st.info("This question was skipped. You can answer it now or continue.")

if state.get("status") not in ("correct", "missed"):
    with st.form(key=f"answer_form_{pdf_id}_{index}_{attempt}"):
        if len(question.answers) == 1:
            selected = st.radio(
                "Choose one answer:",
                options=list(question.options),
                index=None,
                format_func=lambda label: f"{label}. {question.options[label]}",
                key=f"answer_{pdf_id}_{index}_{attempt}",
            )
        else:
            st.write(f"Choose all {len(question.answers)} correct answers:")
            selected = [
                label
                for label, option_text in question.options.items()
                if st.checkbox(
                    f"{label}. {option_text}",
                    key=f"answer_{pdf_id}_{index}_{attempt}_{label}",
                )
            ]
        submitted = st.form_submit_button("Check answer")

    if submitted:
        if isinstance(selected, str):
            selected_labels = {selected}
        else:
            selected_labels = set(selected or [])
        if not selected_labels:
            st.warning("Choose at least one answer before checking.")
        else:
            is_correct = selected_labels == set(question.answers)
            question_states[index] = {
                "status": "correct" if is_correct else "missed",
                "selected_labels": selected_labels,
            }
            st.session_state["score"] = sum(
                item.get("status") == "correct" for item in question_states.values()
            )
            st.rerun()

navigation = st.columns(4)
if navigation[0].button("Back", disabled=index == 0):
    st.session_state["question_index"] = index - 1
    st.rerun()
if navigation[1].button("Skip"):
    if question_states.get(index, {}).get("status", "unanswered") in ("unanswered", "skipped"):
        question_states[index] = {"status": "skipped", "selected_labels": set()}
    if index == len(questions) - 1:
        st.session_state["review_page"] = True
    else:
        st.session_state["question_index"] = index + 1
    st.rerun()
if navigation[2].button("Next question", disabled=index == len(questions) - 1):
    if question_states.get(index, {}).get("status", "unanswered") == "unanswered":
        question_states[index] = {"status": "skipped", "selected_labels": set()}
    st.session_state["question_index"] = index + 1
    st.rerun()
if navigation[3].button("Review answers"):
    st.session_state["review_page"] = True
    st.rerun()

with st.expander("About supported PDFs"):
    st.write(
        "Questions should be numbered, choices labeled A), B), etc., and answers "
        "introduced by “Correct Answer:” or “Correct Answers:”. Explanations should "
        "start with “Explanation:”. See the README for examples."
    )
