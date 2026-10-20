# Interactive Courseware Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task by task.

**Goal:** Build the confirmed independent interactive courseware Agent.
**Architecture:** Independent React feature and FastAPI package; separate database, storage, prompts and jobs. Shared app only selects and mounts agents; reusable chemistry PPT tools assemble files.
**Tech Stack:** React, TypeScript, FastAPI, SQLite, lxml, bundled chemistry tools.
**Spec:** docs/superpowers/specs/2026-10-20-courseware-agent-design.md

## Global Constraints

- Preserve existing uncommitted work and existing guide APIs.
- Use `/api/courseware`, `data/courseware/`, independent browser storage.
- Use supplied PPT template/generate_pptx/validate_paths; no new PPT library.
- Explicitly accept unverified drafts; never invent source verification.
- Body ≥24pt, title ≥32pt, ≤6 paragraphs/200 characters, reject overflow.

## Review Focus

- Upload/job races must not mutate a running snapshot.
- Interrupted jobs recover as failed; no repeated remote calls on restart.
- Stale revision baselines and guide IDs must not resolve in courseware.
- Custom optimization values must survive reopening and repeated fill.
- Malformed model output and arbitrary image paths must fail safely.

### Task 1: Independent backend generation and persistence

Files: `backend/app/courseware/{models,store,model_client,prompting,export,pipeline,api,__init__}.py`, `backend/app/main.py`, `backend/tests/test_courseware.py`.
Interfaces: `CoursewareStore(path)`, `CoursewarePipeline(settings,store,retriever,model)`, `make_router(settings,store,pipeline)`; sessions contain settings/resources/messages/versions/jobs, jobs expose status/stages/error/version_id.

- [x] Write and run failing integration tests for namespace isolation, actual PPTX export, source/draft behavior, revision immutability, uploads and restart recovery.
- [x] Implement independent contracts, transactional job reservations, source snapshots, remote adapter, bounded validation repair, template export and namespace routes.
- [x] Run `pytest backend/tests/test_courseware.py -q`; expected all pass.

### Task 2: Courseware input and optimization UI

Files: `frontend/src/agents/courseware/{types,api,prompt,OptimizeDialog,Composer,CoursewareAgent,Preview,Resources,courseware.css}.*`, `frontend/src/App.tsx`, `frontend/src/agents/courseware/*.test.*`.
Interfaces: `CoursewareAgent({onGuide})` mounted by shared selector; independent API prefix and browser keys; optimization uses `scope/duration/pages/exercises/teaching/focus/extra`.

- [x] Write and run failing tests for option fill/cancel/custom fields, prompt replacement, switching isolation and submission namespace.
- [x] Implement screenshot UI, independent lifecycle/polling/history/resources/library, structured semantic-run preview, downloads and revisions.
- [x] Run frontend tests and build; expected pass.

### Task 3: Verify and document

Files: `README.md`, `docs/verification.md`, feature tests as needed.
- [x] Run full backend/vendor/frontend suites and production build.
- [x] Review complete changes independently; fix material findings with regression tests.
- [x] Inspect running UI in browser at desktop/mobile, optimization and result views.
- [x] Record exact evidence and remaining remote/Office verification limits. Do not stage or commit unrelated user changes.

## Execution record

Implemented inline on codex/courseware-agent; existing uncommitted edits preserved. Independent review completed and material findings fixed with RED/GREEN regression tests. Final full suites: 185 backend/vendor, 40 frontend; production build passed. Real FastGPT generation and page patch verified; Office/WPS visual review remains a teacher verification boundary. No Git commit or push performed to avoid bundling concurrent work.
