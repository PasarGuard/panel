# Historical usage rollups

The scheduler compacts `node_user_usages` and `node_usages` once per hour. It
selects complete UTC days whose end is at least seven days old. For each day,
it replaces the ten-minute rows with one row per user and node (or one row per
node for node totals). Each day is committed in its own transaction. Up to 14
days from each table are processed per run, so a large existing backlog is
worked through gradually.

The daily row is dated at 00:00 UTC and marked `is_daily`. Its byte totals are
the exact sums of the replaced rows. A repeat run makes no change. If a late
historical row is added, the next run combines it with the existing daily row.

Historical charts have daily resolution after compaction. Hourly or minute
views place the full day's usage at 00:00 UTC; they cannot recover the original
within-day distribution. A range starting or ending partway through a UTC day
may therefore include or exclude that day's entire total. Use complete UTC
days for exact historical range totals.

Set `JOB_COMPACT_USAGE_INTERVAL` to change the schedule (default: 3600
seconds). After deployment, run database migrations before the scheduler
starts. The number of rows drops as the backlog is processed. Reclaiming disk
space may require normal database maintenance, depending on the engine.

## Synthetic SQLite measurements

The reproducible [benchmark](../scripts/benchmark_usage_rollups.py) uses 40
users, one node, seven recent days left untouched, and the usage tables and
indexes from the application schema. It checks that all user, uplink, and
downlink byte totals are identical before and after compaction. File size is
measured after `VACUUM` on both sides, so it represents reclaimed SQLite disk
space rather than immediate post-delete size.

| Older data | Sampling | Rows before → after | Row reduction | SQLite file before → after | File reduction |
| --- | --- | ---: | ---: | ---: | ---: |
| 14 days | Hourly | 20,664 → 7,462 | 63.9% | 3,985,408 → 1,679,360 bytes | 57.9% |
| 28 days | Hourly | 34,440 → 8,036 | 76.7% | 6,385,664 → 1,806,336 bytes | 71.7% |
| 14 days | Every 10 minutes | 123,984 → 41,902 | 66.2% | 22,601,728 → 7,958,528 bytes | 64.8% |

These are synthetic results, not a measured reduction on a production database.
The ratio depends on how much recent data remains, sampling frequency, database
engine, indexes, and other tables.

The idea for daily aggregation was inspired by [ErfJab's post](https://t.me/ErfJabs/3448).
