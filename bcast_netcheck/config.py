"""Strict YAML loading and central defaults. Secrets stay out of result objects."""

import ipaddress
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    timeout: float = 3.0
    ping_count: int = 5
    concurrency: int = 20
    interval: float = 5.0
    latency_warn_ms: float = 100.0
    jitter_warn_ms: float = 10.0
    loss_warn_pct: float = 1.0
    ntp_warn_ms: float = 100.0
    expected_mtu: int = 1500


@dataclass(frozen=True)
class Port:
    port: int
    required: bool = False
    name: str = ""


@dataclass
class Endpoint:
    host: str
    description: str = ""
    ports: list[Port] = field(default_factory=list)
    required: bool = False
    snmp: dict = field(default_factory=dict, repr=False)
    expected_mtu: int = Settings.expected_mtu


@dataclass
class Site:
    name: str
    description: str
    endpoints: dict[str, Endpoint]
    dns: dict = field(default_factory=dict)
    ntp: dict = field(default_factory=dict)


def validate_host(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 253:
        raise ConfigError("Host must be a valid IP address or hostname")
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        pass
    if ":" in value or re.fullmatch(r"[0-9.]+", value):
        raise ConfigError("Invalid IP address")
    if not all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", x)
        for x in value.rstrip(".").split(".")
    ):
        raise ConfigError("Invalid hostname")
    return value


def number(value, low, high, label, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{label} must be numeric")
    if not math.isfinite(value) or not low <= value <= high or (integer and int(value) != value):
        raise ConfigError(f"{label} must be between {low} and {high}")
    return int(value) if integer else float(value)


def mapping(value, label):
    if not isinstance(value, dict):
        raise ConfigError(f"{label} must be a mapping")
    return value


def boolean(value, label):
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be true or false")
    return value


def endpoint(data, required=False):
    data = mapping(data, "endpoint")
    ports = data.get("ports", [])
    if not isinstance(ports, list):
        raise ConfigError("ports must be a list")
    parsed = []
    for p in ports:
        p = p if isinstance(p, dict) else {"port": p}
        parsed.append(
            Port(
                number(p.get("port"), 1, 65535, "port", True),
                boolean(p.get("required", False), "port required"),
                str(p.get("name", "")),
            )
        )
    snmp = data.get("snmp", {})
    if isinstance(snmp, bool):
        snmp = {"enabled": snmp}
    snmp = mapping(snmp, "snmp")
    if set(snmp) - {"enabled", "version", "community_env", "port"}:
        raise ConfigError("SNMP accepts enabled, version, community_env and port only")
    boolean(snmp.get("enabled", bool(snmp)), "SNMP enabled")
    if str(snmp.get("version", "2c")) != "2c":
        raise ConfigError("Version 0.1 supports SNMP version 2c only")
    if "community_env" in snmp and (
        not isinstance(snmp["community_env"], str)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", snmp["community_env"])
    ):
        raise ConfigError("Invalid SNMP environment variable name")
    if "port" in snmp:
        snmp["port"] = number(snmp["port"], 1, 65535, "SNMP port", True)
    return Endpoint(
        validate_host(data.get("host")),
        str(data.get("description", "")),
        parsed,
        boolean(data.get("required", required), "required"),
        snmp,
        number(data.get("expected_mtu", Settings.expected_mtu), 576, 9000, "expected_mtu", True),
    )


def config_path(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        if not explicit.is_file():
            raise ConfigError("Explicit configuration file does not exist")
        return explicit
    return next(
        (
            p
            for p in [
                Path.cwd() / "sites.yaml",
                Path.home() / ".config/bcast-netcheck/sites.yaml",
                Path("/etc/bcast-netcheck/sites.yaml"),
            ]
            if p.is_file()
        ),
        None,
    )


def load_sites(path: Path | None) -> dict[str, Site]:
    if path is None:
        return {}
    try:
        # Do not include YAML exceptions: they may contain credential-bearing source lines.
        raw = yaml.safe_load(path.read_text())
    except (OSError, UnicodeError, yaml.YAMLError):
        raise ConfigError("Cannot read configuration or invalid YAML") from None
    raw = mapping(raw, "configuration")
    sites = mapping(raw.get("sites"), "sites")
    result = {}
    for name, data in sites.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
            raise ConfigError("Invalid site name")
        data = mapping(data, "site")
        endpoints = {}
        if "router" in data:
            endpoints["router"] = endpoint(data["router"], True)
        for key, value in mapping(data.get("devices", {}), "devices").items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", key):
                raise ConfigError("Invalid device name")
            endpoints[f"device:{key}"] = endpoint(value)
        for key, value in mapping(data.get("gateways", {}), "gateways").items():
            if key not in ("primary", "backup"):
                raise ConfigError("Gateways must be primary or backup")
            ep = endpoint(value)
            ep.description = str(value.get("provider", key.title() + " WAN"))
            endpoints[key] = ep
        services = {}
        for service in ("dns", "ntp"):
            spec = mapping(data.get(service, {}), service)
            if spec:
                validate_host(spec.get("server"))
                if service == "dns" and "test_name" in spec:
                    validate_host(spec["test_name"])
            services[service] = spec
        if not endpoints and not any(services.values()):
            raise ConfigError("Site has no endpoints or services")
        if name.upper() in result:
            raise ConfigError("Duplicate site name (case insensitive)")
        result[name.upper()] = Site(
            name.upper(), str(data.get("description", "")), endpoints, **services
        )
    return result


def select_target(target, device, sites):
    if target.upper() in sites:
        site = sites[target.upper()]
        if device:
            key = f"device:{device}"
            if key not in site.endpoints:
                raise ConfigError("Unknown configured device")
            return site, {key: site.endpoints[key]}
        return site, site.endpoints
    if device:
        raise ConfigError("Device selection requires a configured site")
    if re.fullmatch(r"[WK][A-Z0-9]{2,5}", target.upper()):
        raise ConfigError("Unknown station; check --config or configuration location")
    return None, {
        "target": Endpoint(
            validate_host(target), ports=[Port(p) for p in (22, 80, 443)], required=True
        )
    }
