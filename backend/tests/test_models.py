import os

import pytest

from junior.models import MODELS_FILE, ModelConfigError, get_router, parse_router

GOOD = """
[tiers]
strong = "big-model"
small = "tiny-model"

[agents]
summarizer = "small"
writer = "special-model"

[prices."big-model"]
input = 2.0
cached_input = 0.1
output = 10.0

[prices."tiny-model"]
input = 0.1
output = 0.5

[prices."special-model"]
input = 1.0
output = 1.0
"""


def test_the_real_file_is_valid():
    router = get_router(MODELS_FILE)
    assert router.model_for("junior_muneer") == router.tiers["strong"]


def test_agents_use_their_tier_or_override():
    router = parse_router(GOOD)
    assert router.model_for("junior_muneer") == "big-model"
    assert router.model_for("anything", default_tier="small") == "tiny-model"
    assert router.model_for("summarizer") == "tiny-model"
    assert router.model_for("writer") == "special-model"


def test_cost_counts_cached_tokens_at_the_cached_price():
    price = parse_router(GOOD).price("big-model")
    # 1M input tokens of which 400k cached, plus 100k output tokens
    assert price.cost(1_000_000, 100_000, cached_input_tokens=400_000) == pytest.approx(
        0.6 * 2.0 + 0.4 * 0.1 + 0.1 * 10.0
    )


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not toml [[[", "not valid TOML"),
        ('[agents]\nx = "small"', "missing the [tiers] section"),
        ('[tiers]\nstrong = "a"', "small"),
        ('[tiers]\nstrong = "a"\nsmall = "b"\nhuge = "c"', "unknown tier"),
        ('[tiers]\nstrong = "a"\nsmall = "b"', "no price for ['a', 'b']"),
        (GOOD + '\n[prices."bad"]\ninput = "cheap"\noutput = 1', 'prices."bad"'),
        (GOOD.replace('writer = "special-model"', 'writer = "unpriced"'), "unpriced"),
    ],
)
def test_mistakes_give_a_clear_error(text, message):
    with pytest.raises(ModelConfigError) as err:
        parse_router(text)
    assert message in str(err.value)


def test_editing_the_file_changes_the_model_without_a_restart(tmp_path):
    path = tmp_path / "models.toml"
    path.write_text(GOOD)
    assert get_router(path).model_for("junior_muneer") == "big-model"

    path.write_text(GOOD.replace('strong = "big-model"', 'strong = "special-model"'))
    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + 5))  # make sure the change is seen
    assert get_router(path).model_for("junior_muneer") == "special-model"


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(ModelConfigError, match="not found"):
        get_router(tmp_path / "nope.toml")
