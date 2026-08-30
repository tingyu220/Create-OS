from creative_os.domains.reader_engagement_migration import ReaderEngagementMigration


def test_migration_never_infers_paid_or_abandoned_from_legacy_text(tmp_path):
    report = ReaderEngagementMigration.inspect(tmp_path)
    assert report.requires_human_plan is True
    assert report.materialized_transitions == ()
