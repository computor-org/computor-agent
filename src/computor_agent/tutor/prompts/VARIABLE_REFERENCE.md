# Variable Reference Card

## Quick Reference - Available Variables by Prompt File

### `strategy/tutor.md` (every live reply)
```
{personality_prompt}           - The personality text (from personality/<tone>.md)
{language}                     - Response language (en, de, etc.)
{student_section}              - Name(s) of the student(s) in the submission group
{assignment_section}           - Current assignment details
{code_section}                 - Student's latest submitted code
{test_results_section}         - Test execution results
{previous_messages_section}    - Conversation history
{reference_comparison_section} - Comparison against the reference solution
{figure_review_section}        - Vision-LLM review of figures in the submission
```

`{student_section}` names the student(s) in the submission group (and, in
group threads, who wrote the current message) so the tutor can address
people and tell group members apart. Names only — emails and ids are never
put into the prompt. Each section is an empty string when its context is
unavailable, and a file that leaves a placeholder out still works; that
section is simply omitted.

### 👤 `personality/*.md`
```
{tutor_name}             - Agent's name (tutor.personality.name, e.g. "Lena")
```

### `figure_review/review.md`
```
{assignment_section}     - Assignment details
{figure_path}            - Path of the figure in the submission
{language}               - Response language
```

### `unit_description/unit_description.md`
```
{language_name}          - Name of the language the draft is written in
{max_chars}              - Target maximum length of the draft
```

### `grading/grading.md`
```
{context}                - Assignment, reference solution and submission
```

### 🔒 Security Prompts:
```
{content}                - Message/code to analyze
{initial_detection}      - Result of the first check (confirmation.md only)
```
Both are required. An override that drops one or adds another is ignored and
the built-in prompt runs instead.

## Examples

### Using Variables in `strategy/tutor.md`:
```markdown
{personality_prompt}

{student_section}

{assignment_section}

{code_section}

{test_results_section}

{previous_messages_section}

Respond in {language}.
```

### Using Variables in Personality Prompt:
```markdown
You are {tutor_name}, a helpful assistant.
```

## Important Notes

1. **Variable names are case-sensitive**: Use exact spelling
2. **Unknown variables**: In `tutor.md`, `personality/*.md`, `figure_review/review.md`
   and `grading/grading.md` an unknown `{name}` makes the prompt fail; write
   literal braces as `{{` and `}}`
3. **Empty variables**: May be empty strings if data not available
4. **Don't remove variables**: Keep them even if sometimes empty
5. **Test with real data**: Variables may contain long content

## Testing Variables

In development mode, you can see what's being substituted:

```bash
# Run with verbose logging and content logging to see prompt construction
computor-agent tutor messaging --dev -v --log-llm-content --prompts-dir ./test
```

---

*This is a quick reference. See README.md for the complete guide.*
