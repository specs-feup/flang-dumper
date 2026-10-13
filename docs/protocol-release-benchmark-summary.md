# Optimized protocol benchmark results

Run completed on 2026-10-13 against Flang dumper HEAD 6e51165a2544eacdc159d4dbc541692f11b1a3f0 and Metafor HEAD 7b98368b9f15ff8f9215b1ad3605e05b06ea0184. Both plugin artifacts used the same CMake Release build tree, Clang 21.1.8, -O3 -DNDEBUG, and the Flang 22.1.2 SDK. Full commands, compiler flags, library identities, plugin hashes, and retained object hashes are in [protocol-release-build-provenance.json](protocol-release-build-provenance.json).

## Native producer results

One warmup and five measured repeats per workload. Values are JSON / protobuf. Raw bytes and gzip bytes measure producer stdout. Wall time is the benchmark harness parent-observed duration around GNU time. RSS is GNU time %M in KiB.

| Workload | Raw bytes | gzip bytes | Wall seconds | Peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| hello | 12,935 / 10,093 | 2,883 / 3,707 | 0.0296 / 0.0295 | 85,996 / 86,960 |
| polybench 3mm | 230,986 / 140,538 | 24,031 / 23,019 | 0.0376 / 0.0391 | 89,968 / 89,880 |
| synthetic 512 | 994,786 / 609,643 | 79,043 / 65,682 | 0.0445 / 0.0510 | 88,044 / 90,908 |

The native report parity preflight covered 53 Metafor sources: 52 matched; one JSON baseline failed because this target does not enable REAL(KIND=16); there were zero protobuf failures and zero graph mismatches. The dedicated JSON and protobuf fixture checks both matched all four frozen native graphs. The six protocol test programs passed.

## Metafor end-to-end results

The Java benchmark used one warmup and five fresh JVM samples per mode and workload. All three workloads produced identical generated Fortran for JSON and protobuf.

| Workload | End-to-end median ms | Protobuf vs JSON | Java process VmHWM KiB | Java command GNU time wait-rusage KiB | Flang child GNU time wait-rusage KiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| hello | 119.309 / 114.833 | -3.75% | 105,924 / 108,968 | 106,800 / 109,680 | 86,148 / 87,276 |
| polybench 3mm | 142.545 / 154.989 | +8.73% | 128,504 / 137,192 | 128,752 / 137,480 | 90,024 / 90,440 |
| synthetic 512 | 186.218 / 229.611 | +23.30% | 209,004 / 219,356 | 209,280 / 220,804 | 88,208 / 91,052 |

The Java process VmHWM is its own high-water RSS after JVM startup, warmup, and the measured sample. GNU time wait-rusage is a separate wait3/wait4 measurement and can include the largest waited child. These figures overlap and must not be added. The Flang child wait-rusage is recorded separately as well.

## Reading the result

The protobuf producer emitted smaller raw streams for all three workloads. Its native wall-time median was nearly equal on hello, about 4% slower on 3mm, and about 14% slower on the synthetic workload. In the Java pipeline, protobuf was 3.75% faster on hello, 8.73% slower on 3mm, and 23.30% slower on the synthetic workload.

Compared with the earlier O0 report, the measured end-to-end penalty narrowed from 18.38% to 8.73% on 3mm and from 54.10% to 23.30% on the synthetic workload. The earlier report used the same Flang binary, Java harness hashes, fixture hashes, and classpath hash, but it did not record the producer source commit or compile flags. Treat this as indicative, not a controlled same-source O0-versus-O3 comparison.

perf is installed, but the host rejects performance events (perf_event_paranoid=4, perf stat reports no supported events). No hot-path profile was available, so no producer optimization was inferred or applied. This run does not justify changing the default parser selection. The result covers these workloads, binaries, and host only.

Reports: [native producer JSON](protocol-release-benchmark-report.json); Metafor end-to-end JSON is at FortranParser/docs/native-end-to-end-release-benchmark-report.json in the Metafor worktree.
