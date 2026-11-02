# PDF Quiz

A local interactive quiz app that extracts multiple-choice questions from a PDF,
asks them one at a time, and shows whether your answer is correct along with the
answer and explanation.

## Run locally

From PowerShell in this project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open the local URL printed by Streamlit and upload your PDF.

## Supported PDF format

The app reads PDF text in visual reading order and expects selectable text
(not scanned images) with numbered questions,
lettered choices, an explicit correct answer label, and an optional explanation.
It parses all numbered questions in the PDF. For example:

```text
Question: 1
Select the two correct items.
A) First choice
B) Second choice
C) Third choice
D) Fourth choice
E) Fifth choice
Correct Answers: B, E
Explanation: The second and fifth choices match the stated rule.
```

PDF question headings in the form `Question: 1` are supported, as are headings
such as `Question 1:` and `1.`. Single-answer questions can use
`Correct Answer: B`. Multiple-answer questions
can have any number of lettered choices, such as A through E, and list all
correct labels on `Correct Answers:`. Compact answer keys such as `Answer: BE`
are also supported. The app shows checkboxes when
there is more than one correct answer and indicates how many answers to choose.
For example, `Correct Answers: B, E` asks you to select two choices. Answers are
compared as a set, so omitting a correct choice or selecting an extra choice is
marked incorrect. Lowercase choice labels are also accepted.

Alternative question headings such as `1.` and `1)` are supported. Incomplete
questions are skipped with a warning shown in the app.

PDFs vary in their layout. If a PDF uses different labels or formatting, its
layout needs to be added to the parser before the app can reliably understand it.
