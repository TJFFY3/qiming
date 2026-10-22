# 导学案知识库原图 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the coordinated implementation below.

**Goal:** 本课知识库原图出现在导学案网页预览与 Word，修复已有两个图片描述占位段落。
**Architecture:** Add canonical image blocks `{id,type:"image",image_id,caption}`. Extract stable 24-hex image IDs from actual source Markdown, pass a catalog to the model, resolve only source-bound assets on server, snapshot assets with each immutable version. Render the same assets in DOCX and a version-scoped image API.
**Tech Stack:** Existing FastAPI/httpx/python-docx/React/JSON schema; no new runtime dependency.
**Spec:** User-approved direct implementation in current chat; real source images only, preview and Word parity, preserve unrelated content and historical versions.

## Global Constraints
- Preserve existing timeout fix and other Agent changes.
- Model never chooses arbitrary image URLs or local file paths.
- Only configured FastGPT origin and `/api/system/file/d/` image URLs can be downloaded; bounded bytes/time, validate image bytes; no credential forwarding; bounded redirects only to trusted FastGPT file CDN.
- Existing text/table and revision/hash behavior must remain compatible.

## Review Focus
- Missing/foreign image IDs: reject before publishing.
- Broken downloads: explicit failure rather than a fake image placeholder.
- Later source deletion/unavailability: historical and unchanged revision images use cached version assets.
- Patch insertion: preserve untargeted blocks, section metadata and original versions.
- Image geometry: fit printable width and bounded height without distorting aspect ratio.

### Task 1: Asset resolution
Files: backend/app/study_images.py; backend/tests/test_study_images.py.
- [x] Write failing tests for catalog extraction, foreign IDs/origins, bounded downloads, invalid bytes and cached images.
- [x] Implement image_catalog(sources)->list[dict] with image_id, source_id, description, url. prepare_image_assets(blocks,sources,cache_dir,transport=None,allowed_origin=None)->dict[str,Path].
- [x] Verify focused tests.

### Task 2: Canonical image blocks and Word
Files: vendor/chemistry/references/outline.schema.json; scripts/outline_contract.py, docx_tools.py, render_outline.py, revise_outline.py; backend/app/documents.py; backend/tests/test_study_image_documents.py.
- [x] Add failing real DOCX tests for image embedding, dimensions and revision caching.
- [x] Extend schema/contract; add image_assets optional arguments to render_document, revise_document, generate_outline; copy required assets to version/images/{id}.bin and embed inline picture/caption.
- [x] DocumentEngine validates provenance, downloads assets and supplies original cached assets on revision.
- [x] Verify real media parts and unchanged historical documents.

### Task 3: Preview and API
Files: frontend/src/api.ts, components/OutlinePreview.tsx, styles.css and image preview tests; backend/app/api.py and API tests.
- [x] Write failing image preview test.
- [x] Extend Block union and render figure/img/caption using `/api/sessions/{sid}/versions/{vid}/images/{image_id}`; size responsively, show visible load failure.
- [x] API serves only referenced image IDs from that version and path-checked snapshot files.
- [x] Verify preview test/API response and build.

### Task 4: Prompt, recovery and validation
Files: backend/app/pipeline.py; regression tests; README.md.
- [x] Supply image catalog for generation/revision; preserve complete descriptions independently of source excerpt limits. Instruct real image blocks, prohibit descriptive placeholders when image requested.
- [x] Recover screenshot session by replacing the two known placeholder blocks with exact matched source images plus retained student tasks in a new version.
- [x] Run backend/vendor/frontend suites, build, render and inspect recovered DOCX, review changes, restart application, verify image/Word endpoints.

Ruling: Real FastGPT originals return 302 redirects to presigned HTTPS file.fastgpt.cn URLs. Follow at most 3 redirects to that CDN or the original file endpoint, validate every hop, clear cookies and send no Authorization. The source URL remains strictly provenance-bound.

Verification: real source images embedded and version endpoints return image/png; screenshot session repaired as v005; rendered DOCX with temporary CJK font configuration for visual QA. Code review found malformed patch image preflight regression; added failing pipeline test and repaired ValueError classification.
