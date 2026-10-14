"""Placeholder translation: `?` -> `%s` must skip quoted literals.

The old implementation was a blind sql.replace("?", "%s"), so any literal
question mark inside a SQL string constant was corrupted into a parameter
marker (gap register: "any literal ? inside a SQL string constant is
corrupted. Reproduced in isolation."). These tests pin the contract:

  - real placeholders are translated, including ?::jsonb casts
  - literal ? inside single-quoted strings survives verbatim
  - literal ? inside double-quoted identifiers survives verbatim
  - '' escape inside a string does not end the literal
  - the parameter COUNT is unchanged (callers bind positionally)
"""
from lead_engine.db_pg import _translate_placeholders


def test_plain_placeholders_translate():
    assert _translate_placeholders("SELECT * FROM jobs WHERE job_id = ?") == \
        "SELECT * FROM jobs WHERE job_id = %s"


def test_multiple_placeholders_translate_in_order():
    assert _translate_placeholders("INSERT INTO t (a, b, c) VALUES (?,?,?)") == \
        "INSERT INTO t (a, b, c) VALUES (%s,%s,%s)"


def test_jsonb_cast_placeholder_translates():
    # provisioning.py emits "?::jsonb" on Postgres — the ? is a parameter.
    assert _translate_placeholders("UPDATE t SET steps = ?::jsonb WHERE id = ?") == \
        "UPDATE t SET steps = %s::jsonb WHERE id = %s"


def test_literal_question_mark_in_string_survives():
    assert _translate_placeholders(
        "SELECT * FROM t WHERE a = ? AND note = 'is this ok?'") == \
        "SELECT * FROM t WHERE a = %s AND note = 'is this ok?'"


def test_string_containing_only_a_question_mark():
    assert _translate_placeholders("SELECT * FROM t WHERE a = '?'") == \
        "SELECT * FROM t WHERE a = '?'"


def test_escaped_quote_does_not_end_the_literal():
    # 'it''s? fine' is ONE literal containing a question mark.
    assert _translate_placeholders(
        "SELECT * FROM t WHERE a = 'it''s? fine' AND b = ?") == \
        "SELECT * FROM t WHERE a = 'it''s? fine' AND b = %s"


def test_question_mark_in_double_quoted_identifier_survives():
    # Postgres treats "..." as an identifier; a ? there is not a parameter.
    assert _translate_placeholders(
        'SELECT "col?x" FROM t WHERE y = ?') == \
        'SELECT "col?x" FROM t WHERE y = %s'


def test_parameter_count_is_preserved():
    sql = ("SELECT * FROM leads WHERE job_id = ? AND stage = ? "
           "AND note = 'why?' AND tag = 'ok?' ORDER BY x")
    out = _translate_placeholders(sql)
    assert out.count("%s") == 2
    assert out.count("?") == 2  # the two literal ones


def test_engine_regression_suite_strings_unchanged():
    # Real SQL shapes from the codebase must translate exactly as before.
    cases = [
        ("UPDATE jobs SET state=?, pause_reason=?, updated_at=?"
         " WHERE job_id=? AND state=?",
         "UPDATE jobs SET state=%s, pause_reason=%s, updated_at=%s"
         " WHERE job_id=%s AND state=%s"),
        ("SELECT * FROM providers WHERE task = ? ORDER BY priority ASC",
         "SELECT * FROM providers WHERE task = %s ORDER BY priority ASC"),
        ("INSERT INTO usage_ledger (ts, provider, task, job_id, units,"
         " unit_kind, status, latency_ms, prompt_tokens, completion_tokens,"
         " key_index) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
         "INSERT INTO usage_ledger (ts, provider, task, job_id, units,"
         " unit_kind, status, latency_ms, prompt_tokens, completion_tokens,"
         " key_index) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"),
        # JSON operators with literal text and one placeholder
        ("SELECT raw->>'pipeline' FROM leads WHERE lead_id = ?",
         "SELECT raw->>'pipeline' FROM leads WHERE lead_id = %s"),
    ]
    for src, want in cases:
        assert _translate_placeholders(src) == want
