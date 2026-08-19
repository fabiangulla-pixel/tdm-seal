from __future__ import annotations

from pathlib import Path

from tdmseal.appconfig import AppDefaults, load_defaults, save_defaults
from tdmseal.models import PublisherInfo


def test_load_defaults_without_file_returns_empty(tmp_path: Path):
    defaults = load_defaults(tmp_path / "does_not_exist.json")

    assert defaults.publisher.is_empty()
    assert defaults.reservation == 1
    assert defaults.policy_url is None


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "config.json"
    original = AppDefaults(
        publisher=PublisherInfo(
            name="Editorial Universidad Ejemplo",
            acronym="EUE",
            website="https://editorial.example.edu",
            rights_email="derechos@editorial.example.edu",
        ),
        reservation=0,
        policy_url="https://editorial.example.edu/tdm/policy.jsonld",
    )

    save_defaults(original, path)
    loaded = load_defaults(path)

    assert loaded == original


def test_save_defaults_creates_parent_directory(tmp_path: Path):
    path = tmp_path / "nested" / "config.json"

    save_defaults(AppDefaults(), path)

    assert path.exists()
