# Prompt Engineering Guide for Tutor Agent

> **Read this first — which prompt actually runs?**
>
> Live tutor replies are generated from **one** unified prompt:
> `strategy/tutor.md`, with `personality/<tone>.md` substituted into it. That is
> the whole surface for the messaging agent.
>
> | I want to change… | Edit |
> |---|---|
> | how the tutor answers students | `strategy/tutor.md` |
> | its tone / persona | `personality/<tone>.md` (`tone:` in config) |
> | the grading rubric | `grading/grading.md` |
> | prompt-injection screening | `security/detection.md`, `security/confirmation.md` |
> | figure review | `figure_review/review.md` |
> | unit description drafts | `unit_description/unit_description.md` |
>
> Placeholders available in `strategy/tutor.md`: `{personality_prompt}`,
> `{language}`, `{student_section}`, `{assignment_section}`, `{code_section}`,
> `{test_results_section}`, `{previous_messages_section}`,
> `{reference_comparison_section}`, `{figure_review_section}`. Sections are
> empty strings when the corresponding context is unavailable.
>
> Note on grading: supplying `grading/grading.md` switches grading to its
> single-step path, because that is the path a custom rubric is applied on.
> Without it, grading uses the more accurate multi-step analysis.

## Overview

This guide explains how to create and modify prompts for the Tutor Agent. Prompts use template variables (in `{variable}` notation) that are replaced with actual values at runtime.

## Directory Structure

```
prompts/
├── personality/      # Define the agent's tone and behavior
├── strategy/        # tutor.md = the live messaging prompt
├── grading/         # Grading rubric (`grading.md`)
├── security/        # Security check prompts
├── figure_review/   # Figure review prompt (`review.md`)
├── unit_description/ # Unit description draft prompt (`unit_description.md`)
├── README.md        # This guide (auto-copied)
└── VARIABLES.md     # Variable reference card (auto-copied)
```

## Template Variables Reference

### `strategy/tutor.md`

| Variable | Description | Example Content |
|----------|-------------|-----------------|
| `{personality_prompt}` | The selected personality text | Content from personality/*.md |
| `{language}` | Response language code | "en", "de", "fr" |
| `{student_section}` | Name(s) of the student(s) | "Student: Max Mustermann" |
| `{assignment_section}` | Current assignment details | "Title: Lab 1\nImplement a sorting algorithm..." |
| `{code_section}` | Student's latest submitted code | "Student's Code: ..." |
| `{test_results_section}` | Test execution results | "Test Results: ..." |
| `{previous_messages_section}` | Conversation history | "Previous Conversation: ..." |
| `{reference_comparison_section}` | Comparison against the reference solution | "Reference Comparison: ..." |
| `{figure_review_section}` | Vision-LLM review of submitted figures | "Figure Review: ..." |

### Personality Prompt Variables
| Variable | Description |
|----------|-------------|
| `{tutor_name}` | The agent's name from config (`tutor.personality.name`) |

### Security Prompt Variables
| Variable | Description |
|----------|-------------|
| `{content}` | Message or code content to analyze |
| `{initial_detection}` | Result of the first check (`confirmation.md` only) |

See `VARIABLES.md` for the placeholders of the figure review, unit description
and grading prompts.

## Prompt Types Explained

### 1. Personality Prompts (`personality/*.md`)

**Purpose**: Define the agent's tone and communication style.

**Template Structure**:
```markdown
You are {tutor_name}, a [adjective] tutor.
[Core behavior description]
[Communication guidelines]

IMPORTANT: Keep responses CONCISE:
- [Specific length guidelines]
- [Focus areas]
```

**Example** (`friendly_professional.md`):
```markdown
You are {tutor_name}, a friendly and professional tutor.
You maintain a warm but educational tone, encouraging students while keeping discussions focused.

IMPORTANT: Keep your responses CONCISE and TO THE POINT:
- Focus on the specific question asked
- Provide clear, direct answers (2-3 paragraphs maximum)
- Include code examples only when necessary
```

### 2. Tutor Prompt (`strategy/tutor.md`)

**Purpose**: Define how the tutor answers students. Every live reply is
generated from this one prompt.

**Template Structure**:
```markdown
{personality_prompt}

[How to help without giving away the solution]

[Response guidelines]

{student_section}
{assignment_section}
{code_section}
{test_results_section}
{previous_messages_section}

Language: {language}
```

### 3. Security Prompts (`security/*.md`)

**Purpose**: Detect and handle potentially malicious content.

**Template Structure**:
```markdown
You are a security analyst checking [what to check].

[Guidelines for detection]

Content to analyze:
---
{content}
---

Respond with JSON:
{
    "is_suspicious": true/false,
    ...
}
```

## Prompt Composition Flow

The agent builds the final prompt by combining multiple pieces:

```
1. Load strategy/tutor.md (or the built-in prompt)
   ↓
2. Replace {tutor_name} within personality/<tone>.md
   ↓
3. Replace {personality_prompt} with that personality text
   ↓
4. Replace the context sections ({assignment_section}, {code_section}, etc.)
   ↓
5. Send to LLM
```

## Best Practices

### 1. Length Control
Always include explicit length constraints:
```markdown
RESPONSE GUIDELINES:
- Keep your answer CONCISE (2-3 paragraphs maximum)
- Focus ONLY on answering the specific question
```

### 2. Variable Usage
- Always keep `{variable}` placeholders intact
- Don't remove variables unless you know they're optional
- Test with different content lengths

### 3. Tone Consistency
- Personality prompts set the base tone
- `strategy/tutor.md` should complement, not override
- Keep language consistent across related prompts

### 4. Security Considerations
- Never include actual sensitive data in examples
- Be cautious with prompts that could reveal system internals
- Test security prompts with various attack vectors

### 5. Testing Your Prompts

**Development Mode Testing**:
```bash
# Start dev mode with your prompts
computor-agent tutor messaging --dev --prompts-dir ./my-prompts

# Edit a prompt file
vim ./my-prompts/personality/friendly_professional.md

# See hot reload message
Prompt reloaded: friendly_professional.md

# Test immediately with a message
```

### 6. Prompt Stacking

Prompts are "stacked" in this order:
1. **Base**: `strategy/tutor.md` provides structure
2. **Personality**: Injected via `{personality_prompt}`
3. **Context**: Variables replaced with actual data
4. **Guidelines**: Response constraints applied

## Common Patterns

### Pattern 1: Socratic Method
```markdown
Don't give direct answers. Instead:
- Ask guiding questions
- Help them discover the solution
- Provide hints, not solutions
```

### Pattern 2: Code-First Response
```markdown
Start with a code example, then explain:
```python
# Example here
```
Brief explanation follows...
```

### Pattern 3: Progressive Disclosure
```markdown
1. Give minimal answer first
2. If they need more, they'll ask
3. Mention "Ask if you need more details"
```

## Troubleshooting

### Variables Not Replaced
- Check variable name spelling exactly
- Ensure the variable is available for that prompt type
- Literal braces must be written as `{{` and `}}`

### Prompts Too Verbose
- Add explicit length constraints
- Use "CONCISE", "BRIEF", "SHORT" keywords
- Specify paragraph/sentence limits

### Inconsistent Behavior
- Check if the personality and tutor prompts conflict
- Ensure all prompts have similar guidelines
- Test with different personalities

## Advanced Techniques

### Conditional Responses
```markdown
If the code has syntax errors:
  - Point out the specific error first
  - Then explain how to fix it

If the code works but is inefficient:
  - Acknowledge it works
  - Suggest optimization
```

### Multi-Language Support
```markdown
Language: {language}

Note: Respond in the language specified above.
If {language} is "de", respond in German.
If {language} is "en", respond in English.
```

### Context-Aware Responses
```markdown
{previous_messages_section}

Based on our previous discussion:
- Reference what was already covered
- Build upon previous explanations
- Avoid repeating information
```

## Testing Checklist

Before deploying prompts:

- [ ] Test with minimal input
- [ ] Test with verbose input
- [ ] Test with code snippets
- [ ] Test with follow-up questions
- [ ] Test with off-topic questions
- [ ] Verify length constraints work
- [ ] Check personality consistency
- [ ] Validate security detection
- [ ] Test with different languages
- [ ] Verify hot reload works (dev mode)

## Version Control

Recommended practices:
- Track prompts in git
- Use meaningful commit messages
- Tag stable prompt versions
- Document significant changes
- A/B test before major changes

## Getting Help

- Check existing prompts for examples
- Test in development mode first
- Use hot reload for rapid iteration
- Monitor actual responses in logs
- Collect student feedback

---

*This guide is automatically copied to your prompts directory when initialized.*