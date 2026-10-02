"""Behavioral checks for public tutor input and configuration boundaries."""
import io
import logging
from types import SimpleNamespace
import zipfile

import pytest

from computor_agent.tutor.config import TutorConfig
from computor_agent.tutor.services.artifacts import ArtifactsService, _valid_public_image


def public_config():
    return {
        "public_mode": True,
        "triggers": {"check_submissions": False},
        "strategies": {"fallback": {"max_response_tokens": 512}},
        "notes": {"enabled": False},
        "context": {
            "include_previous_messages": 2,
            "include_course_member_comments": False,
            "include_test_results": False,
            "include_submission_history": False,
            "include_reference_comparison": False,
            "include_student_progress": False,
            "student_notes_enabled": False,
            "max_code_files": 5,
            "max_code_lines": 300,
        },
        "figure_review": {
            "enabled": True,
            "max_figures": 2,
            "max_image_bytes": 2 * 1024 * 1024,
            "max_response_tokens": 256,
            "image_extensions": [".png", ".jpg", ".jpeg"],
        },
    }


def test_public_mode_rejects_reference_and_oversized_figure_contract():
    config = public_config()
    assert TutorConfig.model_validate(config).public_mode
    config["context"]["include_reference_comparison"] = True
    with pytest.raises(ValueError, match="references"):
        TutorConfig.model_validate(config)
    config["context"]["include_reference_comparison"] = False
    config["figure_review"]["max_figures"] = 3
    with pytest.raises(ValueError, match="figure"):
        TutorConfig.model_validate(config)
    config["figure_review"]["max_figures"] = 2
    config["security"] = {"threat_log_path": "/tmp/luna-threats.log"}
    with pytest.raises(ValueError, match="content-bearing"):
        TutorConfig.model_validate(config)


def test_zip_bomb_and_parent_path_cannot_enter_context():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../secret.py", "print('secret')")
        archive.writestr("work.py", "A" * 200_000)
    result = ArtifactsService(None, public_mode=True)._extract_zip(
        stream.getvalue(), SimpleNamespace(id="synthetic"), max_files=5,
        max_total_size=100,
    )
    assert result.files == {}
    assert result.truncated
    assert "[unsafe path omitted]" in result.binary_files


def test_public_images_reject_type_spoofing_and_huge_dimensions():
    assert not _valid_public_image(b"<svg/>", "plot.png")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (5000).to_bytes(4, "big") + (10).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00" + b"\0" * 4
    assert not _valid_public_image(png, "plot.png")


def test_public_worker_suppresses_content_bearing_library_logs(caplog):
    from computor_agent.cli.main import enforce_public_logging

    secret = "synthetic learner source 8a83e43e"
    previous = logging.root.manager.disable
    try:
        with pytest.raises(ValueError, match="cannot write a log file"):
            enforce_public_logging(True, "/tmp/public-worker.log")
        assert logging.root.manager.disable == previous
        enforce_public_logging(True, None)
        logging.getLogger("third_party.inference").critical("provider failure: %s", secret)
        assert secret not in caplog.text
    finally:
        logging.disable(previous)


def test_public_worker_cannot_route_learner_content_to_another_provider():
    from computor_agent.settings.config import ComputorConfig

    data = {
        "backend": {"url": "https://api.computor.at", "api_token": "ctp_" + "a" * 32},
        "llm": {
            "provider": "openai", "model": "luna-public",
            "base_url": "http://10.77.0.20:8090/v1",
        },
        "tutor": public_config(),
    }
    data["tutor"]["figure_review"]["use_agent_llm"] = True
    ComputorConfig.from_dict(data).validate_public_inference()
    data["llm"]["base_url"] = "https://outside.example/v1"
    with pytest.raises(ValueError, match="private luna-public"):
        ComputorConfig.from_dict(data).validate_public_inference()
    data["llm"]["base_url"] = "http://10.77.0.20:8090/v1"
    data["vision_llm"] = {
        "provider": "openai", "model": "another-model",
        "base_url": "https://outside.example/v1",
    }
    with pytest.raises(ValueError, match="private luna-public"):
        ComputorConfig.from_dict(data).validate_public_inference()
