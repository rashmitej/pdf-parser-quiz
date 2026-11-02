import re
from dataclasses import dataclass, field


_QUESTION_HEADER = re.compile(
    r"^\s*(?:question\s*:?\s*|q\s*)(\d+)\s*[:.)-]?\s*(.*)$",
    re.IGNORECASE,
)
_NUMBERED_HEADER = re.compile(r"^\s*(\d+)\s*[.)]\s*(.*)$")
_OPTION = re.compile(r"^\s*(?:\(([A-Z])\)|([A-Z])[.)])\s*(.*?)\s*$", re.IGNORECASE)
_ANSWER = re.compile(
    r"^\s*(?:(?:correct\s+)?answers?|correct\s+(?:options?|choices?))\s*[:\-]\s*(.*?)\s*$",
    re.IGNORECASE,
)
_EXPLANATION = re.compile(
    r"^\s*(?:explanation|rationale|why)\s*[:\-]\s*(.*?)\s*$",
    re.IGNORECASE,
)
@dataclass(frozen=True)
class QuizQuestion:
    prompt: str
    options: dict[str, str]
    answers: frozenset[str]
    explanation: str


@dataclass(frozen=True)
class ParseResult:
    questions: list[QuizQuestion]
    warnings: list[str]


@dataclass
class _QuestionBuilder:
    prompt: list[str] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)
    answer: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)


def parse_questions(text: str) -> ParseResult:
    """Parse numbered multiple-choice questions with labeled answers and explanations."""
    questions: list[QuizQuestion] = []
    warnings: list[str] = []
    current: _QuestionBuilder | None = None
    section = "prompt"
    header_style: str | None = None

    def finish_question(question: _QuestionBuilder, number: int) -> None:
        prompt = " ".join(question.prompt).strip()
        answer_text = " ".join(question.answer).strip()
        explanation = " ".join(question.explanation).strip()
        answer_labels_found: set[str] = set()
        for token in re.findall(r"[A-Z]+", answer_text.upper()):
            if token in question.options:
                answer_labels_found.add(token)
            elif len(token) == 1:
                answer_labels_found.add(token)
            elif len(token) > 1 and all(label in question.options for label in token):
                answer_labels_found.update(token)
        answer_labels = frozenset(answer_labels_found)

        problems: list[str] = []
        if not prompt:
            problems.append("question text is missing")
        if len(question.options) < 2:
            problems.append("fewer than two answer choices were found")
        if not answer_labels:
            problems.append("correct answer label is missing")
        elif not answer_labels.issubset(question.options):
            unknown = ", ".join(sorted(answer_labels - question.options.keys()))
            problems.append(f"answer label(s) {unknown} do not match any choices")

        if problems:
            warnings.append(f"Question {number} was skipped: {', '.join(problems)}.")
            return

        questions.append(
            QuizQuestion(
                prompt=prompt,
                options=dict(question.options),
                answers=answer_labels,
                explanation=explanation,
            )
        )

    question_number: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        header_match = _QUESTION_HEADER.match(line)
        if header_match:
            header_style = "explicit"
            number_text = header_match.group(1)
            prompt = header_match.group(2) or ""
        else:
            header_match = _NUMBERED_HEADER.match(line) if header_style != "explicit" else None
            if header_match:
                header_style = "numbered"
                number_text = header_match.group(1)
                prompt = header_match.group(2)

        if header_match:
            if current is not None and question_number is not None:
                finish_question(current, question_number)
            question_number = int(number_text)
            current = _QuestionBuilder()
            section = "prompt"
            if prompt.strip():
                current.prompt.append(prompt.strip())
            continue

        if current is None:
            continue

        answer_match = _ANSWER.match(line)
        if answer_match:
            section = "answer"
            if answer_match.group(1):
                current.answer.append(answer_match.group(1).strip())
            continue

        explanation_match = _EXPLANATION.match(line)
        if explanation_match:
            section = "explanation"
            if explanation_match.group(1):
                current.explanation.append(explanation_match.group(1).strip())
            continue

        option_match = _OPTION.match(line)
        if option_match and section in ("prompt", "options"):
            label = (option_match.group(1) or option_match.group(2)).upper()
            option_text = option_match.group(3).strip()
            if label in current.options:
                warnings.append(
                    f"Question {question_number} has a duplicate choice label {label}; "
                    "the later choice was ignored."
                )
            elif option_text:
                current.options[label] = option_text
            section = "options"
            continue

        if section == "prompt":
            current.prompt.append(line)
        elif section == "options" and current.options:
            last_label = next(reversed(current.options))
            current.options[last_label] += f" {line}"
        elif section == "answer":
            current.answer.append(line)
        else:
            current.explanation.append(line)

    if current is not None and question_number is not None:
        finish_question(current, question_number)

    if not questions and not warnings:
        warnings.append(
            "No numbered questions were found. Use headings such as 'Question 1:' or '1.'."
        )
    return ParseResult(questions=questions, warnings=warnings)
