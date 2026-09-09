# bcast-netcheck

Fast, repeatable, read-only Linux network diagnostics for broadcast engineers.
Version 0.1 combines structured evidence with a cautious diagnosis: what answered,
what failed, whether redundancy is degraded, and where to investigate next.
It does not change routes, trigger failover, restart services, or modify equipment.

Use it from an engineering laptop, a Linux host at a studio or transmitter site,
or a troubleshooting VM with access to the equipment. A single run gathers
connectivity evidence for an IP address, hostname, entire station, or one device.
It then presents a diagnosis and suggested next steps in the terminal, with
optional Markdown reports and JSON for automation.

Typical uses include checking an STL encoder before investigating the application,
comparing primary and backup gateway reachability, watching an intermittent device,
and attaching a repeatable network diagnostic to a maintenance ticket.

The current version is **0.1.0**. It measures network reachability and selected
services; it does not inspect audio/video payloads, measure streaming bitrate,
or verify that a broadcast is on air.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Basic use](#basic-use)
- [Command reference](#command-reference)
- [YAML configuration](#yaml-configuration)
- [Checks and interpretation](#checks-and-interpretation)
- [Diagnosis and exit codes](#diagnosis-and-exit-codes)
- [Watch mode](#watch-mode)
- [Reports and JSON](#reports-and-json)
- [Practical examples](#practical-examples)
- [Troubleshooting](#troubleshooting)
- [Security and limitations](#security-and-limitations)
- [How it works](#how-it-works)
- [Development](#development)
- [Roadmap and license](#roadmap-and-license)

## Installation

### Requirements

- Python **3.11 or newer**.
- Linux for the complete set of diagnostics.
- Network access from the machine running the tool to the targets being checked.
- Linux utilities: `ping`, `ip`, and either `traceroute` or `tracepath`.

Python dependencies are installed automatically: Typer for the CLI, Rich for
terminal output, PyYAML for configuration, dnspython for DNS, and PySNMP for SNMP.
No separate SNMP command-line client or vendor MIB package is required.

### Install from source

From a downloaded or cloned copy of this repository, open a terminal in the
`bcast-netcheck` directory. Source installation is the documented installation
method; these instructions do not assume a published PyPI package.

On Debian/Ubuntu, install Python tooling and the diagnostic utilities:

```bash
sudo apt-get update
sudo apt-get install python3 python3-venv python3-pip iputils-ping iproute2 traceroute iputils-tracepath
python3 --version
```

Confirm that the Python version is at least 3.11. If your distribution's `python3`
is older, install a supported interpreter and use it to create the environment.
Then install the project:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
bcast-netcheck --help
```

Activate the environment again in each new terminal, or invoke the executable
as `.venv/bin/bcast-netcheck`. The Python package installation does not require
`sudo`.

If you already use `pipx`, you can instead install the CLI in its own managed
environment from the repository directory:

```bash
pipx install .
bcast-netcheck --help
```

After updating the source, repeat `python -m pip install .` in the virtual
environment. To remove that installation, run `python -m pip uninstall
bcast-netcheck`; for pipx, use `pipx uninstall bcast-netcheck`.

### Platform behavior

Normal diagnostics do not require root. Linux must permit unprivileged ping
(for example, the distribution's configured ping socket or `ping` capability).
Missing utilities and unsupported operating systems produce `SKIP`. Permission
problems produce `ERROR`; other checks continue. Python TCP/DNS/NTP/SNMP checks
can operate on other platforms, but full diagnostics target Linux.

## Quick start

First, run a local check without configuring a station:

```bash
bcast-netcheck 127.0.0.1
```

This checks your own machine. Optional TCP ports may be closed, and Linux-only
checks will be skipped on other operating systems. A local result does not test
the path to your broadcast equipment.

For a station, copy the included example to the default configuration location:

```bash
cp examples/sites.yaml sites.yaml
```

Edit `sites.yaml` to replace the fictional addresses with your real endpoints.
Remove devices and DNS/NTP services you do not want to check, and set required
TCP ports to match the services you actually expect. Then run:

```bash
bcast-netcheck WXYZ --config sites.yaml
bcast-netcheck WXYZ encoder --config sites.yaml --verbose
```

For a smaller starting point, this is a complete configuration for one device:

```yaml
sites:
  WXYZ:
    description: 'Transmitter site'
    devices:
      encoder:
        host: 192.0.2.20 # Replace with your encoder's address.
        required: true
        ports:
          - port: 443
            name: 'Encoder HTTPS'
            required: true
```

The terminal displays check results, an overall diagnosis, and recommendations.
Use `--verbose` to see the measurements behind the result, or `--report` to save
a Markdown copy.

## Basic use

```bash
bcast-netcheck 127.0.0.1
bcast-netcheck 192.0.2.25
bcast-netcheck encoder.example
bcast-netcheck WXYZ --config examples/sites.yaml
bcast-netcheck WXYZ encoder --config examples/sites.yaml
bcast-netcheck WXYZ --ping-count 10 --timeout 5 --concurrency 20
bcast-netcheck WXYZ --verbose
bcast-netcheck WXYZ --debug
```

All station names, providers, and configuration addresses in this repository are
fictional. `192.0.2.0/24`, `198.51.100.0/24`, and `203.0.113.0/24` are documentation
networks. `example` hostnames are fictional. The sample sites normally **will not
respond**; nonzero diagnostic exit codes are expected. Loopback is used only for
local acceptance checks. IPv6 parser fixtures use `2001:db8::/32`.

Direct mode checks ICMP, loss, latency, jitter, TCP ports 22/80/443 marked optional,
routing, traceroute, and IPv4 path MTU. DNS resolves hostnames; numeric targets
skip DNS unless a resolver test is configured in a site. NTP and SNMP need site
configuration. Direct mode does not guess an NTP server or an SNMP community.

Site mode checks the router, devices, gateways, and configured DNS/NTP services.
The optional second argument selects only that device; site-wide services and
other devices are omitted. Site lookup is case insensitive; device names are
case sensitive. Unconfigured station-like names beginning with W or K are errors;
use a fully qualified hostname to disambiguate a direct target.

`--verbose` shows structured evidence, including observed path hops. `--debug`
adds check kinds, durations, and required flags. Neither mode dumps configuration,
environment variables, authentication data, or arbitrary Python exception strings.

## Command reference

```text
bcast-netcheck [OPTIONS] TARGET [DEVICE]
```

There are no subcommands. `TARGET` is an IP address, hostname, or configured site
name. `DEVICE` is an optional key under that site's `devices` mapping.

| Option                  | Default           | Purpose                                                     |
| ----------------------- | ----------------- | ----------------------------------------------------------- |
| `--config PATH`         | Auto-discover     | Read a specific YAML configuration.                         |
| `--ping-count INTEGER`  | `5`               | Probes per endpoint, from 1–100; watch always uses one.     |
| `--timeout FLOAT`       | `3`               | Deadline per check in seconds, from 0.1–120.                |
| `--concurrency INTEGER` | `20`              | Maximum simultaneous checks, from 1–100.                    |
| `--watch`               | Off               | Continuously sample endpoint reachability.                  |
| `--interval FLOAT`      | `5`               | Requested watch interval in seconds, from 0.1–3600.         |
| `--report`              | Off               | Write a timestamped Markdown report.                        |
| `--report-dir PATH`     | Current directory | Existing directory for the Markdown report.                 |
| `--json`                | Off               | Print a JSON document instead of the terminal presentation. |
| `--verbose`             | Off               | Include structured evidence and path hops.                  |
| `--debug`               | Off               | Include evidence plus check timing and execution metadata.  |
| `--help`                | —                 | Show command usage and options.                             |

`--timeout` is not a deadline for the entire command. Checks waiting for a
concurrency slot begin their deadline when they start, so a large site can take
multiple batches to complete. `--verbose` and `--debug` affect terminal rendering;
JSON and Markdown already include structured evidence.

## YAML configuration

The **first existing file** wins; files are never merged:

1. `--config FILE`, when supplied (a missing explicit file is an error)
2. `./sites.yaml`
3. `~/.config/bcast-netcheck/sites.yaml`
4. `/etc/bcast-netcheck/sites.yaml`

Direct mode works without a configuration file. An existing malformed configuration
is an error even for direct mode. A configured site can contain any useful subset
of endpoints/services, but cannot be empty. See [examples/sites.yaml](examples/sites.yaml)
for two fictional stations.

```yaml
sites:
  WXYZ:
    description: 'WXYZ Transmitter Site'
    router:
      host: 192.0.2.1
    devices:
      encoder:
        host: 192.0.2.20
        description: 'STL Encoder'
        required: true
        expected_mtu: 1500
        ports:
          - 22
          - port: 443
            name: 'Encoder HTTPS'
            required: true
      mod_monitor:
        host: 192.0.2.30
        snmp:
          enabled: true
          version: '2c'
          community_env: 'BCAST_SNMP_COMMUNITY'
          port: 161
    gateways:
      primary:
        host: 192.0.2.1
        provider: 'Primary Carrier'
      backup:
        host: 198.51.100.1
        provider: 'Backup Carrier'
    dns:
      server: 192.0.2.53
      test_name: encoder.example
    ntp:
      server: 192.0.2.123
```

### Configuration fields

Each site is a mapping under the top-level `sites` key. Site names begin with a
letter and may contain letters, digits, underscores, and hyphens (up to 64
characters). Names must be unique without regard to case.

| Site field         | Meaning                                                          |
| ------------------ | ---------------------------------------------------------------- |
| `description`      | Human-readable site description.                                 |
| `router`           | One endpoint; its ICMP check defaults to required.               |
| `devices`          | Mapping of device names to endpoints.                            |
| `gateways.primary` | Primary gateway endpoint; `provider` supplies its display label. |
| `gateways.backup`  | Backup gateway endpoint; `provider` supplies its display label.  |
| `dns.server`       | DNS server address or hostname for the site DNS test.            |
| `dns.test_name`    | Optional name to resolve; omission tests a root NS query.        |
| `ntp.server`       | NTP server address or hostname, queried on UDP port 123.         |

| Endpoint field | Default                              | Meaning                                                                             |
| -------------- | ------------------------------------ | ----------------------------------------------------------------------------------- |
| `host`         | Required                             | IP address or hostname, without a URL scheme or port suffix.                        |
| `description`  | Empty                                | Display label for the endpoint.                                                     |
| `required`     | `true` for router; otherwise `false` | Whether ICMP failure counts as a required failure.                                  |
| `ports`        | `[]`                                 | TCP ports to test; integer entries or mappings with `port`, `name`, and `required`. |
| `expected_mtu` | `1500`                               | IPv4 MTU probe ceiling, an integer from 576–9000 bytes.                             |
| `snmp`         | Disabled                             | Boolean or SNMP settings mapping.                                                   |

TCP and SNMP port values must be integers from 1–65535. Device names begin with a
letter and may contain letters, digits, underscores, and hyphens. Only `primary`
and `backup` are accepted as gateway keys. Addresses shared by multiple endpoint
entries are checked separately.

Site endpoints have **no default TCP ports**. The automatic 22/80/443 checks apply
only to direct IP/hostname mode. There is no CLI option to specify TCP ports;
configure a site endpoint to choose them.

### Required checks and SNMP

Endpoint `required` governs ICMP severity. The router defaults to required;
devices and gateways default to optional. Required TCP services are explicit:
bare port numbers are optional. A refused optional port remains `FAIL` in the
check evidence but does not make the target unhealthy on its own. Enabled SNMP
and configured DNS/NTP services are expected checks. `snmp: true` without an
environment reference produces an informative `SKIP`, never an assumed community.

For a fictional lab community:

```bash
export BCAST_SNMP_COMMUNITY="example"
bcast-netcheck WXYZ --config examples/sites.yaml
```

The SNMP mapping accepts only `enabled`, `version`, `community_env`, and `port`.
The defaults are version `"2c"` and port `161`. A nonempty mapping enables SNMP
unless `enabled: false` is set. `community_env` names an environment variable;
it is not the community value itself.

Only SNMP v2c is implemented. The community is loaded from the named environment
variable and never placed in diagnostic data. Plaintext community fields are
rejected. Missing secrets skip the query. Responses query standard `sysName`,
`sysDescr`, and `sysUpTime`; no vendor MIB download is needed.

## Checks and interpretation

| Check      | Evidence and limits                                                                                                                                                |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| ICMP       | Replies, min/average/max RTT, loss from sent/received counters; ICMP filtering can resemble an outage.                                                             |
| Jitter     | Mean absolute difference between consecutive observed RTT samples, not RTP jitter. Fewer than two replies means unavailable.                                       |
| TCP        | Connection attempt only; an open port does not prove application health.                                                                                           |
| DNS        | A/AAAA resolution for hostnames; a configured resolver without a test name receives a root NS query. Negative answers differ from no response.                     |
| NTP        | One UDP/123 exchange, estimated server-minus-local offset and round-trip delay. Validates origin, mode, stratum, timestamps, and synchronization. Never sets time. |
| SNMP       | One bounded v2c GET for three standard system OIDs.                                                                                                                |
| Route      | `ip -j route get`, reporting destination, gateway, interface, and source.                                                                                          |
| Traceroute | Numeric UDP traceroute, or tracepath if unavailable; up to 12 hops. Partial paths remain inconclusive.                                                             |
| Path MTU   | Up to 15 IPv4 DF probes, bounded by the check deadline. Binary searches only on explicit fragmentation evidence. Silence is inconclusive.                          |

MTU probing searches up to the endpoint's `expected_mtu` (default 1500). A success
at that size proves **at least** that MTU, not the absolute maximum. A confirmed
smaller result warns about possible encapsulation; it does not assert a broken
path. IPv6 MTU discovery is explicitly skipped in 0.1.

Central defaults live in `bcast_netcheck/config.py`: 5 pings, 3 seconds per check,
20 concurrent checks, 5-second watch interval; warning thresholds are 100 ms
average latency, 10 ms jitter, 1% loss, and 100 ms absolute NTP offset. Endpoint
MTU expectations are configurable in YAML. Other threshold overrides are a
future configuration extension. `--timeout`, `--ping-count`, `--concurrency`, and
`--interval` override operational defaults. The deadline takes precedence over
ping count; `requested_count`, actual counters, and `deadline_limited` record this.

Checks run concurrently with a global bound. They never invoke a shell.
Subprocesses are interrupted on deadline and killed/reaped if needed, preserving
ping summaries and partial traceroute evidence when available.

## Diagnosis and exit codes

Individual checks use `PASS`, `WARN`, `FAIL`, `SKIP`, or `ERROR`:

- `PASS`: expected behavior observed.
- `WARN`: degraded behavior or inconclusive evidence.
- `FAIL`: expected response unavailable or invalid.
- `SKIP`: unsupported, unavailable utility, or intentionally unconfigured.
- `ERROR`: the check itself could not execute.

Backup-only failure produces a warning about degraded redundancy. Both gateways
failing ICMP can justify a `critical` overall diagnosis, with an explicit caveat
about filtering. An optional device failure never produces `critical`. A healthy
router with one failing optional device suggests a local device/network problem.
Gateway replies do not prove circuit health, end-to-end service, or successful
failover. The displayed route is local routing evidence, not proof of remote forwarding.

| Exit | Meaning                                                            |
| ---- | ------------------------------------------------------------------ |
| 0    | Healthy among completed checks                                     |
| 1    | Warning, degraded redundancy, or incomplete checks                 |
| 2    | Required service failure or critical transport evidence            |
| 3    | Configuration/execution error or no successful diagnostic evidence |
| 130  | Interrupted with Ctrl+C                                            |

A failed required service takes precedence over unrelated execution errors.
Typer command syntax errors (for example an unknown option) use its standard
exit code 2 and help text on stderr. Use the structured status to distinguish
syntax errors from diagnostic results when scripting.

## Watch mode

```bash
bcast-netcheck WXYZ --config examples/sites.yaml --watch
bcast-netcheck WXYZ --config examples/sites.yaml --watch --interval 1
```

Watch samples one ICMP probe per endpoint plus one route lookup each round. It
shows rolling loss and RTT variation over the last 60 samples, and the last 20
reachability events. Full TCP/DNS/NTP/SNMP/MTU/traceroute checks are intentionally
run in normal diagnostic mode. Watch status therefore covers reachability only.

The interval is a requested start-to-start cadence; rounds never overlap. Each
watch probe deadline is capped at 80% of the interval. Large sites or low
concurrency can lengthen actual sampling gaps, which are displayed. Event times
are round completion times. Interruption duration is an estimate between the first
failed sample and restoration; outages between samples can be missed. Execution
gaps invalidate an interruption estimate. No sub-second accuracy is claimed
without corresponding observed sampling intervals. Ctrl+C stops cleanly.

## Reports and JSON

```bash
bcast-netcheck WXYZ --config examples/sites.yaml --report
bcast-netcheck WXYZ --config examples/sites.yaml --report --report-dir /tmp
bcast-netcheck WXYZ --config examples/sites.yaml --json
bcast-netcheck WXYZ --config examples/sites.yaml --json --report
```

Reports use `wxyz-netcheck-YYYY-MM-DD-HHMMSS-microseconds.md` to avoid collisions.
They contain timestamp, version, site, target addresses, check results and
structured evidence, diagnosis, and recommendations. The output directory must
already exist. Files are created exclusively with mode 0600. Report paths go to
stderr, preserving JSON-only stdout when both options are used.

JSON schema version 1 includes `site`, `target`, `timestamp`, `version`, `status`,
`summary`, `diagnosis`, and a `checks` list. Each check includes status, endpoint,
label, target, value, unit, message, details, duration, kind, and required flag.
Check statuses are uppercase; aggregate statuses are lowercase. Configuration
errors with `--json` produce a small JSON error document. CLI parser errors go
to stderr. `--watch` cannot be combined with `--json` or `--report`.

## Practical examples

The station examples below assume you have replaced the documentation addresses
in `sites.yaml` with your own equipment addresses.

### Investigate one encoder

```bash
bcast-netcheck WXYZ encoder --config sites.yaml --verbose
```

Compare ICMP with the required TCP service. An ICMP failure with a working TCP
connection can indicate filtering; a reachable host with a refused required port
suggests investigating the service. A successful TCP connection only establishes
that something accepted the connection, not that the encoder is functioning.

### Allow more time for a slow path

```bash
bcast-netcheck WXYZ --config sites.yaml --ping-count 10 --timeout 10 --concurrency 10
```

This requests ten ICMP probes per endpoint and allows each check up to ten
seconds. Reducing concurrency limits simultaneous check operations, although each
operation may send multiple packets.

### Watch an intermittent device

```bash
bcast-netcheck WXYZ encoder --config sites.yaml --watch --interval 1
```

Watch the rolling loss, RTT variation, and reachability events. Stop with Ctrl+C,
then run a normal diagnostic with `--report` if you need a saved record of the
full checks. Watch history is kept in memory and is not exported as a report.

### Save a maintenance report

```bash
mkdir -p reports
bcast-netcheck WXYZ --config sites.yaml --report --report-dir reports
```

The command prints the generated report path to stderr and the diagnostic result
to the terminal. For example, a filename could be
`wxyz-netcheck-2026-09-09-143000-123456.md`. The filename uses local time; the
report's diagnostic timestamp is UTC.

### Capture JSON and the diagnostic exit code

```bash
if bcast-netcheck WXYZ --config sites.yaml --json > netcheck.json; then
  result_code=0
else
  result_code=$?
fi
printf 'Diagnostic exit code: %s\n' "$result_code"
python -m json.tool netcheck.json
```

The conditional preserves nonzero diagnostic results even in scripts that use
`set -e`. To create both JSON and Markdown in one run:

```bash
mkdir -p reports
bcast-netcheck WXYZ --config sites.yaml --json --report --report-dir reports > netcheck.json
```

A normal JSON document includes `schema_version`, `target`, `site`, `description`,
`timestamp`, `version`, `checks`, `diagnosis`, `status`, and `summary`. The diagnosis
contains `status`, `summary`, and `recommendations`. For example, this Python
snippet prints the aggregate status and each unsuccessful check:

```python
import json
from pathlib import Path

result = json.loads(Path("netcheck.json").read_text())
if "error" in result:
    print("Diagnostic error:", result["error"])
else:
    print(result["status"], "—", result["summary"])
    for check in result["checks"]:
        if check["status"] in {"WARN", "FAIL", "ERROR"}:
            print(check["endpoint"], check["name"], check["status"], check["message"])
```

Treat `schema_version` as the format discriminator in integrations. Configuration
and local execution errors return smaller error documents; CLI syntax errors may
leave stdout empty. JSON files created with shell redirection use your shell's
permissions rather than the Markdown writer's mode 0600. Review reports and JSON
before sharing them or adding them to a repository; `netcheck.json` is not covered
by the project's report-file ignore pattern.

## Troubleshooting

| Symptom                                              | What to check                                                                                                                                |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `bcast-netcheck: command not found`                  | Activate the environment used for installation, try `.venv/bin/bcast-netcheck`, or check your pipx executable directory is on `PATH`.        |
| `This check requires Linux`                          | Run on Linux for ping, route, traceroute, and MTU diagnostics. Installing similarly named macOS utilities does not enable those checks.      |
| `Missing utility: ...`                               | Install the corresponding system package and ensure its executable is on `PATH`.                                                             |
| ICMP execution or permission error                   | Confirm that `ping` works as the same user and that the system permits unprivileged ping.                                                    |
| `Unknown station`                                    | Check the site name and configuration path. Use a fully qualified hostname if the target was intended to be a hostname.                      |
| `Unknown configured device`                          | Use the exact, case-sensitive key from `devices`, after the configured site name.                                                            |
| Configuration error before a direct IP check         | An auto-discovered YAML file is still loaded. Fix it or provide a valid file explicitly with `--config`.                                     |
| Sample stations fail                                 | The bundled IP addresses and hostnames are fictional; replace them before testing real equipment.                                            |
| SNMP is skipped                                      | Enable SNMP and set the environment variable named by `community_env` in the process's environment.                                          |
| SNMP fails with credentials present                  | Check v2c support, the community, the configured UDP port, and the device's source-address access rules.                                     |
| Optional TCP port says `FAIL`, but status is healthy | Optional TCP failures are retained as evidence without making the overall result fail on their own. Mark expected services `required: true`. |
| Fewer pings than requested                           | The deadline takes precedence over probe count. Increase `--timeout` and inspect `deadline_limited` and the actual counters.                 |
| Traceroute or MTU is inconclusive                    | Filtering or timeouts can prevent a conclusion. Inspect verbose evidence and compare it with ICMP/TCP results.                               |
| Report file operation failed                         | Create the output directory first and check write permissions and available storage.                                                         |
| Watch updates take longer than `--interval`          | Rounds do not overlap. Site size, deadlines, and concurrency can make the actual sampling gap longer.                                        |

Use `--debug` for check kinds, duration, required flags, and structured evidence.
It does not expose arbitrary exception text or credentials. A `healthy` result
means no required failures were found among the completed checks; review skipped
checks before treating it as comprehensive evidence.

## Security and limitations

Treat configurations and reports as sensitive. Reports contain operational
addresses and device metadata even though authentication data is excluded.
Keep real configuration files out of source control (`sites.yaml` is ignored).
YAML uses safe loading, hosts and ports are validated, and no configured value
can become a shell command. Configured SNMP secrets are redacted even if a remote
endpoint reflects them. Subprocess environments contain only PATH and locale.
SNMP v2c and the basic NTP exchange are unauthenticated protocols; use them only
on networks where that is appropriate. No SNMPv3 or authenticated NTP in 0.1.

DNS uses asynchronous DNS resolution and `/etc/hosts` for endpoint address lookup;
it does not reproduce all libc NSS integrations such as mDNS or LDAP. Queries
may contact the machine's configured resolvers. A DNS test against a numeric IP
is not a reverse-DNS requirement. Traceroute can be filtered independently of
actual application traffic. MTU is not measured above its configured ceiling.

The automated suite uses mocks and documentation-address fixtures; it does not
need broadcast infrastructure. Development verification on macOS exercises real
localhost TCP and CLI/report flows, while Linux commands use parser/process mocks.
The included Linux CI job additionally checks local ping and route behavior.

## How it works

`checks/` contains independent async checks returning `CheckResult`; `runner.py`
bounds concurrency, `diagnosis.py` correlates evidence, and `reports/` adapts the
same run into terminal, Markdown, and JSON. `watch.py` owns reachability history.
`devices/generic.py` defines an extension protocol; no vendor integrations are
loaded or required.

A normal run follows this sequence:

1. The CLI validates options, finds the configuration, and resolves the target to
   either a configured site, a selected device, or a direct endpoint.
2. The runner schedules ICMP, configured TCP ports, route, traceroute, MTU, SNMP,
   and DNS checks for each endpoint. A full site run also adds configured DNS and
   NTP service tests. Unconfigured checks can return `SKIP`.
3. An asyncio semaphore limits concurrent checks. Each operation has a deadline;
   failures are converted to structured results so unrelated checks can finish.
4. The diagnosis layer correlates required services, router/device reachability,
   and primary/backup gateway evidence. It assigns an aggregate status and next
   steps without claiming to have observed failover or a definitive root cause.
5. Configured secrets are redacted, and the same result model feeds terminal,
   Markdown, and JSON output. The diagnosis determines the process exit code.

Endpoint DNS checks can use the configured site resolver during a full site run.
Other checks resolve their own target addresses through their respective lookup
paths; configuring `dns.server` does not globally redirect every lookup. Selecting
one device omits the site's DNS/NTP service tests and the site resolver override.

```text
bcast_netcheck/
  cli.py              Argument handling and output selection
  config.py           YAML loading, validation, target selection, defaults
  runner.py           Concurrent check scheduling and deadlines
  models.py           Shared check, diagnosis, and run data structures
  diagnosis.py        Evidence correlation and exit status
  security.py         Configured secret collection and redaction
  watch.py            Rolling reachability samples and events
  checks/             ICMP, TCP, DNS, NTP, SNMP, route, traceroute, MTU
  reports/            Terminal, Markdown, and JSON renderers
  devices/            Protocol for future device integrations
examples/sites.yaml   Fictional station configurations
tests/                Automated checks and fixtures
```

## Development

From the repository root, create and activate a virtual environment if needed,
then install the editable package with development dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
ruff check .
ruff format --check .
```

An editable installation reflects changes to Python source without reinstalling.
The development extras supply pytest, pytest-asyncio, and Ruff. Tests cover
configuration, check parsing and execution, diagnosis, CLI behavior, reports,
secret handling, and watch history. They use mocks and local fixtures rather than
requiring access to a transmitter site.

The [GitHub Actions workflow](.github/workflows/tests.yml) runs the suite and
format/lint checks on Linux with Python 3.11, 3.12, and 3.13. It also exercises the
installed CLI and real loopback ping/route checks. CI coverage should not be read
as confirmation of compatibility with every distribution or piece of equipment.

When contributing a check, return a `CheckResult`, preserve bounded execution,
and add tests for successful, failed, and unavailable behavior. Keep example
addresses fictional and credentials out of fixtures. Vendor integrations are
currently an extension protocol only; there is no plugin discovery mechanism.

## Roadmap and license

Future releases can add persisted baselines, maintenance snapshots and comparison,
multicast membership/traffic analysis, RTP sequence/loss/jitter/SSRC analysis, and
documented device plugins. Those commands and features are **not implemented**
in version 0.1. The generic core will remain manufacturer independent.

Protocol/library references: [PySNMP async operations](https://docs.lextudio.com/pysnmp/v7.1/docs/pysnmp-hlapi-tutorial),
[dnspython async resolver](https://dnspython.readthedocs.io/en/stable/async-resolver-functions.html),
and [NTP specification, RFC 5905](https://datatracker.ietf.org/doc/html/rfc5905).

MIT licensed; see [LICENSE](LICENSE).
