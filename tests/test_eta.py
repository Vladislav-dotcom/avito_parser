from services.eta_service import compute_progress_eta


def test_eta_normal_progress():
    # 1300 строк за 90 минут ≈ 14.4/мин, осталось 1500 → ~104 мин
    started = 1_000_000
    now = started + 90 * 60
    elapsed, rpm, eta = compute_progress_eta(
        processed_rows=1300,
        total_rows=2800,
        state="processing",
        started_at=started,
        created_at=started,
        now_ts=now,
    )
    assert elapsed == 90 * 60
    assert rpm is not None and 14.0 <= rpm <= 15.0
    assert eta is not None and 100 * 60 <= eta <= 110 * 60


def test_eta_after_resume_with_reset_started_at():
    # После деплоя started_at свежий, processed_rows большой — без фикса ETA ~секунды.
    created = 1_000_000
    now = created + 90 * 60
    resumed_started = now - 30
    elapsed, rpm, eta = compute_progress_eta(
        processed_rows=1330,
        total_rows=2808,
        state="processing",
        started_at=resumed_started,
        created_at=created,
        now_ts=now,
    )
    assert elapsed == 90 * 60
    assert rpm is not None and rpm < 30
    assert eta is not None and eta > 30 * 60


def test_eta_preserves_started_at_when_plausible():
    created = 1_000_000
    started = created + 60
    now = started + 30 * 60
    elapsed, rpm, eta = compute_progress_eta(
        processed_rows=400,
        total_rows=800,
        state="processing",
        started_at=started,
        created_at=created,
        now_ts=now,
    )
    assert elapsed == 30 * 60
    assert eta is not None and 25 * 60 <= eta <= 35 * 60
