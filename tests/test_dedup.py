import pytest

from lead_engine.pipeline.dedup import DedupEngine, classify_ratio
from lead_engine.pipeline.normalize import normalize_text

SETTINGS = {"dedup": {"auto_merge_threshold": 0.95, "review_threshold": 0.85}}


def engine():
    return DedupEngine(SETTINGS)


def test_arabic_normalization():
    assert normalize_text("عيادة الأسنان") == normalize_text("عياده الاسنان")
    assert normalize_text("Al-Zahra") == normalize_text("al zahra")


def test_classify_ratio_thresholds():
    assert classify_ratio(0.96, 0.95, 0.85) == "merge"
    assert classify_ratio(0.95, 0.95, 0.85) == "review"   # strictly above auto
    assert classify_ratio(0.90, 0.95, 0.85) == "review"
    assert classify_ratio(0.50, 0.95, 0.85) == "separate"


def test_stage1_exact_domain_merge():
    leads = [
        {"name": "Al Zahra Dental Clinic", "domain": "alzahradental.com",
         "city": "Jeddah", "country": "SA", "sources": ["search_api"]},
        {"name": "عيادة الزهراء لطب الأسنان", "domain": "alzahradental.com",
         "city": "Jeddah", "country": "SA", "sources": ["search_api"]},
    ]
    merged, stats = engine().run(leads)
    assert stats.output_count == 1
    assert merged[0]["merged_count"] == 2
    # richer record wins: english name appears first in input
    assert stats.duplicate_rate == 0.5


def test_stage3_fuzzy_auto_merge_without_domain():
    leads = [
        {"name": "Gulf Dental Group", "domain": None, "city": "Riyadh", "country": "SA"},
        {"name": "Gulf  Dental  Group!", "domain": None, "city": "Riyadh", "country": "SA"},
    ]
    merged, stats = engine().run(leads)
    assert stats.output_count == 1  # normalize_text -> identical -> ratio 1.0


def test_conflicting_domains_never_merge():
    leads = [
        {"name": "Elite Dental Clinic", "domain": "elite-dental-jed.com",
         "city": "Jeddah", "country": "SA"},
        {"name": "Elite Dental Clinic", "domain": "elite-dental-riyadh.com",
         "city": "Jeddah", "country": "SA"},
    ]
    merged, stats = engine().run(leads)
    assert stats.output_count == 2


def test_contact_exact_email_merges_across_cities():
    leads = [
        {"name": "A Clinic", "domain": "a.com", "city": "Jeddah", "country": "SA",
         "email": "owner@a.com"},
        {"name": "B Clinic", "domain": None, "city": "Riyadh", "country": "SA",
         "email": "OWNER@A.com"},
    ]
    merged, stats = engine().run(leads)
    assert stats.output_count == 1
    assert merged[0]["domain"] == "a.com"
