# Courseware original images implementation plan

**Goal:** Give the independent courseware Agent the source-bound original-image selection and delivery capabilities present in the guide Agent.
**Architecture:** Share only neutral source-image parsing/downloading primitives. Courseware owns slide image IDs, version caches, API routes, image layout, preview and presentation state. Models never select filesystem paths or invent URLs. Existing text-only decks continue to work.
**Scope:** PNG/JPEG original images already referenced in the current lesson's source evidence; one source image and short caption per slide; preserve aspect ratio and embed image bytes in PPTX. Source image availability errors remain distinct from model-output repairs. No new image-generation service or external image search.
**Stack:** Existing FastAPI, Python OOXML/PPT renderer, React/TypeScript.

- [x] Add failing backend tests for source catalog, source-bound slide image schema, PPT/media embedding, PNG serving, invalid IDs, offline revision reuse and image download failures.
- [x] Extract shared source-image tools to a neutral module with compatibility imports for guide tests. Add courseware image adapter, schema, model context, export assets and version image endpoint; paginate using image-specific capacity.
- [x] Add frontend regression for image rendering, caption, enlargement, failed image and image-free slides; implement native slide image display in preview and presentation.
- [x] Run backend suites, frontend tests and build; check actual source images and a real image-enabled PPT if the current knowledge library has originals. Preserve pre-existing uncommitted work and user versions.
