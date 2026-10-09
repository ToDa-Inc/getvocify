from app.services.live_report import AudioClock, LiveReport, percentiles


def test_lag_is_time_since_the_audio_arrived():
    clock = AudioClock()
    clock.add(3200, now=10.0)  # 0.1 s of audio
    clock.add(3200, now=10.1)  # up to 0.2 s
    assert round(clock.lag(0.2, now=10.9), 3) == 0.8
    assert round(clock.lag(0.05, now=10.9), 3) == 0.9
    assert clock.lag(5.0, now=11.0) is None  # not heard yet


def test_restart_drops_text_sent_again_and_untimed_results_keep_text():
    report = LiveReport(["rep", "prospect"], providers=["speechmatics"])
    report.audio("rep", 32000 * 3)
    report.result("speechmatics", "rep", final=True, start=0.5, end=1.0, text="hola")
    report.result("speechmatics", "rep", final=True, start=2.0, end=2.5, text="bon dia", timed=False)
    report.restarted("rep", "ca", 1.5)
    rep = report.tracks["speechmatics"]["rep"]
    assert [f[2] for f in rep.finals] == ["hola"]
    assert len(rep.final_lags) == 1
    summary = report.summary({"rep": "ca", "prospect": "es"})
    assert summary["restarts"] == [{"side": "rep", "language": "ca", "from_s": 1.5}]
    assert "deepgram" not in summary["providers"]


def test_percentiles():
    assert percentiles([]) is None
    assert percentiles([1.0, 2.0, 3.0, 4.0]) == {"p50": 3.0, "p90": 4.0, "max": 4.0, "n": 4}


def test_report_says_which_service_and_keeps_what_the_mac_measured():
    report = LiveReport(["rep"], providers=["deepgram"], service="api")
    report.from_client({"type": "ClientReport", "lag_s": {"rep": {"final": {"p50": 1.2}}}, "reconnects": 0})
    summary = report.summary({"rep": "es"})
    assert summary["service"] == "api" and summary["provider"] == "deepgram"
    assert summary["client"] == {"lag_s": {"rep": {"final": {"p50": 1.2}}}, "reconnects": 0}
    report.from_client({"lag_s": "nonsense"})
    assert report.summary({})["client"]["reconnects"] == 0


def test_report_goes_to_the_logs_with_both_transcripts(caplog):
    import logging

    report = LiveReport(["rep"], providers=["speechmatics", "deepgram"])
    report.result("speechmatics", "rep", final=True, start=1.0, end=2.0, text="hola qué tal")
    report.result("deepgram", "rep", final=True, start=1.0, end=2.0, text="hola que tal")
    with caplog.at_level(logging.INFO, logger="app.services.live_report"):
        report.log("u1", {"rep": "es"})
    lines = [r.getMessage() for r in caplog.records]
    assert lines[0].startswith("Live report ") and '"service": "live"' in lines[0]
    assert any("speechmatics rep 1/1 [1.0] hola qué tal" in line for line in lines)
    assert any("deepgram rep 1/1 [1.0] hola que tal" in line for line in lines)
    assert not any("\n" in line for line in lines)
