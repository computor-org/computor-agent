"""
Development mode for grading submissions.

Allows testing the grading system locally without API calls:
- Load reference solution from a directory
- Load student submission from a directory
- Run grading and display results
"""

import logging
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from computor_agent.tutor.assignment_loader import AssignmentLoader, AssignmentFile
from computor_agent.tutor.grading.models import (
    GradingContext,
    GradingResult,
    GradingStatus,
    StudentSubmission,
)
from computor_agent.tutor.grading.grader import SubmissionGrader

logger = logging.getLogger(__name__)
console = Console()


def load_student_submission(submission_path: Path, reference_files: list[AssignmentFile]) -> StudentSubmission:
    """
    Load student submission files from a directory.

    Uses the reference solution's file list to know which files to load.

    Args:
        submission_path: Path to student submission directory
        reference_files: List of files from the reference solution (to know what to look for)

    Returns:
        StudentSubmission with loaded files
    """
    files = []

    # Get submission file paths from reference
    submission_file_paths = [f.path for f in reference_files if f.is_submission_file]

    for rel_path in submission_file_paths:
        file_path = submission_path / rel_path

        if not file_path.exists():
            logger.warning(f"Student file not found: {file_path}")
            # Add empty placeholder so we know it's missing
            files.append(AssignmentFile(
                path=rel_path,
                content=f"# FILE NOT FOUND: {rel_path}",
                is_submission_file=True,
            ))
            continue

        try:
            content = file_path.read_text()
            files.append(AssignmentFile(
                path=rel_path,
                content=content,
                is_submission_file=True,
            ))
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")
            files.append(AssignmentFile(
                path=rel_path,
                content=f"# ERROR READING FILE: {e}",
                is_submission_file=True,
            ))

    return StudentSubmission(files=files, submission_path=submission_path)


def display_grading_result(result: GradingResult) -> None:
    """Display the grading result in a nice format."""
    # Status color mapping
    status_colors = {
        GradingStatus.CORRECTED: "green",
        GradingStatus.CORRECTION_NECESSARY: "red",
        GradingStatus.IMPROVEMENT_POSSIBLE: "yellow",
        GradingStatus.NOT_REVIEWED: "dim",
    }
    status_color = status_colors.get(result.status, "white")

    # Build the result panel
    grade_bar = "█" * int(result.grade * 20) + "░" * (20 - int(result.grade * 20))

    content_lines = [
        f"[bold]Grade:[/bold] {result.grade_percentage}% [{status_color}]{grade_bar}[/{status_color}]",
        f"[bold]Status:[/bold] [{status_color}]{result.status.to_display_string()}[/{status_color}]",
        "",
        f"[bold]Summary:[/bold] {result.summary}",
    ]

    if result.issues:
        content_lines.append("")
        content_lines.append("[bold red]Issues:[/bold red]")
        for issue in result.issues:
            content_lines.append(f"  • {issue}")

    if result.suggestions:
        content_lines.append("")
        content_lines.append("[bold yellow]Suggestions:[/bold yellow]")
        for suggestion in result.suggestions:
            content_lines.append(f"  • {suggestion}")

    console.print(Panel(
        "\n".join(content_lines),
        title="Grading Result",
        border_style=status_color,
    ))

    # Show detailed feedback in separate panel
    if result.feedback:
        console.print(Panel(
            result.feedback,
            title="Detailed Feedback",
            border_style="cyan",
        ))


async def run_grading_dev_mode(
    config_path: Path,
    reference_path: Path,
    student_path: Path,
    verbose: bool = False,
    language: Optional[str] = None,
    prompts_dir: Optional[Path] = None,
) -> GradingResult:
    """
    Run grading in development mode.

    Args:
        config_path: Path to configuration file
        reference_path: Path to reference solution directory (with meta.yaml)
        student_path: Path to student submission directory
        verbose: Enable verbose logging
        language: Language for assignment description (default: from meta.yaml)
        prompts_dir: Directory for custom prompt files

    Returns:
        GradingResult with the grading outcome
    """
    from computor_agent.settings import ComputorConfig
    from computor_agent.llm.config import LLMConfig, ProviderType
    from computor_agent.llm.factory import get_provider
    from computor_agent.tutor import TutorLLMAdapter

    # Load configuration
    logger.info(f"Loading config from {config_path}")
    computor_config = ComputorConfig.from_file(config_path)

    # Build info panel
    info_lines = [
        "[bold green]Grading Development Mode[/bold green]\n",
        f"LLM: [green]{computor_config.llm.provider}[/green] ([green]{computor_config.llm.model}[/green])",
        f"Reference: [cyan]{reference_path}[/cyan]",
        f"Student: [cyan]{student_path}[/cyan]",
    ]

    if prompts_dir:
        info_lines.append(f"Prompts: [cyan]{prompts_dir}[/cyan]")

    console.print(Panel(
        "\n".join(info_lines),
        title="Tutor Agent - Grading Mode",
        border_style="green",
    ))

    # Load reference solution (assignment)
    console.print("[dim]Loading reference solution...[/dim]")
    try:
        assignment = AssignmentLoader.load_from_path(reference_path, language)
        console.print(f"[green]✓ Loaded assignment: {assignment.title}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to load reference solution: {e}[/red]")
        raise

    # Show assignment info
    console.print(Panel(
        f"[bold]{assignment.title}[/bold]\n\n"
        f"Identifier: [cyan]{assignment.identifier}[/cyan]\n"
        f"Language: {assignment.language}\n"
        f"Files: {', '.join(f.path for f in assignment.files)}",
        title="Assignment Info",
        border_style="cyan",
    ))

    # Load student submission
    console.print("[dim]Loading student submission...[/dim]")
    student_submission = load_student_submission(student_path, assignment.files)

    if not student_submission.files:
        console.print("[red]No student files found![/red]")
        raise ValueError("No student submission files found")

    console.print(f"[green]✓ Loaded {len(student_submission.files)} student file(s)[/green]")

    # Show file comparison
    table = Table(title="Files")
    table.add_column("File", style="cyan")
    table.add_column("Reference", style="green")
    table.add_column("Student", style="yellow")

    for ref_file in assignment.get_submission_files():
        student_file = student_submission.get_file(ref_file.path)
        ref_lines = len(ref_file.content.splitlines())
        student_lines = len(student_file.content.splitlines()) if student_file else 0

        table.add_row(
            ref_file.path,
            f"{ref_lines} lines",
            f"{student_lines} lines" if student_file else "[red]MISSING[/red]",
        )

    console.print(table)

    # Create grading context
    context = GradingContext(
        assignment_title=assignment.title,
        assignment_description=assignment.readme_content,
        reference_solution=assignment.get_submission_files(),
        student_submission=student_submission,
        language=assignment.language,
    )

    # Create LLM provider
    if not computor_config.llm:
        console.print("[bold red]Error:[/bold red] LLM configuration is required")
        raise ValueError("LLM configuration is required")

    llm_config = LLMConfig(
        provider=ProviderType(computor_config.llm.provider),
        model=computor_config.llm.model,
        base_url=computor_config.llm.base_url,
        api_key=computor_config.llm.get_api_key(),
        temperature=computor_config.llm.temperature,
    )
    llm_provider = get_provider(llm_config)
    tutor_llm = TutorLLMAdapter(llm_provider)

    # Load custom grading prompt if prompts_dir is specified
    grading_prompt = None
    if prompts_dir:
        grading_prompt_path = prompts_dir / "grading" / "grading.md"
        if grading_prompt_path.exists():
            try:
                grading_prompt = grading_prompt_path.read_text().strip()
                logger.info(f"Loaded custom grading prompt from {grading_prompt_path}")
            except Exception as e:
                logger.warning(f"Failed to load grading prompt: {e}")

    # Create grader and run grading
    grader = SubmissionGrader(tutor_llm, prompt_template=grading_prompt)

    console.print("\n[bold]Grading submission (multi-step analysis)...[/bold]")

    # Use status context manager with progress callback
    status = console.status("[bold green]Starting analysis...")
    status.start()

    def update_progress(step: str) -> None:
        status.update(f"[bold green]{step}")

    try:
        result = await grader.grade(context, progress_callback=update_progress)
    finally:
        status.stop()

    # Display result
    display_grading_result(result)

    # Cleanup
    await tutor_llm.close()

    return result
