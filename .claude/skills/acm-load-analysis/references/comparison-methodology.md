# Comparison Methodology

How to compare two acm-deploy-load or acm-telco-core-load test results.

## Phase Matching

When comparing two results, match data sources correctly:

| Result A | Result B | Compare |
|---|---|---|
| Has phase dirs | Has phase dirs | **Both**: phase-by-phase AND full-test (see below) |
| Has phase dirs | No phase dirs | Full-test analysis dirs only |
| No phase dirs | Has phase dirs | Full-test analysis dirs only |
| No phase dirs | No phase dirs | Full-test analysis dirs only |

The full-test Prometheus analysis directory prefix depends on which orchestration
script produced the result: `deploy-pa-*` for acm-deploy-load
(`interval-ztp-install-all.sh`) or `acm-telco-load-hub-*` for acm-telco-core-load
(`acm-telco-core-load.sh`).

**When both results have phase directories, the report MUST include both:**

1. **Phase-by-phase comparison** — a separate section per matching phase (idle↔idle,
   deployment↔deployment, soak↔soak). Each phase section includes per-node resources,
   cluster-level resources, ODF/component data (when present in that phase), and etcd.
   Phases reveal workload-specific differences (idle overhead, deployment peaks,
   sustained soak behavior) that full-test aggregates obscure.

2. **Full-test overview** — using the `deploy-pa-*` or `acm-telco-load-hub-*`
   directories. This provides the aggregate view and includes data typically only
   available at full-test scope (disk I/O, full component breakdown).

Never produce only a full-test comparison when phase data exists in both results.

For telco-core-load batch phases (`phase2-batch-{N}`), match by batch index.

## Delta Calculation

For each metric, compute:
- **Absolute delta**: Result B value - Result A value
- **Percentage delta**: ((Result B - Result A) / Result A) * 100

Present both in the comparison table. Use Result A as the baseline (denominator).

When Result A is zero, the percentage delta is undefined — show "N/A" or "—"
in the percentage column and report the absolute delta only.

## Significance Thresholds

| Delta Range | Classification | Presentation |
|---|---|---|
| < 5% | Within run-to-run variance | Note but do not emphasize |
| 5% - 10% | Minor difference | Report normally |
| 10% - 25% | Notable difference | Highlight in findings |
| > 25% | Significant difference | Call out explicitly in key findings |

These thresholds apply to resource metrics (CPU, memory, network, disk). For
timing metrics, apply a stricter standard:
- < 5%: run-to-run variance
- 5% - 15%: minor
- > 15%: notable

## Comparison Report Structure

1. **Test Environment Summary** — side-by-side metadata from both report.txt files
   (versions, cluster count, method, success rates). Flag any differences in test
   setup that could affect comparability.

2. **Timing Comparison** — deploy-time milestones, workload stats (ICI, CGU, CI)
   with p50, p95, p99, max and deltas.

3. **Hub Cluster Resource Comparison** — cluster-level tables first (the headline),
   then per-node tables as drill-down detail. Columns:
   Metric | Result A | Result B | Delta | Delta %

4. **Component Comparison** — CPU P95 and Memory Max for each component with deltas.
   Only include components present in both results. List components unique to one
   result separately (e.g., ODF components in an ODF-vs-No-ODF comparison).

5. **etcd Comparison** — DB size, latencies, leader elections.

6. **Storage Comparison** — PVC usage, Ceph (if applicable).

7. **Key Differences** — bullet-point summary of the most significant findings,
   ordered by magnitude of impact.

## Causation Rule

**Report observations, not theories.** State what differs and by how much.
Do not assert why two values differ unless the test design explicitly isolates
that variable.

Acceptable: "ODF run used 16 GiB more cluster memory (Max) than the No-ODF run."

Not acceptable: "ODF caused 16 GiB additional memory consumption due to Ceph
caching behavior."

When a variable is explicitly isolated by test design (e.g., the only difference
between two runs is ODF vs No-ODF), it is acceptable to attribute the delta to
that variable, but phrase it as an observation: "The 16 GiB memory delta
corresponds to the ODF overhead, as ODF was the only configuration difference."

## Handling Asymmetric Components

When one result has components the other does not (e.g., ODF in one, LSO in the
other), report the unique component's resource footprint separately rather than
as a comparison row with zero on one side. Present it as additive cost:

"ODF resource footprint (not present in Result A):"
| Metric | Value |
|---|---|
| CPU P95 | 0.39 cores |
| Memory Max | 8.78 GiB |

## Multiple-Phase Comparison

When comparing phase-by-phase, produce a separate comparison section per phase
with full per-node, cluster-level, etcd, and component/ODF tables for each.

The Key Differences section at the end MUST include:
1. **A cross-phase trends table** showing how the key deltas (memory, CPU,
   network) change across phases — this is the most valuable part of a
   phase-by-phase comparison as it reveals growth patterns and workload-specific
   overhead (e.g., ODF memory growing from idle to soak, network peaks during
   deployment that subside in soak).
2. **Key findings that reference phase-specific behavior** — e.g., "overhead is
   X at idle but Y during deployment" rather than a single full-test number.
