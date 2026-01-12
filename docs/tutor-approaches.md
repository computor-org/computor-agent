# Tutor Agent: Two Processing Approaches

This document provides an overview of the two main tasks for the Tutor AI Agent.

> **Implementation Order:**
> 1. **Messaging** (help conversations) - See [tutor-messaging.md](./tutor-messaging.md) ← **CURRENT FOCUS**
> 2. **Grading** (submission review) - See [tutor-grading.md](./tutor-grading.md) ← POSTPONED

---

## Overview

The tutor agent handles two **distinct and separate** tasks:

| Task | Trigger | Purpose | Output | Status |
|------|---------|---------|--------|--------|
| **1. Messaging** | Message with `#ai::request` tag | Help students with questions | Response message | **IN PROGRESS** |
| **2. Grading** | Ungraded submission | Review and grade code | Grade + Status + Feedback | POSTPONED |

These tasks are **independent** and should be implemented separately.

### Shared Components

Both tasks share:
- Authentication (API tokens)
- Security checks (prompt injection detection)
- Assignment description fetching (from GitLab)

---

## Authentication

| API | Header | Token Format |
|-----|--------|--------------|
| Computor Backend | `X-API-Token` | `ctp_<32chars>` (from config.yaml) |
| GitLab (for repos) | `PRIVATE-TOKEN` | `glpat-<token>` (from credentials.yaml) |

---

## API Endpoints Used

### Tutor Endpoints (Aggregated Data)

The `/tutors` endpoints provide pre-aggregated information optimized for the tutor workflow:

| Endpoint | Purpose | Key Fields |
|----------|---------|------------|
| `GET /tutors/course-members` | List course members with counts | `unread_message_count`, `ungraded_submissions_count` |
| `GET /tutors/course-members/{cm_id}/course-contents` | List course contents for member | `submission_group`, `result` |
| `GET /tutors/course-members/{cm_id}/course-contents/{cc_id}` | Get student work + test results | `result`, `submission_group.gradings`, `directory` |
| `PATCH /tutors/course-members/{cm_id}/course-contents/{cc_id}` | Submit grade | `grade`, `status`, `feedback` |
| `GET /students/courses/{course_id}` | Get course info (for repo paths) | `repository.provider_url`, `repository.full_path` |

### Submission Endpoints

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `GET /submissions/artifacts/download` | Download latest submission artifact | `submission_group_id` OR (`course_content_id` + `course_member_id`) |

### Message Endpoints

| Endpoint | Purpose | Key Fields |
|----------|---------|------------|
| `GET /messages?tags=ai::request&unread=true` | Find tagged messages | `tags`, `unread`, `parent_id` |
| `POST /messages` | Send response | `content`, `title`, `parent_id` |
| `POST /messages/{id}/reads` | Mark as read | - |

---

## Assignment Description Location

Assignment descriptions are stored in the **student-template repository** on GitLab.

### How to Fetch

1. Get course info: `GET /students/courses/{course_id}`
   - Extract: `repository.provider_url` and `repository.full_path`

2. Build student-template path:
   ```
   {provider_url}/{full_path}/student-template
   ```

3. Get assignment directory from course content's `directory` field

4. Fetch README via GitLab API:
   ```
   GET {provider_url}/api/v4/projects/{encoded_path}/repository/files/{directory}/README_en.md?ref=main
   ```

5. Fallback order: `README_en.md` → `README_de.md` → `README.md`

### Example

```
Course: Programming in Physics MATLAB
  provider_url: http://localhost:8084
  full_path: test/showcases/programming/matlab.sc

Assignment: "Anonymous Functions"
  directory: itpcp.pgph.mat.anonymous_function

README path: test/showcases/programming/matlab.sc/student-template/itpcp.pgph.mat.anonymous_function/README_en.md
```

---

## Approach 1: Message-Based Help

### Trigger
A student writes a message with a configured trigger tag (e.g., `#ai::request`) in the title.

### Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     MESSAGE HELP FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DETECT TRIGGER                                              │
│     GET /messages?submission_group_id=...&tags=ai::request      │
│                  &unread=true                                   │
│     → Find messages with request tag                            │
│     OR                                                          │
│     GET /messages?submission_group_id=...&unread=true           │
│     → Find follow-up replies in AI conversation chains          │
│                                                                 │
│  2. GATHER CONTEXT                                              │
│     ├─ Fetch full conversation (message + all parents)         │
│     ├─ Fetch student info (name, email, role)                  │
│     ├─ Download submission artifacts (if any exist)            │
│     │   └─ Student code repository                             │
│     │   └─ Read content/index_en.md (assignment in repo)       │
│     ├─ Download reference example (if available)               │
│     │   └─ Read content/index_en.md (reference description)    │
│     └─ Load AI notes for this student/group (memory)           │
│                                                                 │
│  3. SECURITY CHECK                                              │
│     ├─ Scan message for prompt injection                       │
│     ├─ Scan code for malicious content                         │
│     └─ If threat detected → block or log                       │
│                                                                 │
│  4. CLASSIFY INTENT                                             │
│     ├─ QUESTION_EXAMPLE - about assignment requirements        │
│     ├─ QUESTION_HOWTO - general programming question           │
│     ├─ HELP_DEBUG - needs debugging assistance                 │
│     ├─ HELP_REVIEW - wants code review                         │
│     ├─ CLARIFICATION - follow-up question                      │
│     └─ OTHER - unclear intent                                  │
│                                                                 │
│  5. GENERATE RESPONSE                                           │
│     ├─ Select strategy based on intent                         │
│     ├─ Build prompt with full context                          │
│     └─ Generate helpful LLM response                           │
│                                                                 │
│  6. SEND RESPONSE                                               │
│     POST /messages                                              │
│     ├─ Create message with parent_id (reply chain)             │
│     ├─ Add response tag (#ai::response) to title               │
│     └─ Mark original message as read                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Message Trigger Detection

**Two scenarios trigger a response:**

| Trigger | Condition | Query |
|---------|-----------|-------|
| **New Conversation** | Message has request tag AND is unread | `messages.list(tags=[...], unread=True)` |
| **Follow-up Reply** | Unread reply with `parent_id` AND AI previously responded in chain | `messages.list(unread=True)` + trace parent chain |

---

## Approach 2: Submission Review

### Trigger Conditions

A submission should be graded when **ALL** of the following are true:

| Condition | Location | Check |
|-----------|----------|-------|
| No existing gradings | `submission_group.gradings` | `gradings == []` (empty list) |
| Status is "not reviewed" | `submission_group.status` | `status == None` or `status == "not_reviewed"` |

**Re-submissions**: Do NOT re-grade if already graded (gradings list is not empty).

### Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                   SUBMISSION REVIEW FLOW                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. FIND COURSE MEMBERS WITH WORK                               │
│     GET /tutors/course-members                                  │
│     → Filter by: ungraded_submissions_count > 0                │
│     → Returns course members needing attention                  │
│                                                                 │
│  2. GET COURSE CONTENTS FOR MEMBER                              │
│     GET /tutors/course-members/{cm_id}/course-contents          │
│     → Filter by: has_ungraded_submission=true                  │
│     → Returns list of course contents needing grading          │
│                                                                 │
│  3. GET COURSE CONTENT DETAILS                                  │
│     GET /tutors/course-members/{cm_id}/course-contents/{cc_id}  │
│     → Get: result.result (test score float 0-1)                │
│     → Get: result.result_json (detailed test output)           │
│     → Get: submission_group.gradings (check if empty!)         │
│     → Get: submission_group.status (check if not_reviewed!)    │
│     → Get: directory (for assignment description path)         │
│                                                                 │
│  4. DOWNLOAD CODE & ASSIGNMENT DESCRIPTION                      │
│     ├─ Download student artifact                               │
│     │   GET /submissions/artifacts/download                    │
│     │   params: submission_group_id OR (course_content_id +    │
│     │           course_member_id)                              │
│     ├─ Fetch assignment description from GitLab                │
│     │   → student-template/{directory}/README_en.md            │
│     └─ Load AI notes for this student/group                    │
│                                                                 │
│  3. SECURITY CHECK                                              │
│     ├─ Scan submitted code for malicious content               │
│     └─ If threat detected → block or flag for review           │
│                                                                 │
│  4. LLM ANALYSIS & STATUS DETERMINATION                         │
│     │                                                           │
│     │  The LLM reviews:                                        │
│     │  ├─ Student code vs reference solution                   │
│     │  ├─ Whether index_en.md requirements are fulfilled       │
│     │  ├─ Test results and any failures (result_json)          │
│     │  └─ Code quality and improvements                        │
│     │                                                           │
│     │  The LLM determines status based on requirements:        │
│     │  ┌─────────────────────────────────────────────────┐     │
│     │  │ Requirements fully met    → CORRECTED (1)       │     │
│     │  │ Met but improvements      → IMPROVEMENT_POSSIBLE│     │
│     │  │ Not met, needs rework     → CORRECTION_NECESSARY│     │
│     │  └─────────────────────────────────────────────────┘     │
│     │                                                           │
│     │  Note: Test result (float) is a METRIC, not the         │
│     │        decision factor. LLM judges if requirements       │
│     │        from index_en.md are fulfilled.                   │
│     │                                                           │
│     └─ Generate explanation message for the status             │
│                                                                 │
│  5. SUBMIT GRADE                                                │
│     PATCH /tutors/course-members/{cm_id}/course-contents/{cc_id}│
│     Body: {                                                     │
│       "grade": 0.85,           // float 0.0-1.0                │
│       "status": 1,             // GradingStatus enum           │
│       "feedback": "...",       // explanation for student      │
│       "artifact_id": "..."     // which artifact was graded    │
│     }                                                           │
│                                                                 │
│  6. SEND FEEDBACK MESSAGE (optional)                            │
│     POST /messages                                              │
│     ├─ Create detailed feedback message                        │
│     └─ Add response tag (#ai::response) to title               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Correction Status Values

| Status | Value | Meaning | When to Use |
|--------|-------|---------|-------------|
| NOT_REVIEWED | 0 | Not yet reviewed | Default/initial state |
| CORRECTED | 1 | Submission accepted | Requirements from index_en.md fulfilled |
| CORRECTION_NECESSARY | 2 | Must be reworked | Requirements NOT met, student must fix |
| IMPROVEMENT_POSSIBLE | 3 | Accepted with suggestions | Requirements met, but could be better |

### Important: Status Determination Logic

The test result (`result.result`) is just a **metric** (float 0-1).

**The actual status decision is made by the LLM** based on:
1. Does the student's code fulfill the requirements in `content/index_en.md`?
2. What do the test results show? (pass/fail details from `result_json`)
3. Is the implementation correct, even if tests didn't catch everything?

Example scenarios:
- Test score 0.95 but missing required feature → `CORRECTION_NECESSARY`
- Test score 0.70 but all requirements met → `CORRECTED` or `IMPROVEMENT_POSSIBLE`
- Test score 1.0 with ugly code → `IMPROVEMENT_POSSIBLE` with suggestions

---

## Key Differences: Old vs New Approach

### Finding Ungraded Submissions

| Old (Wrong) | New (Correct) |
|-------------|---------------|
| `GET /submissions/artifacts?submit=true` | `GET /tutors/submission-groups?has_ungraded_submissions=true` |
| Must manually check if already graded | Pre-filtered to only ungraded |
| No grading status info | Includes `grading_statistics` |
| No member info | Includes `members[]` with names |

### Submitting Grades

| Old (Wrong) | New (Correct) |
|-------------|---------------|
| `PATCH /submission-groups/{id}` | `PATCH /tutors/course-members/{cm_id}/course-contents/{cc_id}` |
| Limited fields | Full grading fields: `grade`, `status`, `feedback`, `artifact_id` |
| No response confirmation | Returns `graded_artifact_id`, `graded_artifact_info` |

### Getting Test Results

| Old (Missing) | New (Correct) |
|---------------|---------------|
| Not implemented | `GET /tutors/course-members/{cm_id}/course-contents/{cc_id}` |
| - | Returns `result.result` (score) and `result.result_json` (details) |

---

## Configuration

### tutor.yaml

```yaml
# Triggers - when the agent responds
triggers:
  # Tags that trigger message responses
  request_tags:
    - scope: "ai"
      value: "request"
  response_tag:
    scope: "ai"
    value: "response"

  # Enable submission review (uses tutor endpoints)
  check_submissions: true

# Grading - automated grade assignment
grading:
  enabled: true
  auto_submit_grade: false  # If true, automatically submit grade via API

# Context - what information to include
context:
  include_previous_messages: 3
  include_reference_solution: true
  include_test_results: true
  max_code_lines: 1000
  max_code_files: 20

  # Assignment description file (inside downloaded repo)
  assignment_file: "content/index_en.md"
  assignment_fallback_languages: ["de", ""]
```

---

## Security

Both approaches maintain security checks - this is **not bypassed**:

1. **Message scanning**: Check student messages for prompt injection
2. **Code scanning**: Check submitted code for malicious content
3. **Two-phase confirmation**: Second LLM call to confirm threats
4. **Blocking behavior**: Configurable (block response vs. log only)

Security runs **after** context gathering and **before** LLM response generation.

---

## Summary

| Feature | Approach 1 (Message) | Approach 2 (Submission) |
|---------|---------------------|------------------------|
| Trigger | `#ai::request` tag OR follow-up reply | `has_ungraded_submissions=true` |
| Detection Endpoint | `GET /messages?tags=...&unread=true` | `GET /tutors/submission-groups?has_ungraded_submissions=true` |
| Intent | Classified by LLM | Fixed: SUBMISSION_REVIEW |
| Grade output | No | Yes (grade + status + feedback) |
| Test results | Optional context | Primary input (from tutor endpoint) |
| Grading Endpoint | N/A | `PATCH /tutors/course-members/.../course-contents/...` |
| Response type | Helpful answer | Structured feedback with "why" |
