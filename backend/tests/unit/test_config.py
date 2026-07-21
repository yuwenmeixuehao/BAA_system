from pathlib import Path

from app.core.config import BACKEND_ROOT, ENV_FILES, PROJECT_ROOT, Settings


def test_cors_origins_are_parsed_from_comma_separated_value() -> None:
    settings = Settings(CORS_ORIGINS="http://localhost:5173,http://127.0.0.1:5173")

    assert settings.cors_origin_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_default_env_files_are_absolute_and_independent_of_working_directory() -> None:
    assert ENV_FILES == (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env")
    assert all(path.is_absolute() for path in ENV_FILES)


def test_empty_override_does_not_replace_filled_model_config(tmp_path: Path) -> None:
    base = tmp_path / "base.env"
    override = tmp_path / "override.env"
    base.write_text(
        "MODEL_PROVIDER=openai_compatible\n"
        "MODEL_NAME=shared-model\n"
        "API_KEY=fake-secret\n",
        encoding="utf-8",
    )
    override.write_text("MODEL_NAME=\nAPI_KEY=\n", encoding="utf-8")

    settings = Settings(_env_file=(base, override))

    assert settings.analysis_model_name == "shared-model"
    assert settings.analysis_model_api_key == "fake-secret"


def test_relative_agent_data_root_is_resolved_from_backend_root() -> None:
    settings = Settings(_env_file=None, AGENT_DATA_ROOT="../data")

    assert settings.agent_data_root == (PROJECT_ROOT / "data").resolve()


def test_worker_redis_timeout_exceeds_blocking_queue_wait() -> None:
    settings = Settings(
        _env_file=None,
        TASK_WORKER_BLOCK_TIMEOUT_SECONDS=20,
        TASK_WORKER_REDIS_SOCKET_TIMEOUT_SECONDS=3,
    )

    assert settings.effective_worker_redis_socket_timeout_seconds == 25
