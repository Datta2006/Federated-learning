# AirFed Stack 5 --- Harness-Driven Implementation Workflow

**Purpose:** Complete Stack 5 as one coordinated engineering effort,
using multiple specialist sub-agents, the repository's available skills,
and a continuous verification loop. This is an execution workflow, not
another architecture proposal.

## 1. Mission

Finish Stack 5 so AirFed becomes a coherent, polished, demonstrable
product on top of Stacks 1--4:

-   RPL/Trickle network simulation
-   Resilient IoT gateways and telemetry pipeline
-   Gateway-based federated learning and FedAvg
-   Global model deployment, edge inference, forecasting and monitoring

The result must have a genuinely good, consistent, responsive UI; useful
interactive visualizations; durable experiment and operational history;
and a mobile-friendly PWA sensor simulator integrated with the real
simulated network pipeline.

Do not treat the existing implementation as correct merely because it
exists. Inspect it, preserve what is sound, and improve or replace weak
parts based on evidence.

## 2. Start with repository and Phase 1 recovery

Before changing code:

1.  Identify and print the actual working directory and Git root.
2.  Confirm all work is happening inside that one repository.
3.  Inspect `git status`, current branch, uncommitted changes and recent
    relevant commits. Do not discard or overwrite user changes.
4.  Locate and inspect all Phase 1 work already performed.
5.  Verify the actual contents and import paths of:
    -   `dashboard/backend/database.py`
    -   `dashboard/backend/experiment_tracker.py`
    -   `dashboard/backend/experiment_api.py`
6.  Determine whether these files are in the active Git repository or
    were accidentally edited in another project copy.
7.  Run focused tests and inspect integration points before deciding
    what to reuse, repair or replace.

### Phase 1 work reported so far --- treat as unverified until inspected

The previous agent reported creating or modifying:

-   `dashboard/backend/database.py` --- SQLite/SQLAlchemy database
    layer, tables/session handling and singleton initialization.
-   `dashboard/backend/experiment_tracker.py` --- experiment tracking
    logic.
-   `dashboard/backend/experiment_api.py` --- FastAPI experiment
    endpoints.

It also reported addressing imports, relative import consistency, a
database initialization race condition and an experiment
round-submission endpoint.

However, the available log does **not** prove that: - the changes are
all in the correct Git repository; - the full backend test suite
passes; - actual FL coordinator runs are recorded; - MQTT telemetry,
forecasts and alerts are persisted; - experiment and telemetry history
survive a backend restart.

Do not recreate these files blindly. Audit the current repository,
preserve valid work, repair incomplete work, and finish the integration.

## 3. Multi-agent orchestration

Use the agent/sub-agent capabilities available in the environment. First
inspect the installed agent tools, project instructions and relevant
skills. Select and invoke suitable skills rather than assuming a
particular framework or imposing arbitrary implementation details.

Create specialist sub-agents for independent workstreams. Give each
agent: - a narrow ownership area and explicit deliverables; - the
relevant repository instructions and skills; - permission to inspect and
implement within its owned files; - a requirement to run focused
tests; - a requirement to report changed files, evidence, risks and
unresolved issues.

Suggested workstreams (adapt to actual tool capabilities and repository
boundaries):

  -----------------------------------------------------------------------
  Workstream                          Responsibility
  ----------------------------------- -----------------------------------
  Orchestrator / integrator           Own the plan, repository safety,
                                      interfaces, dependencies,
                                      integration order, conflict
                                      resolution and final acceptance

  Data & experiment persistence       Audit and complete Phase 1 SQLite
                                      persistence, experiment lifecycle,
                                      historical queries and migrations

  FL integration                      Connect real coordinator/client
                                      runs to experiment tracking and
                                      round metrics; verify actual
                                      training provenance

  Telemetry & edge history            Persist incoming telemetry,
                                      forecasts and alerts; preserve live
                                      update behaviour and distinguish
                                      simulated data

  Frontend product & UX               Audit and improve all dashboard
                                      pages, navigation, responsive
                                      design, accessibility and visual
                                      consistency

  Visualization & topology            Build useful interactive analytics
                                      and network topology using
                                      libraries appropriate to the
                                      existing stack

  PWA & sensor simulator              Implement
                                      installable/offline-capable PWA
                                      behaviour and connect simulated
                                      sensor submissions to the existing
                                      ingestion and routing pipeline

  QA / independent reviewer           Independently test interfaces,
                                      regressions, persistence,
                                      end-to-end behaviour and claims
                                      made by other agents
  -----------------------------------------------------------------------

Do not spawn agents merely to maximize the count. Combine workstreams if
the available agent system or repository size makes parallel ownership
unsafe.

### Coordination rules

-   The orchestrator is the single owner of the overall architecture and
    integration.
-   Agree on API contracts, schemas, event shapes and frontend data
    contracts before parallel agents depend on them.
-   Assign non-overlapping file ownership wherever possible.
-   Agents must not independently redesign shared interfaces.
-   Integrate in small increments; resolve conflicts deliberately.
-   The QA agent must challenge assumptions and verify evidence, not
    simply approve other agents' reports.
-   If sub-agents are unavailable, emulate these workstreams
    sequentially while retaining the same ownership boundaries.

## 4. Skills-first engineering

Inspect project-specific instructions (including `CLAUDE.md`,
`AGENTS.md`, README files and package scripts) and all relevant
installed skills before implementation.

Let the available skills and repository conventions determine
appropriate: - architecture and implementation patterns; -
database/session/migration approach; - frontend design system and
component patterns; - charting and graph libraries; - PWA implementation
approach; - testing strategy and accessibility checks; - code review,
debugging and verification workflows.

Do not force a particular library or framework just because it appears
in this document. Choose tools that fit the actual project, explain
consequential choices briefly, and avoid adding dependencies without a
clear benefit.

## 5. Stack 5 scope

Complete the following capabilities, adapting implementation details to
the repository and skills.

### A. Durable data and experiment lifecycle

-   Complete the existing Phase 1 work rather than restarting it.
-   Persist experiments, configuration/provenance, round-level metrics,
    telemetry, forecasts and alerts.
-   Connect experiment records to actual FL coordinator executions and
    real round outcomes.
-   Capture enough metadata to reproduce and compare runs, including
    model/configuration, seeds where applicable, dataset/partition
    information, gateway participation, timings and evaluation metrics.
-   Provide reliable historical APIs, filtering, pagination and
    experiment comparison.
-   Preserve compatibility with existing CSV/JSON registries and
    consumers where needed.
-   Ensure data survives application restarts.
-   Handle concurrent FastAPI and MQTT activity safely.
-   Use sensible indexes, transactions, error handling and schema
    evolution for the scale of this project.
-   Never manufacture experiment results or backfill invented
    measurements.

### B. Complete dashboard product experience

Review all existing pages and improve the whole product, not just one
chart:

-   Overview
-   Workers
-   Network
-   Federated Learning
-   Global Models
-   Performance / Experiments
-   Air Quality
-   Communication

Create a coherent, polished visual system. Improve information
hierarchy, navigation, page composition, responsive behaviour,
typography, spacing, contrast, loading/empty/error states, tables and
interactions.

The interface should feel like one intentionally designed product rather
than separate developer pages. It should be attractive and clear on
desktop, tablet and mobile.

Use the project's existing design conventions where good; improve them
where they are weak. Do not invent a design system disconnected from the
application.

### C. Interactive analytics and topology

Provide meaningful, interactive visualizations backed by actual APIs and
persisted data, including as supported by the real data model:

-   Observed and predicted air-quality readings and forecasts
-   FL training/evaluation trends and round history
-   Gateway participation and aggregation contributions
-   Model/version history
-   Network delivery, latency, hop, ETX/link and routing metrics
-   Communication activity and throughput
-   Gateway health and inference/deployment status

Use suitable chart and graph libraries selected through repository
inspection and skills. Replace custom visualizations when they
materially limit usability. Ensure charts have clear labels, units,
legends, tooltips, useful time ranges, responsive sizing and
understandable empty states.

Network topology should make the RPL structure, parent relationships and
state changes understandable. Do not imply that it is a packet-level
physical network or a fully RFC-compliant implementation unless the
underlying simulator supports that claim.

### D. Mobile PWA and sensor simulator

-   Make the application installable where supported.
-   Add an appropriate manifest, icons and service-worker behaviour.
-   Support a useful offline app shell.
-   Where reliable, queue sensor readings locally while offline and
    synchronize them safely when connectivity returns.
-   Prevent duplicate submissions during retries.
-   Provide a mobile-friendly sensor simulator for PM2.5, PM10,
    temperature and humidity.
-   Send readings through the existing ingestion → RPL forwarding →
    gateway pipeline.
-   Show submission status, connectivity and clear simulated-data
    labels.
-   Do not claim phones have physical PM2.5 sensors.
-   Treat push notifications and advanced background capabilities as
    optional unless the current deployment environment supports them
    reliably.

### E. Integration and product reliability

-   Preserve Stacks 1--4 and existing working functionality.
-   Avoid duplicate services, duplicate sources of truth and unnecessary
    microservices.
-   Keep simulated and historical data provenance visible.
-   Preserve the existing CNN-RNN architecture, preprocessing, scalers,
    sequence construction and delta reconstruction unless controlled
    evidence justifies a change.
-   Do not claim differential privacy, secure aggregation, physical
    sensors or production hardware behaviour that has not been
    implemented.
-   Keep configuration and persistent storage locations deployment-safe.
-   Provide useful diagnostics without exposing secrets.
-   Do not commit changes unless explicitly asked.

## 6. Harness loop --- required operating method

Use a continuous, evidence-driven loop throughout the work:

1.  **Discover:** inspect repository instructions, relevant skills,
    architecture, tests and existing behaviour.
2.  **Plan:** define a small, testable task and identify file
    ownership/dependencies.
3.  **Delegate:** assign independent tasks to specialist agents with
    explicit acceptance criteria.
4.  **Implement:** make focused changes; do not make broad speculative
    rewrites.
5.  **Test:** run focused tests and static checks immediately after each
    meaningful change.
6.  **Review:** have an independent reviewer inspect correctness, edge
    cases, security, UX and compatibility.
7.  **Integrate:** merge compatible work, resolve interface mismatches
    and run cross-stack tests.
8.  **Exercise:** run the application and verify real user workflows
    through the available browser/UI tooling where possible.
9.  **Repair:** feed failures back to the responsible agent; repeat
    until acceptance criteria pass.
10. **Record:** maintain a concise progress log with completed work,
    evidence, known issues and next actions.

Do not let an agent mark work complete solely because files were created
or code compiles. Every completion claim needs test output or observable
workflow evidence.

## 7. End-to-end acceptance

Verify as much of this workflow as the environment supports, without
fabricating success:

1.  Start the backend, broker and simulator using the documented project
    workflow.
2.  Open the dashboard and verify its primary pages and navigation.
3.  Register or use a simulated sensor and submit a reading through the
    mobile-friendly interface.
4.  Confirm that the reading enters the existing ingestion and
    RPL/gateway pipeline.
5.  Confirm that the dashboard displays the corresponding real submitted
    reading and gateway/network state.
6.  Start an actual FL training run through the existing coordinator
    workflow.
7.  Confirm that the experiment is recorded and real round metrics are
    associated with it.
8.  Confirm that model aggregation/version updates remain compatible
    with the existing registry and deployment flow.
9.  Confirm that inference, forecasts and alerts are recorded and
    visible where supported.
10. Compare at least two genuine experiment runs if the environment has
    enough runs; otherwise verify the comparison API/UI with truthful
    empty-state handling.
11. Export available historical/experiment data.
12. Restart the backend and confirm that persisted history remains
    accessible.
13. Test responsive/mobile layouts and PWA install/offline behaviour
    where the environment permits.
14. Run the complete backend test suite, frontend typecheck, production
    build and relevant integration/e2e tests.

If a workflow cannot be exercised because of environment limitations,
state exactly what was blocked and what evidence was still obtained.

## 8. Definition of done

Stack 5 is complete only when:

-   Existing Phase 1 work is verified and correctly integrated.
-   Actual FL runs and operational data are persisted.
-   Historical data remains available after restart.
-   All dashboard pages form a polished, coherent and responsive
    product.
-   Interactive charts and topology use real backend data.
-   Experiment history and comparisons reflect genuine runs.
-   The mobile PWA and sensor simulator use the existing system
    pipeline.
-   Stacks 1--4 remain functional.
-   Backend tests, frontend checks/build and relevant integration tests
    pass.
-   Remaining limitations are explicitly documented.

## 9. Final handoff report

At completion, provide a concise but evidence-based report:

1.  Workstreams/sub-agents used and their responsibilities.
2.  Phase 1 work reused, repaired or replaced.
3.  Major features delivered.
4.  Important architecture and library decisions, including why.
5.  Key files changed.
6.  Backend test results, frontend typecheck/build and integration/e2e
    results.
7.  End-to-end workflows actually demonstrated.
8.  Persistence-after-restart evidence.
9.  Screenshots or browser verification evidence where available.
10. Known limitations, environment blockers and follow-up work.

**Start by verifying the repository root and auditing the current Phase
1 changes. Then orchestrate the complete Stack 5 implementation. Do not
stop after producing another plan or blueprint.**
