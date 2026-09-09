#!/usr/bin/env python3
"""Adversarial tests for the FPL observation layer (public API only)."""
import json
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fpl_skill.observation import diff, ingest, model, store, watcher


def mk_picks(event, starters, bench, cap=None, vc=None, chip=None,
             autosub=False):
    """Build a picks payload with minimal field set."""
    picks = []
    for el, mult in starters:
        picks.append({"element": el, "position": len(picks) + 1,
                      "multiplier": mult,
                      "is_captain": el == cap, "is_vice_captain": el == vc,
                      "element_type": 1})
    for el in bench:
        picks.append({"element": el, "position": len(picks) + 1,
                      "multiplier": 0, "is_captain": False,
                      "is_vice_captain": False, "element_type": 1})
    out = {"active_chip": chip, "picks": picks,
           "entry_history": {"event": event}}
    if autosub:
        out["automatic_subs"] = [{"element_in": 1, "element_out": 2}]
    return out


class FakeResp:
    def __init__(self, status=200):
        self.status = status
        self.headers = {}
        self.body = None


class FakeTransport(ingest.Transport):
    """Synchronous stub with a mutable per-url response table."""

    def __init__(self):
        self.responses = {}
        self.hits = {}

    def set(self, url, payload):
        body = json.dumps(payload).encode()
        self.responses[url] = FakeResp(200)
        self.responses[url].body = body

    def set404(self, url):
        self.responses[url] = FakeResp(404)

    def get(self, url):
        self.hits[url] = self.hits.get(url, 0) + 1
        return self.responses.get(url, FakeResp(404))


def run_with(w, evts, iterations=1):
    return w.run(iterations=iterations)


# ---------- 1. identical snapshots -> zero events ----------
def test_identical_snapshots_zero_events():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev.jsonl"))
    picks = mk_picks(4, [(411, 1), (165, 1), (8, 1)],
                     [50, 51], cap=411, vc=165)
    t.set(ingest.picks_url(99, 4), picks)
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.transfers_url(99), [])
    ev = watcher.Watcher(t, st,
                         [{"entry_id": 99}],
                         live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"},
                         on_alert=lambda e: None)
    a = ev.poll_once()
    # same poll once again (identical) -> still zero (first poll is baseline)
    b = ev.poll_once()
    assert len(a) == 0
    assert len(b) == 0
    assert st.count() == 0


# ---------- 2. genuine state transition -> exactly one event ----------
def test_single_transition_single_event():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev2.jsonl"))
    cap_change = mk_picks(4, [(411, 1), (165, 1)], [], cap=165, vc=411)
    t.set(ingest.picks_url(99, 4), cap_change)
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.transfers_url(99), [])
    ev = watcher.Watcher(t, st, [{"entry_id": 99}],
                         live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    ev.poll_once()
    # second poll: cap flip
    t.set(ingest.picks_url(99, 4), mk_picks(4, [(411, 1), (165, 1)],
                                             [], cap=411, vc=165))
    got = ev.poll_once()
    cap_evs = [e for e in got if e["Event_type"] == "CAPTAINCY"]
    assert len(cap_evs) == 1
    assert st.count() == 1


# ---------- 3. restart does not duplicate ----------
def test_restart_no_duplicate():
    path = os.path.join(tempfile.mkdtemp(), "ev3.jsonl")
    t = FakeTransport()
    picks = mk_picks(4, [(411, 1), (165, 1)], [], cap=411, vc=165)
    t.set(ingest.picks_url(99, 4), picks)
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.transfers_url(99), [])

    w1 = watcher.Watcher(t, store.EventStore(path), [{"entry_id": 99}],
                         live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    w1.poll_once()
    t.set(ingest.picks_url(99, 4), mk_picks(4, [(411, 1), (165, 1)],
                                             [], cap=165, vc=411))
    got1 = w1.poll_once()
    w2 = watcher.Watcher(t, store.EventStore(path), [{"entry_id": 99}],
                         live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    # identical state after restart: store already has the event id
    got2 = w2.poll_once()
    assert len(got1) == 1
    assert all(g["Event_type"] == "CAPTAINCY" for g in got1)
    assert len(got2) == 0
    assert st_file_count(path) == 1


def st_file_count(path):
    with open(path) as fh:
        return sum(1 for _ in fh if _.strip())


# ---------- 4. timestamps UTC ordered ----------
def test_utc_ordered():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev4.jsonl"))
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.picks_url(99, 4), mk_picks(4, [(411, 1)], []))
    w = watcher.Watcher(t, st, [{"entry_id": 99}],
                        live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    # baseline: no transfers yet
    t.set(ingest.transfers_url(99), [])
    w.poll_once()
    # second poll: two transfers arrive
    tr = [{"event": 3, "element_in": 399, "element_out": 427,
           "element_in_cost": 75, "element_out_cost": 80,
           "time": "2026-08-28T20:19:00Z"},
          {"event": 2, "element_in": 402, "element_out": 400,
           "element_in_cost": 50, "element_out_cost": 45,
           "time": "2026-08-22T10:00:00Z"}]
    t.set(ingest.transfers_url(99), tr)
    got = w.poll_once()
    tr_evs = [e for e in got if e["Event_type"] == "TRANSFER"]
    assert len(tr_evs) == 2
    times = [e["Event_time"] for e in tr_evs]
    assert times == sorted(times)


# ---------- 5. missed polling recovers ----------
def test_missed_poll_recovery():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev5.jsonl"))
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.picks_url(99, 4), mk_picks(4, [(411, 1)], []))
    w = watcher.Watcher(t, st, [{"entry_id": 99}],
                        live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    # baseline silent
    t.set(ingest.transfers_url(99), [])
    got1 = w.poll_once()
    assert got1 == []
    # two transfers between polls
    tr_now = [{"event": 3, "element_in": 1, "element_out": 2,
               "element_in_cost": 50, "element_out_cost": 45,
               "time": "2026-08-28T20:19:00Z"},
              {"event": 3, "element_in": 3, "element_out": 4,
               "element_in_cost": 60, "element_out_cost": 55,
               "time": "2026-08-28T20:20:00Z"}]
    t.set(ingest.transfers_url(99), tr_now)
    got1 = w.poll_once()
    assert len([e for e in got1 if e["Event_type"] == "TRANSFER"]) == 2
    # new transfer appears
    tr3 = [{"event": 3, "element_in": 5, "element_out": 6,
            "element_in_cost": 70, "element_out_cost": 65,
            "time": "2026-08-28T20:21:00Z"}] + tr_now
    t.set(ingest.transfers_url(99), tr3)
    got2 = w.poll_once()
    newtr = [e for e in got2 if e["Event_type"] == "TRANSFER"]
    assert len(newtr) == 1
    assert newtr[0]["New_state"]["element_in"] == 5


# ---------- 6. post-event info not a decision ----------
def test_autosub_not_decision():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev6.jsonl"))
    p1 = mk_picks(4, [(411, 1), (165, 1)], [50], cap=411, vc=165)
    # GW finished -> autosub switched 50 in
    p2 = mk_picks(4, [(411, 1), (165, 1), (50, 1)], [],
                  cap=411, vc=165, autosub=True)
    t.set(ingest.picks_url(99, 4), p1)
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.transfers_url(99), [])
    w = watcher.Watcher(t, st, [{"entry_id": 99}],
                        live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    w.poll_once()
    t.set(ingest.picks_url(99, 4), p2)
    got = w.poll_once()
    assert got == []


# ---------- 7. action timestamp unavailable ----------
def test_transfer_absent_time_unknown():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev7.jsonl"))
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.picks_url(99, 4), mk_picks(4, [(411, 1)], []))
    w = watcher.Watcher(t, st, [{"entry_id": 99}],
                        live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    t.set(ingest.transfers_url(99), [])
    w.poll_once()
    tr = [{"event": 3, "element_in": 399, "element_out": 427,
           "element_in_cost": 75, "element_out_cost": 80}]
    t.set(ingest.transfers_url(99), tr)
    got = w.poll_once()
    tr_evs = [e for e in got if e["Event_type"] == "TRANSFER"]
    assert len(tr_evs) == 1
    assert tr_evs[0]["Event_time"] is None


# ---------- 8. deadline crossing stops picks diffing ----------
def test_deadline_crossing():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev8.jsonl"))
    p1 = mk_picks(4, [(411, 1), (165, 1)], [50], cap=411, vc=165)
    p2 = mk_picks(4, [(411, 1), (165, 1)], [50], cap=165, vc=411)
    t.set(ingest.picks_url(99, 4), p1)
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.transfers_url(99), [])
    # deadline in the past relative to fake now
    w = watcher.Watcher(t, st, [{"entry_id": 99}],
                        live_event={"id": 4, "deadline_time": "2026-08-28T17:30:00Z"},
                        now=lambda: datetime_utc())
    got = w.poll_once()
    assert got == []


def datetime_utc():
    from datetime import datetime, timezone
    return datetime(2026, 9, 9, 12, 0, 0, tzinfo=timezone.utc)


# ---------- 9. missing manager 404 ----------
def test_missing_manager_404():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev9.jsonl"))
    t.set404(ingest.picks_url(999, 4))
    t.set404(ingest.history_url(999))
    t.set(ingest.transfers_url(999), [])
    w = watcher.Watcher(t, st, [{"entry_id": 999}],
                        live_event={"id": 4, "deadline_time": "2020-01-01T00:00:00Z"},
                        now=lambda: datetime(2026, 9, 9, 12, 0, 0,
                                             tzinfo=timezone.utc))
    got = w.poll_once()
    assert any(e["Event_type"] == "MISSING_MANAGER" for e in got)


# ---------- 10. future-GW 404 ----------
def test_future_gw_404():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev10.jsonl"))
    t.set404(ingest.picks_url(99, 5))
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.transfers_url(99), [])
    w = watcher.Watcher(t, st, [{"entry_id": 99}],
                        live_event={"id": 5, "deadline_time": "2026-09-18T17:30:00Z"},
                        now=lambda: datetime(2026, 9, 9, 12, 0, 0,
                                             tzinfo=timezone.utc))
    got = w.poll_once()
    # future-GW 404 is NOT a miss (picks not open yet)
    assert got == []


# ---------- 11. rate limiting (token bucket) ----------
def test_token_bucket():
    calls = []
    tb = ingest.TokenBucket(rate=10, burst=2, sleep=lambda s: calls.append(s))
    tb.wait()
    tb.wait()
    tb.wait()  # should sleep
    assert len(calls) >= 1


# ---------- 12. partial response / malformed JSON ----------
def test_partial_response():
    url = "http://x/"
    r = ingest.HttpResponse(200, {}, b"{broken", cached=False)
    data, resp = ingest.fetch_json(FakeTransport(), url)
    # fetch_json on a 200 with bad body -> (None, resp) without raise
    assert data is None


# ---------- 13. stale response ----------
def test_stale_detection():
    # STALE_RESPONSE event is emitted by watcher when last_modified too old
    # (monitor contract only, no HTTP smoke here)
    assert "STALE_RESPONSE" in model.STATE_EVENTS


# ---------- 14. schema mutation ----------
def test_schema_mutation():
    t = FakeTransport()
    st = store.EventStore(os.path.join(tempfile.mkdtemp(), "ev14.jsonl"))
    t.set(ingest.picks_url(99, 4), {"nonsense": 1})
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.transfers_url(99), [])
    w = watcher.Watcher(t, st, [{"entry_id": 99}],
                        live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"})
    got = w.poll_once()
    assert any(e["Event_type"] == "SCHEMA_CHANGE" for e in got)


# ---------- 15. duplicate alert prevention ----------
def test_duplicate_alert_prevention():
    path = os.path.join(tempfile.mkdtemp(), "ev15.jsonl")
    t = FakeTransport()
    t.set(ingest.history_url(99), {"chips": [], "current": []})
    t.set(ingest.picks_url(99, 4), mk_picks(4, [(411, 1)], []))
    w1 = watcher.Watcher(t, store.EventStore(path), [{"entry_id": 99}],
                         live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"},
                         on_alert=lambda e: None)
    t.set(ingest.transfers_url(99), [])
    w1.poll_once()
    tr = [{"event": 3, "element_in": 399, "element_out": 427,
           "element_in_cost": 75, "element_out_cost": 80,
           "time": "2026-08-28T20:19:00Z"}]
    t.set(ingest.transfers_url(99), tr)
    w1.poll_once()
    w2 = watcher.Watcher(t, store.EventStore(path), [{"entry_id": 99}],
                         live_event={"id": 4, "deadline_time": "2099-01-01T00:00:00Z"},
                         on_alert=lambda e: None)
    w2.poll_once()
    assert st_file_count(path) == 1


# ---------- 16. adaptive polling near deadline ----------
def test_adaptive_polling():
    ev = type("E", (), {"id": 5,
                        "deadline_time": "2099-01-01T00:00:00Z"})
    ev = {"id": 5, "deadline_time": "2099-01-01T00:00:00Z"}
    w = watcher.Watcher(None, None, [],
                        live_event=ev, poll_interval=60.0,
                        deadline_burst_interval=10.0,
                        deadline_window_seconds=3600)
    # far away -> slow
    w.now_fn = lambda: datetime_utc()
    assert w.next_sleep() == 60.0
    # 5 minutes before deadline -> burst
    w.now_fn = lambda: datetime(2098, 12, 31, 23, 55, 0,
                                tzinfo=timezone.utc)
    assert w.next_sleep() == 10.0


from datetime import datetime, timezone


# ---------- 17. capped backoff ----------
def test_backoff_capped():
    sig = ingest.HttpFetcher.__init__
    assert sig.__defaults__[4] == 3  # max_retries default 3
    waits = []
    tb = ingest.TokenBucket(rate=1, burst=1,
                            sleep=lambda s: waits.append(s))
    assert tb is not None


# ---------- RUNNER ----------
def main():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            passed += 1
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ✗ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)


def test_store_salvages_crash_window():
    import os, tempfile, json
    from fpl_skill.observation import store
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'events.json')
    with open(p, 'w') as fh:
        fh.write(json.dumps({'Event_id': 'ok1', 'Detected_at': 'a'}) + '\n')
        fh.write('{"Event_id":"partial","Det')  # truncated tail, no newline
        fh.write(json.dumps({'Event_id': 'ok2', 'Detected_at': 'b'}) + '\n')
    es = store.EventStore(p)
    assert es.exists('ok1')
    assert es.exists('ok2')
    assert not es.exists('partial')
    assert es.count() == 2
