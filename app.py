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
parser_version = 4
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

index = st.session_state["question_index"]
if index >= len(questions):
    st.success(f"Quiz complete! Your score: {st.session_state['score']} / {len(questions)}")
    if st.button("Start again"):
        st.session_state["question_index"] = 0
        st.session_state["score"] = 0
        st.session_state["submitted"] = False
        st.rerun()
    st.stop()

question = questions[index]
st.progress((index + 1) / len(questions), text=f"Question {index + 1} of {len(questions)}")
st.subheader(question.prompt)

with st.form(key=f"answer_form_{pdf_id}_{index}"):
    if len(question.answers) == 1:
        selected = st.radio(
            "Choose one answer:",
            options=list(question.options),
            index=None,
            format_func=lambda label: f"{label}. {question.options[label]}",
            key=f"answer_{pdf_id}_{index}",
        )
    else:
        st.write(f"Choose all {len(question.answers)} correct answers:")
        selected = [
            label
            for label, option_text in question.options.items()
            if st.checkbox(
                f"{label}. {option_text}",
                key=f"answer_{pdf_id}_{index}_{label}",
            )
        ]
    submitted = st.form_submit_button("Check answer")

if submitted and not st.session_state["submitted"]:
    if isinstance(selected, str):
        selected_labels = {selected}
    else:
        selected_labels = set(selected or [])
    if not selected_labels:
        st.warning("Choose at least one answer before checking.")
    else:
        st.session_state["selected_labels"] = selected_labels
        st.session_state["is_correct"] = selected_labels == set(question.answers)
        if st.session_state["is_correct"]:
            st.session_state["score"] += 1
        st.session_state["submitted"] = True

if st.session_state["submitted"]:
    if st.session_state["is_correct"]:
        st.success("Correct!")
    else:
        st.error("Not quite.")

    correct_labels = ", ".join(sorted(question.answers))
    correct_text = "; ".join(
        f"{label}. {question.options[label]}" for label in sorted(question.answers)
    )
    st.markdown(f"**Correct answer:** {correct_labels} — {correct_text}")
    st.markdown(f"**Explanation:** {question.explanation or 'No explanation was provided in the PDF.'}")

    if st.button("Finish quiz" if index == len(questions) - 1 else "Next question"):
        st.session_state["question_index"] += 1
        st.session_state["submitted"] = False
        st.rerun()

with st.expander("About supported PDFs"):
    st.write(
        "Questions should be numbered, choices labeled A), B), etc., and answers "
        "introduced by “Correct Answer:” or “Correct Answers:”. Explanations should "
        "start with “Explanation:”. See the README for examples."
    )
