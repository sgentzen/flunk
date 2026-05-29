from flunk.catalog.metadata import SECURITY_RULES, is_security_rule


def test_security_rules_locked() -> None:
    assert is_security_rule("flunk.sql-injection")
    assert is_security_rule("flunk.csrf-middleware")
    assert is_security_rule("flunk.f811-suppression")
    assert is_security_rule("flunk.bare-except-security")


def test_judgment_rules_not_security() -> None:
    assert not is_security_rule("flunk.async-client-in-fn")
    assert not is_security_rule("flunk.duplication")
    assert not is_security_rule("flunk.humanize")


def test_set_is_subset_of_catalog() -> None:
    from flunk.catalog.metadata import CATALOG
    assert SECURITY_RULES <= set(CATALOG)
