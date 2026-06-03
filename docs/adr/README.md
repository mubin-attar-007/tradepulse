# Architecture Decision Records

Short, dated records of significant, hard-to-reverse decisions. Format: Context → Decision → Consequences. Supersede rather than edit when a decision changes.

| # | Decision | Status |
|---|----------|--------|
| [0001](0001-modular-monolith.md) | Modular monolith (not microservices) | Accepted |
| [0002](0002-async-task-queue-arq.md) | ARQ for background jobs | Accepted |
| [0003](0003-redis-not-kafka.md) | Redis pub/sub, not a message broker | Accepted |
| [0004](0004-sessions-not-jwt.md) | Opaque Redis sessions, not JWT | Accepted |
| [0005](0005-owner-id-tenancy.md) | `owner_id` on every domain row | Accepted |
| [0006](0006-decimal-money.md) | `Decimal`/`NUMERIC` money; decimal strings over the wire | Accepted |
| [0007](0007-tooling-uv-npm-just.md) | uv + npm + just + Docker Compose | Accepted |
| [0008](0008-one-canonical-strategyspec.md) | One canonical `StrategySpec` (generated downstream) | Accepted |
