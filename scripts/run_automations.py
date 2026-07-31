from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import app.main  # noqa: E402,F401
from app.core.database import SessionLocal, set_tenant_context  # noqa: E402
from app.modules.accounts.models import Tenant  # noqa: E402
from app.modules.automation.service import AutomationEngine  # noqa: E402
from app.modules.sequences.service import CadenceService  # noqa: E402


def process_once() -> tuple[int, int, int, int]:
    with SessionLocal() as control_db:
        tenant_ids = [row.id for row in control_db.query(Tenant).filter(Tenant.is_active.is_(True))]

    evaluated = 0
    matched = 0
    cadence_evaluated = 0
    cadence_executed = 0
    for tenant_id in tenant_ids:
        with SessionLocal() as tenant_db:
            tenant_db.info["enforce_tenant_rls"] = True
            set_tenant_context(tenant_db, tenant_id)
            tenant_evaluated, tenant_matched = AutomationEngine(tenant_db).run_scheduled(
                tenant_id,
                None,
            )
            evaluated += tenant_evaluated
            matched += tenant_matched
            tenant_cadence_evaluated, tenant_cadence_executed = CadenceService(
                tenant_db
            ).process_due(tenant_id)
            cadence_evaluated += tenant_cadence_evaluated
            cadence_executed += tenant_cadence_executed

    return evaluated, matched, cadence_evaluated, cadence_executed


def main() -> None:
    parser = argparse.ArgumentParser(description="Process scheduled CRM automations")
    parser.add_argument("--loop", action="store_true", help="Keep polling until stopped")
    parser.add_argument(
        "--interval",
        type=float,
        default=60,
        help="Seconds between scheduled scans",
    )
    args = parser.parse_args()
    while True:
        evaluated, matched, cadence_evaluated, cadence_executed = process_once()
        print(
            "Scheduled automation complete: "
            f"evaluated={evaluated}, matched={matched}, "
            f"cadence_evaluated={cadence_evaluated}, cadence_executed={cadence_executed}",
            flush=True,
        )
        if not args.loop:
            return
        time.sleep(max(args.interval, 5))


if __name__ == "__main__":
    main()
