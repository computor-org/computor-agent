# Tutor Agent: Grading (Submission Review)

> **Status: POSTPONED** - This task will be implemented after the messaging task is complete.

This document describes the **grading task** of the Tutor AI Agent - reviewing and grading student submissions.

---

## Overview

| Aspect | Description |
|--------|-------------|
| **Purpose** | Review submissions, determine grade and status |
| **Trigger** | Ungraded submission (`gradings == []` AND `status == None`) |
| **Output** | Grade (0.0-1.0) + Status (CORRECTED, CORRECTION_NECESSARY, IMPROVEMENT_POSSIBLE) + Feedback message |
| **Context** | Student code, assignment description, test results, reference solution |

---

## Trigger Conditions

A submission should be graded when **ALL** are true:

| Condition | Location | Check |
|-----------|----------|-------|
| No existing gradings | `submission_group.gradings` | `gradings == []` |
| Status is not reviewed | `submission_group.status` | `status == None` |

**Re-submissions**: Do NOT re-grade if already graded.

---

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /tutors/course-members` | Filter by `ungraded_submissions_count > 0` |
| `GET /tutors/course-members/{cm_id}/course-contents` | Filter by `has_ungraded_submission=true` |
| `GET /tutors/course-members/{cm_id}/course-contents/{cc_id}` | Get details, check `gradings`, `status` |
| `GET /submissions/artifacts/download` | Download student code |
| `PATCH /tutors/course-members/{cm_id}/course-contents/{cc_id}` | Submit grade |

---

## Grading Status Values

| Status | Value | Meaning |
|--------|-------|---------|
| NOT_REVIEWED | 0 | Not yet reviewed (initial state) |
| CORRECTED | 1 | Requirements met, accepted |
| CORRECTION_NECESSARY | 2 | Requirements NOT met, must fix |
| IMPROVEMENT_POSSIBLE | 3 | Requirements met, but could be better |

---

## Flow (To Be Implemented)

```
1. POLL for ungraded submissions
2. CHECK trigger conditions (gradings empty, status null)
3. DOWNLOAD student artifact
4. FETCH assignment description
5. FETCH test results (result.result_json)
6. SECURITY check code
7. LLM analysis → determine status + generate feedback
8. SUBMIT grade via PATCH endpoint
9. POST feedback message (optional)
```

---

## Implementation Notes

- The `process_submission()` method in `agent.py` handles this
- Uses `SubmissionReviewStrategy` with grading extraction
- Test results come from `CourseContentStudentGet.result.result_json`
- Grade is submitted via `PATCH /tutors/course-members/.../course-contents/...`

---

## See Also

- [tutor-messaging.md](./tutor-messaging.md) - The messaging task (implemented first)
- [tutor-approaches.md](./tutor-approaches.md) - Overview of both approaches
