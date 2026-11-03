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

To stop the app, focus the PowerShell window where Streamlit is running and
press **Ctrl+C**. Closing that terminal also stops the local server.

The quiz keeps your answers in the local Streamlit session. Use **Back** and
**Next question** to navigate, or **Skip** to mark a question for later. **Review
answers** opens a summary grouped into correct, missed, skipped, and unanswered
questions. Each question can be reopened and reattempted; the score reflects
your latest attempt.

## Optional local AI parser

The regular text parser runs without an AI model. To ask a local model to repair
questions the text parser skips:

1. Install [Ollama for Windows](https://ollama.com/download/windows).
2. In PowerShell, download the default model:

   ```powershell
   ollama pull qwen2.5:7b
   ```

3. Keep Ollama running, start the quiz app, and choose **Local AI repair
   (Ollama)** in the sidebar.

The AI mode sends only skipped question text to the local Ollama server at
`localhost:11434`; it does not send the PDF to a hosted AI service. It verifies
that extracted correct-answer labels match the extracted choices and reports
questions that remain unreadable. Model downloads require an internet connection,
and parsing a large PDF can take a while on a CPU.

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
