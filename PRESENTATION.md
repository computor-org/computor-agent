# Computor Agent - AI-Powered Teaching Assistant

## Overview

The **Computor Agent** is an intelligent tutoring system that automatically assists students with their programming assignments. It acts as a virtual teaching assistant that monitors student activity, answers questions, and provides feedback on code submissions - all without human intervention.

---

## The Big Picture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           COMPUTOR PLATFORM                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐         ┌─────────────┐         ┌─────────────┐         │
│   │   Student   │         │   Tutor     │         │   Lecturer  │         │
│   │  (Browser)  │         │  (Browser)  │         │  (Browser)  │         │
│   └──────┬──────┘         └──────┬──────┘         └──────┬──────┘         │
│          │                       │                       │                 │
│          │    ┌──────────────────┴───────────────────────┘                 │
│          │    │                                                            │
│          ▼    ▼                                                            │
│   ┌─────────────────────────────────────────────────────────────┐         │
│   │                    COMPUTOR BACKEND                          │         │
│   │                                                              │         │
│   │  • Courses & Assignments    • Student Submissions           │         │
│   │  • Messages & Discussions   • Grades & Feedback             │         │
│   │  • User Management          • File Storage                  │         │
│   └─────────────────────────────────────────────────────────────┘         │
│                              ▲                                             │
│                              │ API                                         │
│          ┌───────────────────┼───────────────────┐                        │
│          │                   │                   │                        │
│          ▼                   ▼                   ▼                        │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                │
│   │   VSCode    │     │  TUTOR AI   │     │   Future    │                │
│   │  Extension  │     │   AGENT     │     │   Tools     │                │
│   │             │     │             │     │             │                │
│   │ For humans  │     │ Autonomous  │     │     ...     │                │
│   └─────────────┘     └─────────────┘     └─────────────┘                │
│                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## What Does the Tutor AI Agent Do?

The agent works like a tireless teaching assistant that:

### 1. Monitors Student Activity
- Watches for new questions in discussion threads
- Detects when students submit their assignments
- Identifies which students need help

### 2. Understands Student Needs
- Reads student messages and code
- Classifies what kind of help they need:
  - Asking for an example
  - Stuck on a bug
  - Requesting code review
  - General questions

### 3. Provides Helpful Responses
- Generates personalized explanations
- Gives hints without revealing solutions
- Reviews code and suggests improvements
- Adapts to each student's skill level

### 4. Maintains Safety
- Detects inappropriate content
- Blocks manipulation attempts
- Ensures educational integrity

---

## How It Works - The Student Journey

```
   STUDENT                        TUTOR AI AGENT                    BACKEND
      │                                 │                              │
      │  1. Writes message:             │                              │
      │     "How do I sort a list?"     │                              │
      │  ─────────────────────────────► │                              │
      │                                 │                              │
      │                                 │  2. Polls for new messages   │
      │                                 │  ◄──────────────────────────►│
      │                                 │                              │
      │                                 │  3. Analyzes the question    │
      │                                 │     • Security check ✓       │
      │                                 │     • Intent: "How-to"       │
      │                                 │                              │
      │                                 │  4. Generates response       │
      │                                 │     using AI (LLM)           │
      │                                 │                              │
      │                                 │  5. Posts helpful reply      │
      │                                 │  ─────────────────────────►  │
      │                                 │                              │
      │  6. Sees response:              │                              │
      │     "Here's how to sort..."     │                              │
      │  ◄─────────────────────────────────────────────────────────────│
      │                                 │                              │
```

---

## Architecture - Building Blocks

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TUTOR AI AGENT                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────┐                                                   │
│  │    SCHEDULER    │  Runs continuously, checking for work             │
│  │                 │  every 30 seconds                                 │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │    TRIGGER      │  Decides: "Should I respond to this?"             │
│  │    DETECTOR     │  • New message from student?                      │
│  │                 │  • New submission to review?                      │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │  SECURITY GATE  │  Checks for threats & manipulation               │
│  │                 │  • Prompt injection attempts                     │
│  │                 │  • Inappropriate content                         │
│  └────────┬────────┘                                                   │
│           │ (if safe)                                                  │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │    INTENT       │  Understands what student needs                  │
│  │    CLASSIFIER   │  • Question about examples                       │
│  │                 │  • Help with debugging                           │
│  │                 │  • Code review request                           │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │    STRATEGY     │  Generates appropriate response                  │
│  │    EXECUTOR     │  • Uses configured personality                   │
│  │                 │  • Applies grading rubrics                       │
│  │                 │  • Formats helpful reply                         │
│  └────────┬────────┘                                                   │
│           │                                                            │
│           ▼                                                            │
│  ┌─────────────────┐                                                   │
│  │   RESPONSE      │  Delivers the response                           │
│  │   HANDLER       │  • Posts message to student                      │
│  │                 │  • Optionally submits grade                      │
│  └─────────────────┘                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## The Abstraction Layer - Connecting Everything

The agent connects to the Computor platform through an **abstraction layer**. This means:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│    TUTOR AGENT                    ABSTRACTION                BACKEND   │
│    (What it wants)                LAYER                      (API)     │
│                                                                         │
│    "Get student info"      ──►    Adapter       ──►    /api/users/...  │
│    "Read messages"         ──►    Adapter       ──►    /api/messages/  │
│    "Post response"         ──►    Adapter       ──►    /api/messages/  │
│    "Submit grade"          ──►    Adapter       ──►    /api/grades/    │
│                                                                         │
│    "Generate AI response"  ──►    LLM Adapter   ──►    AI Service      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Why this matters:**
- The agent speaks a simple language ("get messages", "post reply")
- The adapter translates to the technical API calls
- If the backend changes, only the adapter needs updating
- The same pattern is used by the VSCode Extension

---

## Shared Design - Agent & VSCode Extension

Both the Tutor AI Agent and the VSCode Extension follow the **same structure**:

```
                    ┌─────────────────────┐
                    │   COMPUTOR BACKEND  │
                    │        (API)        │
                    └──────────┬──────────┘
                               │
              ┌────────────────┴────────────────┐
              │                                 │
              ▼                                 ▼
     ┌─────────────────┐               ┌─────────────────┐
     │  VSCode Plugin  │               │  Tutor AI Agent │
     │                 │               │                 │
     │  For HUMANS     │               │  For AUTOMATION │
     │  - IDE features │               │  - Auto-respond │
     │  - Manual work  │               │  - 24/7 active  │
     │  - Visual UI    │               │  - No UI needed │
     └─────────────────┘               └─────────────────┘
              │                                 │
              ▼                                 ▼
     ┌─────────────────────────────────────────────────┐
     │           SAME DIRECTORY STRUCTURE              │
     │                                                 │
     │   /course-name/                                │
     │   ├── /student-submissions/                    │
     │   │   ├── /student-a/                         │
     │   │   │   └── code files...                   │
     │   │   └── /student-b/                         │
     │   │       └── code files...                   │
     │   └── /reference-solution/                    │
     │       └── solution files...                   │
     └─────────────────────────────────────────────────┘
```

**Key insight:** Whether a human tutor uses VSCode or the AI agent runs automatically, they both see and work with student submissions in the exact same way.

---

## Configuration - Teaching the Agent

The agent is configured to match your course needs:

### Personality Settings
- Friendly and encouraging vs. formal and direct
- Patience level for struggling students
- Language and tone preferences

### Response Strategies
- How to handle different question types
- When to give hints vs. explanations
- Code review depth and focus areas

### Grading Rules
- Rubric-based evaluation
- Point distributions
- Automatic vs. suggested grades

### Security Policies
- What content to block
- How to handle edge cases
- Logging and alerts

---

## Benefits

| For Students | For Teaching Staff | For Institutions |
|-------------|-------------------|------------------|
| Instant help 24/7 | Reduced workload | Scalable support |
| Consistent feedback | Focus on complex cases | Cost efficient |
| No waiting time | Overview of common issues | Quality assurance |
| Personalized hints | Automatic first response | Data insights |

---

## Summary

The **Computor Agent** transforms how programming education works:

1. **Always Available** - Students get help anytime, not just during office hours
2. **Consistent Quality** - Every student receives thoughtful, appropriate feedback
3. **Safe & Secure** - Built-in protections against misuse
4. **Seamlessly Integrated** - Works with the existing Computor platform
5. **Configurable** - Adapts to different courses and teaching styles

The agent acts as a bridge between AI capabilities and educational needs, bringing the same functionality that human tutors have (through VSCode) into an automated, scalable system.

---

*Built with the Computor Platform - Empowering Education Through Technology*
