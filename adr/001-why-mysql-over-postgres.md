# ADR 001: MySQL over PostgreSQL for Primary Database

**Status**: Accepted

**Date**: 2026-02-16

## Context

We needed to choose a primary relational database for CostIntel Pipeline. The main contenders were PostgreSQL and MySQL 8.0+. Both are production-ready, support JSON, have async drivers, and are widely used in enterprise environments.

Key considerations:
- **Team expertise**: FinOps teams are more familiar with MySQL in enterprise settings
- **JSON support**: MySQL 8.0+ has robust JSON column types and functions
- **Async support**: Both have async Python drivers (asyncpg for PostgreSQL, aiomysql for MySQL)
- **Hosting compatibility**: Both available on all major cloud providers
- **Operational complexity**: Similar operational overhead

## Decision

We chose **MySQL 8.0+** as the primary database.

Rationale:
1. **Enterprise alignment**: MySQL is more commonly used in the target market (FinOps, enterprise cloud management)
2. **Migration path**: Existing tools and teams often have MySQL experience
3. **Feature parity**: MySQL 8.0+ JSON support matches PostgreSQL's for our use case
4. **SQLAlchemy compatibility**: Full async support via aiomysql with SQLAlchemy 2.0

## Consequences

### Positive
- Easier adoption for enterprise teams with existing MySQL infrastructure
- Familiar operational patterns for DBAs
- Strong tooling ecosystem (MySQL Workbench, Percona, etc.)

### Negative
- Slightly less advanced JSON querying compared to PostgreSQL
- No built-in full-text search as sophisticated as PostgreSQL's
- Community perception sometimes favors PostgreSQL for "modern" applications

## Mitigations

- Use SQLAlchemy 2.0's JSON column types for flexible metadata storage
- Accept trade-off: our JSON usage is primarily for metadata storage, not complex querying
- Can migrate to PostgreSQL later if needed (SQLAlchemy abstracts most differences)

## Related Decisions

- Alembic for migrations (works with both databases)
- SQLAlchemy 2.0 with async support
- aiomysql as the async driver
