"""SNMP v2c availability and three standard system OIDs, with environment secrets."""

import asyncio
import os

from bcast_netcheck.models import CheckResult
from bcast_netcheck.models import CheckStatus as S
from bcast_netcheck.security import redact

OIDS = {
    "sysName": "1.3.6.1.2.1.1.5.0",
    "sysDescr": "1.3.6.1.2.1.1.1.0",
    "sysUpTime": "1.3.6.1.2.1.1.3.0",
}


async def check(host, settings, config):
    if not config.get("enabled", bool(config)):
        return CheckResult("SNMP", S.SKIP, host, message="SNMP not configured")
    community = os.environ.get(config.get("community_env", ""))
    if not community:
        return CheckResult(
            "SNMP", S.SKIP, host, message="SNMP enabled but community environment variable is unset"
        )
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        Udp6TransportTarget,
        UdpTransportTarget,
        get_cmd,
    )
    from pysnmp.proto.rfc1905 import EndOfMibView, NoSuchInstance, NoSuchObject

    from bcast_netcheck.checks.route import address

    engine = SnmpEngine()
    try:
        destination = await address(host)
        transport_class = Udp6TransportTarget if ":" in destination else UdpTransportTarget
        transport = await transport_class.create(
            (destination, config.get("port", 161)), timeout=settings.timeout * 0.8, retries=0
        )
        error, status, index, bindings = await asyncio.wait_for(
            get_cmd(
                engine,
                CommunityData(community, mpModel=1),
                transport,
                ContextData(),
                *(ObjectType(ObjectIdentity(oid)) for oid in OIDS.values()),
                lookupMib=False,
            ),
            settings.timeout * 0.9,
        )
        if error:
            return CheckResult(
                "SNMP",
                S.FAIL,
                host,
                message="No valid SNMP response; check endpoint and credentials",
            )
        if status:
            return CheckResult(
                "SNMP", S.WARN, host, message="SNMP responded but denied the system OID query"
            )
        data = {name: redact(str(binding[1]), [community]) for name, binding in zip(OIDS, bindings)}
        missing = any(
            isinstance(b[1], (NoSuchObject, NoSuchInstance, EndOfMibView)) for b in bindings
        ) or len(bindings) != len(OIDS)
        return CheckResult(
            "SNMP",
            S.WARN if missing else S.PASS,
            host,
            message="SNMP responded; some OIDs unavailable"
            if missing
            else "SNMP system OIDs responsive",
            details=data,
        )
    except TimeoutError:
        return CheckResult("SNMP", S.FAIL, host, message="SNMP response timed out")
    except Exception:
        return CheckResult("SNMP", S.ERROR, host, message="SNMP query could not execute")
    finally:
        engine.close_dispatcher()
