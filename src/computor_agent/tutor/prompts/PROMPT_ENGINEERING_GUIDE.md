# Prompt Engineering Guide for Tutor Agent

## Overview

This guide explains how to create and modify prompts for the Tutor Agent. Prompts use template variables (in `{variable}` notation) that are replaced with actual values at runtime.

## Directory Structure

```
prompts/
├── personality/      # Define the agent's tone and behavior
├── strategy/        # Define response strategies for different intents
├── security/        # Security check prompts
└── README.md        # This guide (auto-copied)
```

## Template Variables Reference

### Common Variables (Available in Most Prompts)

| Variable | Description | Example Content |
|----------|-------------|-----------------|
| `{tutor_name}` | The agent's name from config | "Tutor AI" |
| `{language}` | Response language code | "en", "de", "fr" |
| `{personality_prompt}` | The selected personality text | Content from personality/*.md |
| `{assignment_description}` | Current assignment details | "Title: Lab 1\nImplement a sorting algorithm..." |

### Strategy-Specific Variables

#### All Strategy Prompts
| Variable | Description | Available In |
|----------|-------------|--------------|
| `{student_message}` | The student's current message | fallback, clarification |
| `{student_code}` | Student's repository code | help_debug, help_review |
| `{previous_messages}` | Conversation history | clarification, all strategies |
| `{reference_solution_section}` | Reference solution (if enabled) | help_debug, help_review |

#### Intent-Specific Variables
| Variable | Description | Used In Strategy |
|----------|-------------|------------------|
| `{user_intent_description}` | AI's interpretation of user intent | fallback |
| `{test_results}` | Test execution results | help_debug |
| `{artifacts}` | Build/compilation artifacts | help_debug |
| `{git_diff}` | Recent changes in repository | help_review |
| `{reference_comparison}` | Diff against reference solution | help_review |

### Security Prompt Variables
| Variable | Description |
|----------|-------------|
| `{content}` | Message content to analyze |
| `{code}` | Code content to check |
| `{repository_files}` | List of files in repository |

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

### 2. Strategy Prompts (`strategy/*.md`)

**Purpose**: Define how to handle specific types of student requests.

**Template Structure**:
```markdown
You are helping a student [context].

Assignment Context:
---
{assignment_description}
---

{personality_prompt}

[Specific instructions for this intent]

[Response guidelines]

Language: {language}
```

**Available Strategies**:
- `question_example.md` - Student asks about assignment requirements
- `question_howto.md` - Student asks how to do something
- `help_debug.md` - Student needs debugging help
- `help_review.md` - Student wants code review
- `clarification.md` - Student asks follow-up questions
- `fallback.md` - Unmatched intents

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
1. Load Strategy Template (e.g., question_howto.md)
   ↓
2. Replace {personality_prompt} with content from personality/*.md
   ↓
3. Replace {tutor_name} within personality prompt
   ↓
4. Replace context variables ({assignment_description}, {student_message}, etc.)
   ↓
5. Send to LLM
```

### Example Composition

**Input**: Student asks "How do I read a file in Python?"

**Composition**:
1. Intent classified as `QUESTION_HOWTO`
2. Load `strategy/question_howto.md`
3. Load `personality/friendly_professional.md`
4. Replace variables:
   - `{personality_prompt}` → Entire personality text
   - `{tutor_name}` → "Tutor AI"
   - `{assignment_description}` → "Title: File I/O Lab..."
   - `{language}` → "en"

**Final Prompt Sent to LLM**:
```
You are helping a student learn how to do something.

Assignment Context:
---
Title: File I/O Lab
Implement file reading and writing operations...
---

You are Tutor AI, a friendly and professional tutor.
You maintain a warm but educational tone...

The student is asking a general how-to question...

RESPONSE GUIDELINES:
- Provide a CONCISE answer (2-3 paragraphs maximum)
- Show ONE clear example if helpful (keep it brief)

Language: en
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
- Strategy prompts should complement, not override
- Keep language consistent across related prompts

### 4. Security Considerations
- Never include actual sensitive data in examples
- Be cautious with prompts that could reveal system internals
- Test security prompts with various attack vectors

### 5. Testing Your Prompts

**Development Mode Testing**:
```bash
# Start dev mode with your prompts
computor-agent tutor --dev --prompts-dir ./my-prompts

# Edit a prompt file
vim ./my-prompts/personality/friendly_professional.md

# See hot reload message
🔄 Prompt reloaded: friendly_professional.md

# Test immediately with a message
```

### 6. Prompt Stacking

Prompts are "stacked" in this order:
1. **Base**: Strategy template provides structure
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
- Check the strategy implementation in code

### Prompts Too Verbose
- Add explicit length constraints
- Use "CONCISE", "BRIEF", "SHORT" keywords
- Specify paragraph/sentence limits

### Inconsistent Behavior
- Check if personality and strategy prompts conflict
- Ensure all prompts have similar guidelines
- Test with different personality/strategy combinations

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
{previous_messages}

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