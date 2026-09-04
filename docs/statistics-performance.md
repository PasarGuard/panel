# Statistics page performance

The Statistics page combines live system data with several historical charts.
On large installations, historical queries must be kept separate from the
short polling loop used for live resource data.

## Query-load safeguards

- The subscription-client chart defaults to one month. All-time data remains
  available as an explicit selection.
- Live CPU, memory, and disk data refresh every two seconds, while aggregate
  user counts refresh every 30 seconds.
- The owner-wide subscription chart reads `user_subscription_updates` directly;
  it joins `users` only when an admin scope is requested.
- Subscription pie totals are derived from the period aggregation, reducing the
  endpoint from two history queries to one without changing the response.
- Unscoped online-user history counts read `node_user_usages` directly. Status
  metrics and admin-scoped requests still join the tables required for their
  filters.
- `user_subscription_updates.created_at` has its own index for owner-wide time
  range queries. The existing `(user_id, created_at)` index remains useful for
  per-user and admin-scoped access paths.

Creating the new index must scan the existing subscription-update table. On a
large MySQL installation, apply the migration during a maintenance window and
monitor the database until the DDL completes; the exact locking behavior depends
on the MySQL/MariaDB version and table configuration.

## Expected structural improvement

| Work on page load | Before | After |
| --- | ---: | ---: |
| Subscription history aggregation queries | 2 | 1 |
| Owner-wide subscription joins to `users` | 1 per query | 0 |
| Unscoped online-count joins to `users` | 1 per query | 0 |
| Aggregate user-stat polling interval | 2 seconds | 30 seconds |
| Default subscription-history range | Since 2000 | 1 month |

Actual latency depends on the database size and engine. For production
verification, capture `EXPLAIN ANALYZE` for the two historical endpoints and
compare rows examined, temporary-table use, and execution time before and after
the migration. The application test suite verifies response equivalence, the
single-query subscription path, join selection, and migration integrity.

## Directional benchmark

An in-memory SQLite benchmark with 400,000 rows in each history table was run
seven times after one warm-up; the table below shows median wall-clock time.
It exercises the before/after SQL shapes and is not a production MySQL latency
guarantee.

| Query shape | Before | After | Change |
| --- | ---: | ---: | ---: |
| Unscoped online count | 406.16 ms | 325.05 ms | -20.0% |
| Subscription chart | 896.68 ms | 502.13 ms | -44.0% |

The first comparison removes the `users` join. The second replaces separate
total and period aggregations with the single period aggregation used to build
both response sections.
