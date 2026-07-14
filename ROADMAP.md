# Roadmap - ranked by impact/effort (July 2026 scout)

Status legend: **[SHIPPED]** = implemented and committed. **[PARTIAL]** = core module
shipped, some wiring or UI integration still open. **[OPEN]** = not started.
Items marked "needs live editor" cannot be finished blind; they require hands-on
verification inside a running Unreal Editor.

## 1. External-validation module + calibration dashboard  [SHIPPED]

**Impact:** This was a broken headline feature: ui/widgets/active_panel_widget.py imported `analysis.metric_validation.MetricValidator` (SSIM/PSNR/MSE/LPIPS + AI-score validation + correlation stats), but analysis/metric_validation.py did not exist in the repo. Shipping it delivers the exact thing the SIGGRAPH poster is about (self-score vs objective score), and the dashboard makes the plugin the only tool that shows users when the AI is lying about its own quality - a differentiator no competitor (Intangible, Cybever, Ludus) has.

**Done:** analysis/metric_validation.py, metrics_tracker.py, multi_model_tracker.py recovered and committed. core/external_validator.py (opencv / second_model / both strategies) shipped. The iteration loop's early-stop decision in active_panel_widget.py now cross-checks self-scores > 80 against the external validator when `validation.external_validation` is enabled (off by default; gate is min(self, external)). Settings UI toggle in General tab. analysis/calibration_dashboard.py renders a PIL scatter (self vs external, per-model colors, mean-error legend) from recorded metrics.

**Still open:** a Qt tab embedding the dashboard PNG in the main window (small wiring pass).

## 2. One-click animatic: Movie Render Queue render of the master sequence  [PARTIAL]

**Impact:** The deliverable of previz IS a watchable animatic - Previs Pro 3 ships MP4 animatic export as a headline feature, so this is table stakes. The plugin already builds per-panel shot sequences with camera cut tracks and a master sequence, so 'storyboard in, video out' is one call away and is the single best demo/adoption hook.

**Done:** core/animatic_renderer.py (MRQ via MoviePipelineQueueSubsystem, PNG-sequence output with documented ffmpeg mux command, every class lookup version-guarded). create_master_sequence now honors per-panel durations (seconds) and sets the master playback range. MCP tool render_animatic exposed.

**Still open (needs live editor):** verify MRQ render end-to-end in 5.4/5.6/5.8, a 'Render Animatic' button in ui/main_window.py, optional bundled-ffmpeg auto-mux. Note: re-running create_master_sequence on an existing master stacks duplicate sub tracks (pre-existing; clear or reuse the track on re-run).

## 3. Per-run cost estimator + live token/cost strip in the UI  [PARTIAL]

**Impact:** API cost anxiety is the top stated blocker for indie/hackathon users. All the data exists but is invisible: providers track total_cost, cache_savings, per-call tokens. Showing 'this 6-panel board at 10 iterations = $1.80' before the run converts fear into trust.

**Done:** utils/cost_estimator.py (pricing table for current Claude models + gpt-4o, alias/prefix resolution, estimate_run/format_estimate, prompt-cache discount note). Scorer split: claude_provider score_images() runs cheap re-scoring passes on claude-haiku-4-5 with correct pricing swap. Files API support (upload once, reference by file_id instead of re-sending base64 every iteration). Batch API client (api/batch_client.py, 50% token discount) for overnight runs. New settings keys: cost.use_files_api, cost.scoring_model, cost.use_scoring_model.

**Still open:** wiring the strip into ActivePanelWidget next to match_progress (:807) - supervised pass, the widget is 6k lines. ui/widgets/iteration_progress.py has the integration comment.

## 4. Downloadable sample UE project + genre starter asset libraries  [PARTIAL]

**Impact:** Highest-leverage onboarding: a ready-made project zip turns 30-60 min of setup into 5. Genre libraries multiply first-run quality since the AI can only position assets it can match.

**Done:** samples/asset_library.fantasy.sample.json and asset_library.scifi.sample.json (BasicShapes-only, work in an empty project), samples/README.md updated.

**Still open (needs a machine with UE installed):** package a minimal UE 5.6 project with the plugin pre-built as a GitHub Release artifact; 'Load Sample Show' button in show_manager.py.

## 5. Headless/overnight batch mode  [PARTIAL]

**Impact:** The natural workflow is 'queue the whole board, come back in the morning', which no prior mode supported (batch required the editor UI up).

**Done:** core/batch_runner.py - UI-free run_batch(show, episode, provider, generate, max_panels, progress_cb): single-pass analyze + generate per panel, JSON report to Saved/StoryboardTo3D/batch_reports/, runnable from the UE Python console, provider/key bridging from plugin settings, graceful degradation without keys.

**Still open (large):** porting the iterative refinement loop out of ActivePanelWidget (Qt-timer driven) into a headless state machine via slate post-tick callbacks, and `-ExecutePythonScript` offscreen capture verification (scout-camera path may not work offscreen; SceneCapture2D fallback).

## 6. Semantic asset matching via embeddings  [SHIPPED]

**Impact:** Asset matching is the quality ceiling after positioning: difflib character similarity means 'canine' never finds the dog asset and falls back to a cube.

**Done:** core/asset_matcher.py - optional OpenAI text-embedding-3-small matching as PRIORITY 3 (between exact cache and fuzzy), cosine similarity >= 0.55, embeddings cached to ~/.storyboard_to_3d/embedding_cache.json keyed by text hash, batched, query cache, off by default (`asset_library.semantic_matching` + OpenAI key required), every failure falls through to the unchanged fuzzy path.

**Still open:** local-model fallback via the pytorch_server.py subprocess pattern (/embed endpoint with sentence-transformers) for keyless users.

## 7. Storyboarder (.storyboarder) and ComfyUI folder import  [SHIPPED]

**Impact:** Free inbound pipeline from the most popular free storyboard tool; ComfyUI folder import covers AI-generated boards.

**Done:** core/importers/ package - storyboarder_importer.py (boards array, image resolution, duration ms-to-s, dialogue/action returned per panel) and image_folder_importer.py (natural sort, multi-pattern glob), both importing through EpisodesManager with get-or-create show/episode.

**Still open:** register both in the Import Panels dialog (ui/main_window.py) as file-type filters; persist imported durations into panels_metadata.json (the managers only accept image paths today - importer returns the metadata for the caller).

## 8. Iteration progress UI with live score graph and cancel button  [PARTIAL]

**Impact:** A 10-20-iteration run is minutes of apparent freeze today; a visible 'iteration 7/20, score 62 to 78, $0.34 spent, Stop & keep best' panel is what makes people trust the loop.

**Done:** ui/widgets/iteration_progress.py - self-contained IterationProgressWidget with QPainter score sparkline, current-score readout, cost label, cancel button emitting a `cancelled` Signal. Integration point documented in-file.

**Still open:** supervised wiring into ActivePanelWidget (instantiate near match_progress :807, feed from _record_iteration_metrics, check the cancel flag between capture steps).

## 9. USD export of the generated scene  [PARTIAL]

**Impact:** Makes the output portable to Houdini, Maya, Omniverse, and studio USD pipelines instead of trapping results inside one UE project.

**Done:** core/usd_exporter.py - export_level_usd() via AssetExportTask + LevelExporterUSD(Options), version-guarded, clear error when the USD plugin is disabled.

**Still open (needs live editor):** LevelSequence USD export (camera animation), spawnable-to-possessable conversion or transform baking before export, menu items in ui/main_window.py.

## 10. One-button A/B provider comparison mode  [PARTIAL]

**Impact:** Turns the thesis's most shareable result (Claude 83.3% vs GPT-4o 16.7% at equal confidence) into a product feature - and every run generates calibration data feeding item 1's dashboard.

**Done:** core/ab_comparison.py - snapshot/restore of StoryboardGenerated-tagged actor transforms, run-per-provider orchestration taking callables, score extraction, placed-actor counts, elapsed time, provider-failure tolerance.

**Still open:** 'Compare Providers' UI action + side-by-side results dialog (hero captures, self vs objective score, iterations, cost).

---

# Frontier / blocked items (need hands-on verification or external accounts)

## 11. MCP image returns  [SHIPPED, interim form]
capture_scene_views(include_images=True) embeds base64 PNGs (downscaled to cap payload) so an MCP client can SEE the scene it is directing; validate_scene tool exposes the external validator to agents. Native MCP image content blocks ({"type":"image","data":...,"mimeType":"image/png"}) should replace the base64 payload once Epic documents the Python-to-MCP mapping for tool results.

## 12. Script-to-shot-list front end  [SHIPPED]
core/script_breakdown.py: text-only LLM breakdown of a script into numbered shots (description/characters/props/location/shot size), strict JSON with normalization, saved to Saved/StoryboardTo3D/breakdowns/. Panels still need images; pairs naturally with item 7's importers once boards are drawn or generated.

## 13. PCG set dressing pass (UE 5.7+)  [OPEN - needs live editor]
Procedural background props around VLM-placed hero actors via PCG Python interop (Beta in 5.7). Tracked in GitHub issue #2. Blocked on hands-on API verification.

## 14. Generative environment backdrops (Marble / Gaussian splats)  [OPEN - needs evaluation]
Import splat/mesh exports (PLY/glTF) behind the hero framing; panel analysis already extracts a location string usable as the generator prompt. Blocked on export-format and UE-splat-plugin evaluation.

## 15. Prebuilt binaries per engine version + Fab listing  [OPEN - needs UE build machine]
Release zips with prebuilt Win64 binaries for 5.4-5.8 so non-C++ users skip Visual Studio; then a Fab marketplace listing (repo structure already complies).
