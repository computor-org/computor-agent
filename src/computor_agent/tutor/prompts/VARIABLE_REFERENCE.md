# Variable Reference Card

> **Which of these actually reach the LLM?**
>
> Live replies use only the placeholders of `strategy/tutor.md`:
> `{personality_prompt}`, `{language}`, `{assignment_section}`,
> `{code_section}`, `{test_results_section}`, `{previous_messages_section}`,
> `{reference_comparison_section}`, `{figure_review_section}`.
>
> The per-intent strategy variables documented below belong to the retired
> intent→strategy model and are not substituted for live replies.

## Quick Reference - Available Variables by Prompt Type

### ✅ ALL Strategy Prompts Can Use:
```
{personality_prompt}      - The personality text (from personality/*.md)
{language}               - Response language (en, de, etc.)
{assignment_description} - Current assignment details
```

### 📚 Strategy-Specific Variables:

#### `question_example.md` & `question_howto.md`
```
{student_code}            - Student's repository code
{previous_messages}       - Conversation history
{reference_solution_section} - Reference solution (if enabled)
```

#### `help_debug.md`
```
{student_code}            - Student's repository code
{previous_messages}       - Conversation history
{reference_solution_section} - Reference solution
{test_results_section}    - Test execution results
{submission_history_section} - Previous submission attempts
{artifacts_section}       - Build/compilation artifacts
{progress_section}        - Student's course progress
```

#### `help_review.md`
```
{student_code}            - Student's repository code
{previous_messages}       - Conversation history
{reference_solution_section} - Reference solution
{reference_comparison_section} - Diff against reference
{submission_history_section} - Previous attempts
```

#### `clarification.md`
```
{previous_messages}       - Conversation history (IMPORTANT!)
{student_code}            - Current code
```

#### `fallback.md` (Special)
```
{student_message}         - The actual message from student
{user_intent_description} - AI's interpretation of intent
```

### 🔒 Security Prompts:
```
{content}                 - Message/code to analyze
```

### 👤 Personality Prompts:
```
{tutor_name}             - Agent's name (e.g., "Tutor AI")
```

## Examples

### Using Variables in Strategy Prompt:
```markdown
You are helping a student debug their code.

Assignment:
---
{assignment_description}
---

{personality_prompt}

Student's Code:
---
{student_code}
---

Test Results:
{test_results_section}

Language: {language}
```

### Using Variables in Personality Prompt:
```markdown
You are {tutor_name}, a helpful assistant.
Keep responses in {language} language.
```

## Important Notes

1. **Variable names are case-sensitive**: Use exact spelling
2. **Missing variables**: Will show as "(No data available)" or similar
3. **Empty variables**: May be empty strings if data not available
4. **Don't remove variables**: Keep them even if sometimes empty
5. **Test with real data**: Variables may contain long content

## Testing Variables

In development mode, you can see what's being substituted:

```bash
# Run with verbose logging to see prompt construction
computor-agent tutor --dev -v --prompts-dir ./test

# Check logs for "LLM Request messages:" to see final prompt
```

---

*This is a quick reference. See README.md for the complete guide.*