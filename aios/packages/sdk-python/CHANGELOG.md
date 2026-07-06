# Changelog

All notable changes to `aios-sdk` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/) and the project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-07-06

### Added
- Initial public client for the AIOS Control Plane `/v1` API.
- `Client` with `cohorts`, `lineage`, `approvals`, `proposals`, `admin`
  namespaces and a per-cohort `CohortHandle` (tasks, metrics, control loop,
  slot operations, safety, dimension expansion, audit export).
- `AiosApiError` normalizing non-2xx responses to `(status, detail, aios_code)`.
- API-key (`X-API-Key`) authentication and injectable `httpx` transport.
- PEP 561 typing marker (`py.typed`).
