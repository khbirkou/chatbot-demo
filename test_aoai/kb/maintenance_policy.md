# Maintenance Policy

## Statuses
- AVAILABLE: ready for use
- IN_SERVICE: scheduled maintenance
- MAINTENANCE: repairs or urgent checks
- OUT_OF_ORDER: not usable, blocked

## Rules
- If a mower reports repeated navigation failures within 24h → set status to MAINTENANCE.
- After MAINTENANCE, a mower must pass a 10-minute functional test → then set to AVAILABLE.
- OUT_OF_ORDER requires a work order with priority HIGH.

## SLA (internal)
- HIGH: response within 4 hours
- MEDIUM: response within 1 business day
- LOW: response within 3 business days
