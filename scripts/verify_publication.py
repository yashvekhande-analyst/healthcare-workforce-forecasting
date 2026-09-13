"""Check frozen evidence and portable documentation without fetching or training."""
from pathlib import Path
import hashlib
import json
import math
import re
from urllib.parse import unquote, urlsplit

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def verify_bundle():
    entries = json.loads((ROOT / 'artifacts/bundle_checksums.json').read_text())['files']
    for entry in entries:
        path = ROOT / entry['path']
        assert path.is_file(), f'Missing bundle file: {entry["path"]}'
        assert path.stat().st_size == entry['bytes'], f'Changed file size: {path}'
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], f'Changed evidence: {path}'
    run = ROOT / 'artifacts/full'
    metadata = json.loads((run / 'models/metadata.json').read_text())
    assert hashlib.sha256((run / 'models/bundle.joblib').read_bytes()).hexdigest() == metadata['bundle_sha256']
    assert hashlib.sha256((run / 'features.parquet').read_bytes()).hexdigest() == metadata['feature_data_sha256']
    print(f'Bundle checksums: {len(entries)} files passed; model {metadata["version"]}')


def verify_metrics():
    run = ROOT / 'artifacts/full'
    forecasts = pd.read_parquet(run / 'test_forecasts.parquet')
    outcomes = pd.read_parquet(run / 'test_outcomes.parquet')
    assert 'actual' not in forecasts.columns
    assert not forecasts.duplicated(['model', 'facility', 'origin']).any()
    assert not outcomes.duplicated(['facility', 'origin']).any()
    connection = duckdb.connect()
    connection.register('forecasts', forecasts)
    connection.register('outcomes', outcomes)
    actual = connection.execute('''
        SELECT model, count(*) AS n,
               avg(abs(prediction-actual)) AS mae_hours,
               sum(abs(prediction-actual))/nullif(sum(abs(actual)), 0) AS wape,
               avg(prediction-actual) AS signed_error_hours,
               avg(CAST(actual BETWEEN lower AND upper AS DOUBLE)) AS coverage,
               avg(upper-lower) AS mean_width_hours
        FROM forecasts JOIN outcomes USING (facility, origin, target_end)
        WHERE actual IS NOT NULL GROUP BY model ORDER BY model
    ''').df().set_index('model')
    connection.close()
    expected = pd.read_csv(run / 'reports/test_metrics.csv').set_index('model')
    assert set(actual.index) == set(expected.index)
    for model, row in actual.iterrows():
        for metric, value in row.items():
            assert math.isclose(value, expected.loc[model, metric], rel_tol=1e-10, abs_tol=1e-10), (model, metric)
    metadata = json.loads((run / 'models/metadata.json').read_text())
    validation = pd.read_csv(run / 'reports/validation_metrics.csv')
    assert validation.sort_values('mae_hours').iloc[0]['model'] == metadata['selected_validation_candidate']
    selected = actual.loc[metadata['selected_model']]
    summary = json.loads((run / 'backtest_summary.json').read_text())
    assert selected['n'] == summary['evaluated_origins'] == 8660
    assert len(forecasts.loc[forecasts.model == metadata['selected_model']]) == summary['forecastable_origins']
    print(f'Independent SQL: all three models match; selected MAE {selected.mae_hours:.2f} h, '
          f'WAPE {selected.wape:.2%}, coverage {selected.coverage:.2%}')


def verify_links():
    count = 0
    # Explicit inline Markdown links/images used by this repository. Code blocks
    # are removed so examples and generated text are not interpreted as links.
    files = [ROOT / 'README.md', ROOT / 'VERIFICATION.md', ROOT / 'DATA_NOTICE.md']
    files += sorted((ROOT / 'docs').glob('*.md'))
    files += sorted((ROOT / 'artifacts/full/reports').glob('*.md'))
    for path in files:
        content = re.sub(r'```.*?```', '', path.read_text(encoding='utf-8'), flags=re.S)
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', content):
            target = target.strip().split(' "', 1)[0].strip('<>')
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            resolved = (path.parent / unquote(url.path)).resolve()
            assert resolved.is_relative_to(ROOT), f'Nonportable link in {path}: {target}'
            assert resolved.exists(), f'Broken link in {path}: {target}'
            count += 1
    print(f'Relative document links and images: {count} passed')


if __name__ == '__main__':
    verify_bundle()
    verify_metrics()
    verify_links()
