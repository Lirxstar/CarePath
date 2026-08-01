from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_canonical_repository_structure_exists() -> None:
    required_directories = {
        ".github",
        "agents",
        "apps/mobile",
        "backend",
        "backend/api",
        "data",
        "deployment",
        "docs",
        "evaluation",
        "personalization",
        "retrieval",
        "safety",
        "tests",
        "timeseries",
    }
    assert all((ROOT / path).is_dir() for path in required_directories)


def test_legacy_top_level_mobile_directory_is_absent() -> None:
    assert not (ROOT / "mobile").exists()


def test_canonical_governance_files_exist() -> None:
    required_files = {
        ".gitignore",
        ".env.example",
        "ISSUE_BOARD.md",
        "LICENSE",
        "PROJECT_SCOPE.md",
        "README.md",
        "SECURITY_AND_DATA_POLICY.md",
    }
    assert all((ROOT / path).is_file() for path in required_files)


def test_backend_is_an_installable_python_package() -> None:
    required_package_files = {
        "backend/__init__.py",
        "backend/api/__init__.py",
        "backend/api/app/__init__.py",
    }
    assert all((ROOT / path).is_file() for path in required_package_files)


def test_gitignore_protects_sensitive_and_generated_content() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    required_patterns = {
        ".env",
        "!.env.example",
        "data/private/",
        "data/generated/",
        "*.ckpt",
        "*.safetensors",
    }
    assert required_patterns.issubset(set(gitignore.splitlines()))
