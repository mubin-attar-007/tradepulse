# 0003 — Redis pub/sub, not a message broker

Date: 2026-06-03 · Status: Accepted

## Context
Real-time fan-out (quotes, order/fill updates) and domain events need delivery to UI clients. A full broker (Kafka/RabbitMQ) is unjustified at single-VPS, single-user scale.

## Decision
A thin in-process event bus + **Redis pub/sub** for fan-out. Durability comes from persisting state to Postgres; the UI reconciles via a REST snapshot on (re)connect (pub/sub is treated as lossy).

## Consequences
- No broker to operate.
- The transactional outbox + at-least-once delivery are deferred until real-money async broker fills require them (gated live-trading phase). A thin `EventPublisher` interface preserves that seam.
