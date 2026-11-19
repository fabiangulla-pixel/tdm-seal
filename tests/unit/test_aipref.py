from __future__ import annotations

import pytest

from tdmseal.aipref import (
    CATEGORIES,
    DEFAULT_PREFERENCES,
    VOCAB_DRAFT,
    AiPreferences,
    AiPrefError,
    default_preferences,
)


def test_categories_match_vocab_08():
    # Si el borrador cambia, esta prueba obliga a revisar a conciencia.
    assert CATEGORIES == ("train-ai", "ai-use", "search")
    assert VOCAB_DRAFT == "draft-ietf-aipref-vocab-08"


def test_default_preferences():
    prefs = default_preferences()
    assert prefs.serialize() == DEFAULT_PREFERENCES == "train-ai=n, ai-use=n, search=y"
    assert prefs.denies_ai()


def test_parse_normalizes_order_spacing_and_last_wins():
    prefs = AiPreferences.parse("search=y,train-ai=y ,  train-ai=n")
    assert prefs.serialize() == "train-ai=n, search=y"
    assert prefs.get("ai-use") is None


def test_parameters_are_ignored():
    assert AiPreferences.parse("train-ai=n;x=1").serialize() == "train-ai=n"


@pytest.mark.parametrize(
    "bad",
    ["tdm=n", "train-genai=n", "train-ai=no", "train-ai", "Train-AI=n", "", "train ai=n"],
)
def test_rejects_unknown_or_malformed(bad):
    with pytest.raises(AiPrefError):
        AiPreferences.parse(bad)


def test_consistency_with_tdmrep():
    prefs = AiPreferences.parse("train-ai=n")
    assert prefs.check_consistency(1) == []
    assert "Contradicción" in prefs.check_consistency(0)[0]
    assert AiPreferences.parse("search=y").check_consistency(0) == []


def test_report_says_not_embedded():
    report = default_preferences().to_report()
    assert report["embedded_in_file"] is False
    assert report["content_usage"] == DEFAULT_PREFERENCES
    assert "1.3.1" in report["note"]
