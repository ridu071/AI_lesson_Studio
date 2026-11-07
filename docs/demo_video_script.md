# Demo video script (about 7 minutes)

The brief asks the video to show: lesson generation, research references, both QC
layers, content review, editing and export, plus a short explanation of the tools.

**Before recording**
- Start the app: `cd backend`, `streamlit run streamlit_app.py`, then open http://localhost:8501.
- Open the sidebar and check that "HTTP Requests and Responses (demo)" and
  "Photosynthesis (demo)" are there.
- Close `.env` and anything that shows an API key.

---

## 1. Opening (0:00-0:40)
*Show the first screen.*

> "Hi, this is AI Lesson Studio. You give it a lesson title and a learning objective.
> It researches real sources, writes a 45-minute visual lesson, and then checks that
> lesson with two separate quality checks before a teacher reviews it."

## 2. Create a lesson live (0:40-1:50)
*Type **HTTP Requests and Responses**. For the goal, type: "Explain GET and POST
methods and distinguish between 2xx, 4xx, and 5xx response status categories." First
press Create with the topic box empty.*

> "If I leave the topic empty, it stops me and tells me what's missing."

*Fill it in and press **Create my lesson** (choose "Create a new one anyway" if asked).*

> "Each duck is one real step. First, the AI plans what to search for. Then the code
> itself searches Wikipedia, Open Library and YouTube, and keeps the exact Wikipedia
> paragraphs as evidence. The AI writes the lesson using only that evidence. Finally,
> two quality checks run. Every step is saved, so if one fails I can press Try again
> and it continues from there, without losing work."

## 3. The student view (1:50-3:10)
*Open the **Learn** tab.*

> "The lesson has seven parts: an intro, core ideas with diagrams and examples, a
> worked example with a Try-it activity, and a short check after each idea. Students
> go one step at a time."

*Open a hint. Go to the **Test** and press Submit with one question empty.*

> "The test has ten questions of different types: multiple choice, scenarios,
> ordering steps and matching. You can't submit until every question is answered."

*Answer the questions, getting one or two wrong on purpose, then submit.*

> "The results show a score for each learning goal. If a goal is under 70%, the
> student gets a short review of that part. The recap ends with a personal summary."

## 4. Sources (3:10-3:40)
*Open the **Sources** tab.*

> "These are the references: the Wikipedia articles used as evidence, YouTube videos
> you can play here, and books. The code builds this list straight from the research,
> so the AI can't invent a link."

## 5. The two quality checks (3:40-5:00)
*Open **Teacher tools**, then **Fact check (QC1)**.*

> "Quality check 1 is about facts. Every claim in the lesson is matched to an exact
> evidence paragraph. The AI only says whether a paragraph supports or contradicts a
> claim, and the code decides the verdict. It isn't even told which source the lesson
> cited."

*Open **Teaching check (QC2)**.*

> "Quality check 2 is about teaching: is every goal explained, practised and tested,
> does it fit 45 minutes, are the answer keys right, is the language at the right
> level. Each problem comes with a suggested fix. Some rules always block the lesson,
> whatever the score: a made-up citation, a contradicted fact, going over 45 minutes,
> or a goal that's never tested."

## 6. Review, improve, edit (5:00-6:10)
*Open **Photosynthesis (demo)**, then **Teacher tools**, then **Version history**.*

> "When I checked this lesson by hand, I found two questions using 'primary electron
> donor' for two different things. Neither quality check caught it. That's exactly why
> a teacher stays in the loop."

*Use **What changed**, version 1 to version 2.*

> "I fixed it with Improve. Here you can see exactly which lines changed. The new
> version was checked again automatically, and the old one is kept. I also added this
> mistake to my test set, and the checks now catch it."

*Show **Improve**, then **Edit**. Change one sentence and save.*

> "I can apply the suggested fixes or write my own instruction, or edit by hand. Every
> save becomes a new version."

## 7. Export (6:10-6:40)
*Open the **Export** tab, download the PDF and create the summary image. Then go to
**Teacher tools**, then **Reports & files**.*

> "Students can download PDF notes and a one-page summary image. Teachers get a zip
> with the lesson, the references and both quality reports."

## 8. Tools and wrap-up (6:40-7:15)

> "It's built in Python. Gemini 3.1 Flash Lite does the planning, the writing and the
> AI parts of the checks. Pydantic keeps the data in a strict format, Streamlit runs
> the interface, and ReportLab and Pillow make the exports. There are 249 automated
> tests that run on GitHub. There's also a 27-case benchmark of planted mistakes. On
> it, the checks reach the right final decision in every case and never wrongly block
> or miss a lesson. The README lists the known limitations and credits Wikipedia, Open
> Library, YouTube and the libraries. I used Claude Code as an AI coding assistant.
> Thanks for watching."

---

**Tips**
- If a live build is slow or fails, keep recording. Showing **Try again** demonstrates
  the error handling the brief asks for.
- If you run short of time, cut part 3 down to the test and its results.
