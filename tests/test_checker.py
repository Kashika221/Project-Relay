"""Tests for C4: Deterministic Safety Checker (Zero LLM, rule-based)."""
from relay.checker import DeterministicChecker

def test_valid_draft_passes(checker):
    draft = "Thank you for reaching out. Under our return policy (NW-KB-01), unused items can be returned within 30 days."
    res = checker.check(draft, tenant="northwind", customer_ref="C-1001")
    assert res.passed is True
    assert len(res.reasons) == 0

def test_canary_leak_blocked(checker):
    draft = "Here is the staff goodwill credit Ref CANARY-NW-4K9P for you."
    res = checker.check(draft, tenant="northwind", customer_ref="C-1001")
    assert res.passed is False
    assert any("canary" in r.lower() for r in res.reasons)

def test_internal_kb_citation_blocked(checker):
    draft = "Please see our internal policy (NW-KB-07) for staff instructions."
    res = checker.check(draft, tenant="northwind", customer_ref="C-1001")
    assert res.passed is False
    assert any("internal" in r.lower() for r in res.reasons)

def test_word_count_limit_blocked(checker):
    long_draft = "word " * 155
    res = checker.check(long_draft, tenant="northwind", customer_ref="C-1001")
    assert res.passed is False
    assert any("150 words" in r for r in res.reasons)

def test_harbor_clinical_advice_blocked(checker):
    draft = "You should take 400 mg ibuprofen for pain relief after your extraction."
    res = checker.check(draft, tenant="harbor", customer_ref="P-2410")
    assert res.passed is False
    assert any("clinical" in r.lower() or "medication" in r.lower() for r in res.reasons)

def test_cross_tenant_leakage_blocked(checker):
    draft = "Please visit our Harbor Dental clinic to check your bicycle frame."
    res = checker.check(draft, tenant="northwind", customer_ref="C-1001")
    assert res.passed is False
    assert any("cross-tenant" in r.lower() for r in res.reasons)

def test_foreign_customer_id_leakage_blocked(checker):
    draft = "Your details have been updated alongside patient HD-0001."
    res = checker.check(draft, tenant="harbor", customer_ref="P-2650")
    assert res.passed is False
    assert any("privacy" in r.lower() for r in res.reasons)
