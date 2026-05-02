# DESIGN.md

## 1. Tech stack

**Decision.** FastAPI + SQLAlchemy + SQLite on the backend; Vite + React + TypeScript + Tailwind on the frontent. 

Claude proposed me with different stacks, and I made the architectural trade-offs and arrived to that. I chose SQLite because its enough for this project scope and Postgres would be overkill. 

---

## 2. Two LLM calls

**Decision.** Extraction and scoring are two separate LLM calls with two separate prompts. The extraction result is persisted before scoring runs. This is because I wanted the extraction to be reusable so the recruiters could re-run the extraction (for custom fields) or re-run scoring as much as they want. The extraction modle first return is_resume boolean and validity_confidence, and any documents that is not resume is instantly skipped for scoring. However, the recruiter can still open and edit.

The whole idea is mine. For the resume extraction prompt, i hand written the whole JSON structure and the scoring prompt is fully written by claude (scoring is not the main part of assignment, but the document scanninng is)

---

## 3. Eval dataset

**Decision.** The evaluation dataset is from the Kaggle resume corpus, one from each of 8 different categories (engineering, healthcare, finance, etc.). I hand-lablled all 8 of the resumes by manually, and "make eval" shows the diffs in each field against the extraction from claude-sonnet-4-6, and shows the final metrics of resume accuracy + education match + skills F1 + years of experience difference.

The whole idea is mine, including getting resumes from Kaggle + labelling.

---

## 4. Opt-in alias learning

**Decision.** In the editor page (after extracting the resume), the recruiter can choose to make the system remember the corrections made to the skill tags by opting-in the "Apply skill  corrections to alias learning for future resumes." Because sometimes people would write NodeJS, and sometimes people write node.js in their resume.

The idea is mine. The first version learned automatically and I noticed the alias table was filling with garbage after a few test runs. So, I told Claude to add the opt-in checkbox.

---

## 5. Custom fields

**Decision.** Recruiters can add custom fields under each of the job descriptions. The custom field structre is (name, description, any{text, bool, list, number}). The descriptions written by the recruiters are injected into the extraction prompt. For example, a recruiter might want to add name = "current_student", description = "is this applicant still in school",and bool to filter out any applicants who are not still in school for internship positions.

The idea is mine, including the field structure. Copilot wrote the CRUD endpoints and the Schema page admin UI.

---

## 6. Async upload with task polling

**Decision.** After a resume is uploaded (POST /api/resumes/upload) it returns with "HTTP 202 Accepted" instantly and created {task_id, resume_id} on the backend. The frontend then polls GET /api/resumes/tasks/{task_id} every 1.2s. This allowed the recruiter to upload multiple resumes without having to wait on a single thread rendering. It also shows each status of the task to let the recruiter know Reading document -> AI extracting -> AI scoring -> Done /Rejected document / Failed.

Last time Professor Nadia made comments a lot on the performance. So this time, i decided to ask my digital friend gemini 3.1 (apparently good at critiquing on usability), and this is what he came up with. I polished it a bit and Claude implemented it.

---

## 7. Resume schema

**Decision.** There is a bunch of different versions of the resume extraction schema, because i kept nudging Claude to handle all the possible edge cases. I don't exactly remember what i changed for each version but apparently its at version 7. For the full resume schema, refer to the readme.md.

100% mine for every schema change. They were prompted by specific test cases in my own resume.

---

## 8. concerns field

**Decision.** The extraction prompt produces a concerns field array on factual observations that the recruiter may want to ask the applicant during a phone screen, espcially focusing on time sensitive events like graduation date clarification, or overlapping months on job experiences. Note: these don't affecting the scoring because it's unfair for the applicants to get auto-deduct points for a 14-month gap in education.

The whole idea is mine, claude implemented it.

---
