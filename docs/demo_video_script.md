# Demo video script (about 7 minutes)

The brief asks the video to show: lesson generation, research references, both QC
layers, content review, editing and export, plus a short explanation of the tools.

**Before recording**
- Start the app: `cd backend`, `streamlit run streamlit_app.py`, then open http://localhost:8501.
- Open the sidebar (`>>`) and check that the two demo lessons are there:
  "HTTP Requests and Responses (demo)" and "Photosynthesis (demo)".
- Have `demo/` and the README open in another window.

---

## 1. Introduction (0:00-0:40)

> "This is AI Lesson Studio. From a lesson title and a learning objective, it researches
> websites, books and YouTube, writes a 45-minute visual lesson, and checks it with two
> independent quality-control layers before an instructor reviews it."

Show the first screen: the topic, level and goal fields.

## 2. Generate the sample lesson live (0:40-1:50)

1. Type **HTTP Requests and Responses** and the goal *"Explain GET and POST methods and
   distinguish between 2xx, 4xx, and 5xx response status categories."*
2. Press **Create my lesson** (choose "Create a new one anyway" if it asks).
3. While the ducks swim, explain:
   > "Each duck is a real step. The AI only *plans* the search; the code searches
   > Wikipedia, Open Library and YouTube, and keeps the exact Wikipedia paragraphs as
   > evidence. Then the AI writes the lesson using only that evidence, and both QC
   > layers check it."
4. Point at each duck's result line as it finishes (articles and passages found, the
   sections written, the QC scores).

## 3. The lesson, as a student sees it (1:50-3:00)

- **Learn**: show the Intro, one Core idea (a diagram, an example, the check question)
  and the Worked example with the **Try it** task (open its Hint).
- **Test**: show the question types and hints; press Submit with a question empty to
  show it is blocked; answer everything (get one or two wrong on purpose) and submit.
- **Your results**: per-objective scores, and the review block for a weak objective.
- **Recap**: the personal results line.

## 4. Research references (3:00-3:30)

- **Sources** tab: the Wikipedia pages (marked "used as evidence"), the playable YouTube
  videos, and the books.
  > "References are built by the code from the research, so the AI can never invent a link."

## 5. Both QC layers (3:30-4:50)

Open **Teacher tools** (top right):
- **Fact check (QC1)**: the claim table, where each claim maps to an evidence passage.
  > "QC1 doesn't ask the AI whether a fact is true. The AI only says how each passage
  > relates to each claim, and the code decides the verdict. It's not even told which
  > source the claim cites."
- **Teaching check (QC2)**: rubric scores, the objective coverage matrix and any issues
  with suggested fixes.
  > "Hard rules beat scores: a fabricated citation, a contradicted fact, more than 45
  > minutes or an untested objective blocks the lesson, whatever the score."

## 6. Review, apply recommendations, edit (4:50-6:00)

- Open **Photosynthesis (demo)** and go to **Teacher tools**, then **Version history**:
  > "My manual fact check found two questions that used 'primary electron donor' for
  > different things. Neither QC layer caught it, so I fixed it here with Improve."
  Then use **What changed** (version 1 to version 2) to show exactly which lines the fix changed.
- Show **Improve**: the QC suggestions and the instruction box. Explain that the
  revision becomes a new version and is re-checked automatically.
- Show **Edit**: change a sentence, save it as a new version, and point to Version
  history (the old version is kept).

## 7. Export (6:00-6:30)

- **Export** tab: download the **PDF notes** and open it briefly; press **Create summary
  image** and show the card.
- **Teacher tools**, then **Reports & files**: the zip with the lesson, references and
  both QC reports.

## 8. Tools and wrap-up (6:30-7:00)

> "It's built in Python: Gemini for planning, writing and the AI parts of QC; Pydantic
> for strict data contracts; Streamlit for the interface; ReportLab and Pillow for the
> exports. Every step is saved, so a failure can be retried without losing work. There
> are 249 unit tests, run automatically on GitHub, and a 27-case benchmark of planted errors; the results and the
> known limitations are in the README."

**Tips**
- If a live generation is slow or fails, keep recording: show the stuck duck and
  **Try again**, which demonstrates the error handling the brief asks for.
- Keep the API key out of the video: don't open `.env`.
