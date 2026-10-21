from scripts.backfill_company_name_key import plan


def row(i, name, domain=None, city="Jeddah", org="o1", key=None):
    return {"id": i, "org_id": org, "canonical_name": name, "domain": domain,
            "city": city, "name_key": key}


def test_fills_missing_keys_and_is_idempotent():
    rows = [row("1", "Al Zahra Dental Clinic")]
    first = plan(rows)
    assert first["updates"] == [("1", "zahra")]
    rows[0]["name_key"] = "zahra"           # after applying
    assert plan(rows)["updates"] == []       # re-run writes nothing


def test_generic_names_are_left_null_not_guessed():
    out = plan([row("1", "Dental Clinic"), row("2", "عيادة أسنان")])
    assert out["updates"] == [] and out["skipped_generic"] == 2


def test_reports_same_business_as_candidate_but_never_merges():
    out = plan([row("1", "Al Zahra Dental Center (@alzahradental)"),
                row("2", "Al Zahra Dental Clinic", "alzahradental.com")])
    assert len(out["merge_candidates"]) == 1
    assert set(out["merge_candidates"][0]["ids"]) == {"1", "2"}


def test_different_domains_are_not_candidates():
    out = plan([row("1", "أفضل عيادة أسنان بالرياض", "a.sa", "Riyadh"),
                row("2", "افضل عياده اسنان بالرياض", "b.sa", "Riyadh")])
    assert out["merge_candidates"] == []


def test_different_city_or_org_never_grouped():
    assert plan([row("1", "Elite Dental", city="Jeddah"),
                 row("2", "Elite Dental", city="Riyadh")])["merge_candidates"] == []
    assert plan([row("1", "Elite Dental", org="a"),
                 row("2", "Elite Dental", org="b")])["merge_candidates"] == []


def test_stale_key_is_cleared_when_the_name_is_now_generic():
    """A key written by an older rule must not keep matching once the name is
    judged generic: it is set back to NULL (None), not silently left behind."""
    rows = [{"id": "1", "org_id": "o", "canonical_name": "best dental hospital in saudi arabia",
             "domain": None, "city": "Riyadh", "name_key": "arabia best saudi"}]
    out = plan(rows)
    assert out["updates"] == [("1", None)]
    assert out["skipped_generic"] == 1


def test_generic_row_with_no_key_needs_no_write():
    rows = [{"id": "1", "org_id": "o", "canonical_name": "Dental Clinic",
             "domain": None, "city": None, "name_key": None}]
    assert plan(rows)["updates"] == []
