from app.extraction.prompts import (
    CANONICAL_BLOCK_HEADER,
    CUSTOM_FIELDS_HEADER,
    build_extraction_system_prompt,
)


def test_empty_prompt_has_no_alias_or_custom_block():
    p = build_extraction_system_prompt()
    assert CANONICAL_BLOCK_HEADER not in p
    assert CUSTOM_FIELDS_HEADER not in p


def test_aliases_grouped_by_canonical():
    aliases = {"js": "JavaScript", "javascript": "JavaScript", "py": "Python"}
    p = build_extraction_system_prompt(aliases=aliases)
    assert CANONICAL_BLOCK_HEADER in p
    assert "JavaScript: javascript, js" in p
    assert "Python: py" in p


def test_custom_fields_injected_into_prompt():
    fields = [
        {"name": "aws_certified", "type": "bool", "description": "AWS certification?"},
    ]
    p = build_extraction_system_prompt(custom_fields=fields)
    assert CUSTOM_FIELDS_HEADER in p
    assert "`aws_certified`" in p
    assert "AWS certification?" in p
