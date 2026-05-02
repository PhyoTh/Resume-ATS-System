# Feedback response

## [Feedback from Ethan Jenkins](https://github.com/ucsd-cse-genai-programming-sp26/02-doc-scanner-phthant-assignment-2/issues/2)

### 1. Trim the extraction prompt for lower latency — **Declined**

- **What I did**: No changes made.
- **Why**: As I mentioned in the design.md. I have updated the extraction propmt iteratively by trying out different edge cases in real-world resumes. For example, date formats could sometimees be 01/2026 or Jan. 2026 or January 2026, sometimes even just a single-date entries like 2028 which is supposed to mean end-date, degree abbreviations, contact-link rendering where PDFs show display labels like "GitHub" without the URL, calculated-YOE month math (only calculate the durations in experience section only, and don't double count the overlapping time), So, trimming the extraction prompt would be regress those cases. I even wanted to add more prompts to handle more edge cases, see [Plan.md](Plan.md)
- Additionally, A/B comparisons are already supported with make eval, so a recruiter-facing A/B UI in the web app would not add value as users for recruiters. Those are only for developers.

### 2. Scanner mode for "on-the-spot scoring without saving real information" — **Declined**

- **What I did**: I first tried prototyping a server-side ephemeral + scanner-mode upload toggle that requries opt-in. It will delete the file from disk after uploading the resume and resume row in the DB. But then, after implementing it and using it end-to-end, I decided to removed it back.
- **Why**: I couldn't justify the use case once I tried it. If a recruiter doesn't want to save a resume to their pipeline, they can just open the PDF and read it manually. The LLM extraction can mistake anyway. And without scoring, alias learning, or custom-field application, the "scan only" output is more or less the same as just looking at the original resume.

---

## [Feedback from Nick Pham](<TODO-fill-in-github-issue-url>)

### 1. Customer-base ambiguity — **Fixed**

- **What I did**: On resume upload, the hint now says "Uploaded resumes are saved to your local recruiter database" instead of "uploaded files are persisted in the backend database." On the Job Description page, "every resume that was submitted under it" became "every resume you uploaded against it". On the Verify page, the Concerns hint text now says recruiter directly as "you" rather than referring to "the recruiter" in third person. I also fixed the JD-page dialog "submitted under this JD" to "uploaded against this JD".
- **Why**: The project is made for recruiters, but during the production I might have prompted in a way that made claude thinks that i am developing for the applicants instead. The reviewer found this confusing enough that he flagged it as the most-confusing thing about the implementation. So it's worth fixing even though it's not a code-level issue.
- [Relevant commit](https://github.com/ucsd-cse-genai-programming-sp26/02-doc-scanner-phthant-assignment-2/commit/dc1c5af6166e111a6e8a9b72074f89bd77dcc165)

### 2. Edit on the Schema page + Global Custom Field — **Fixed**

- **What I did**: I added the inline edit on the Schema page for skill aliases so the recruiters can now just click edit on a row to change the canonical without having to delete and re-add a new alias. There was no change in backend because POST /api/aliases was already doing upsert. 
- I also added a global Custom Fields panel with full support for CRUD. I added PUT /api/custom_fields/{id}. For the existing JD related custom fields (which are managed on the Job Description page) I added PUT /api/jd/{jd_id}/custom_fields/{field_id} and DELETE /api/jd/{jd_id}/custom_fields/{field_id}. Then, I switched the JD related delete to use its own end point because it had been calling the global delete previously when the JD related delete route didn't exist.
- **Why**:  I think this is really helpful for the recruiters to be able to update the fields in the alias otherwise they would have to delete, then re-add to update just one field. Due to this implmentation i also found a bug in JD related delete. Previously, the route didn't exist, but api.deleteCustomField(id) was deleting via the global route which worked because the row is in the same custom_field table.
- [Relevant commit](https://github.com/ucsd-cse-genai-programming-sp26/02-doc-scanner-phthant-assignment-2/commit/dc1c5af6166e111a6e8a9b72074f89bd77dcc165)

### 3. Don't store outputs in the backend; use localStorage — **Declined**

- **What I did**: No changes made.
- **Why**: Same reasoning as Ethan's 2 above. Once I tried it, I couldn't justify the use case. A recruiter who doesn't want a resume in their pipeline would just open the PDF directly. I understand the privacy concern, but as an applicant, when they sent the recruiter their resume they are already obligated to share their private information with the company. The "use localStorage instead of a database" suggestion is also no-go for this app because the dashboard, ranking, scoring, and pipeline-status features all require persistent server-side storage. 

---

## [Instructor feedback from teoremma](https://github.com/ucsd-cse-genai-programming-sp26/02-doc-scanner-phthant-assignment-2/issues/4)

### Passed all the checks

---

## Feedback from myself