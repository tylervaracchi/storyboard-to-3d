# Roadmap - ranked by impact/effort (July 2026 scout)

Status legend: **[SHIPPED]** = implemented and committed. **[PARTIAL]** = core module
shipped, some wiring or UI integration still open. **[OPEN]** = not started.
Items marked "needs live editor" cannot be finished blind; they require hands-on
verification inside a running Unreal Editor.

## 1. External-validation module + calibration dashboard  [SHIPPED]

**Impact:** This was a broken headline feature: ui/widgets/active_panel_widget.py imported `analysis.metric_validation.MetricValidator` (SSIM/PSNR/MSE/LPIPS + AI-score validation + correlation stats), but analysis/metric_validation.py did not exist in the repo. Shipping it delivers the exact thing the SIGGRAPH poster is about (self-score vs objective score), and the dashboard makes the plugin the only tool that shows users when the AI is lying about its own quality - a differentiator no competitor (Intangible, Cybever, Ludus) has.

**Done:** analysis/metric_validation.py, metrics_tracker.py, multi_model_tracker.py recovered and committed. core/external_validator.py (opencv / second_model / both strategies) shipped. The iteration loop's early-stop decision in active_panel_widget.py now cross-checks self-scores > 80 against the external validator when `validation.external_validation` is enabled (off by default; gate is min(self, external)). Settings UI toggle in General tab. analysis/calibration_dashboard.py renders a PIL scatter (self vs external, per-model colors, mean-error legend) from recorded metrics.

**Still open:** none. The dashboard PNG is now viewable in-window via Tools > Calibration Dashboard (scrollable dialog + open-in-viewer button).

## 2. One-click animatic: Movie Render Queue render of the master sequence  [PARTIAL]

**Impact:** The deliverable of previz IS a watchable animatic - Previs Pro 3 ships MP4 animatic export as a headline feature, so this is table stakes. The plugin already builds per-panel shot sequences with camera cut tracks and a master sequence, so 'storyboard in, video out' is one call away and is the single best demo/adoption hook.

**Done:** core/animatic_renderer.py (MRQ via MoviePipelineQueueSubsystem, PNG-sequence output with documented ffmpeg mux command, every class lookup version-guarded). create_master_sequence now honors per-panel durations (seconds) and sets the master playback range. MCP tool render_animatic exposed.

**Still open (needs live editor):** verify MRQ render end-to-end in 5.4/5.6/5.8, optional bundled-ffmpeg auto-mux. The 'Render Animatic' entry now exists in the main window's Tools menu (prefilled master-sequence path + existence pre-check). Note: re-running create_master_sequence on an existing master stacks duplicate sub tracks (pre-existing; clear or reuse the track on re-run).

## 3. Per-run cost estimator + live token/cost strip in the UI  [SHIPPED]

**Impact:** API cost anxiety is the top stated blocker for indie/hackathon users. All the data exists but is invisible: providers track total_cost, cache_savings, per-call tokens. Showing 'this 6-panel board at 10 iterations = $1.80' before the run converts fear into trust.

**Done:** utils/cost_estimator.py (pricing table for current Claude models + gpt-4o, alias/prefix resolution, estimate_run/format_estimate, prompt-cache discount note). Scorer split: claude_provider score_images() runs cheap re-scoring passes on claude-haiku-4-5 with correct pricing swap. Files API support (upload once, reference by file_id instead of re-sending base64 every iteration). Batch API client (api/batch_client.py, 50% token discount) for overnight runs. New settings keys: cost.use_files_api, cost.scoring_model, cost.use_scoring_model.

**Still open:** none. The strip is wired into ActivePanelWidget under the comparison result: pre-run estimate at run start (cost_estimator + configured model + batch queue size), per-iteration score points, and running spend from the loop's own total_cost. Display-only; cancel uses the existing stop flags.

## 4. Downloadable sample UE project + genre starter asset libraries  [PARTIAL]

**Impact:** Highest-leverage onboarding: a ready-made project zip turns 30-60 min of setup into 5. Genre libraries multiply first-run quality since the AI can only position assets it can match.

**Done:** samples/asset_library.fantasy.sample.json and asset_library.scifi.sample.json (BasicShapes-only, work in an empty project), samples/README.md updated.

**Still open (needs a machine with UE installed):** package a minimal UE 5.6 project with the plugin pre-built as a GitHub Release artifact. The 'Load the sample show' button now ships in the first-run welcome panel (creates SampleShow + Episode 01 from bundled samples/).

## 5. Headless/overnight batch mode  [PARTIAL]

**Impact:** The natural workflow is 'queue the whole board, come back in the morning', which no prior mode supported (batch required the editor UI up).

**Done:** core/batch_runner.py - UI-free run_batch(show, episode, provider, generate, max_panels, progress_cb): single-pass analyze + generate per panel, JSON report to Saved/StoryboardTo3D/batch_reports/, runnable from the UE Python console, provider/key bridging from plugin settings, graceful degradation without keys.

**Still open (large):** porting the iterative refinement loop out of ActivePanelWidget (Qt-timer driven) into a headless state machine via slate post-tick callbacks, and `-ExecutePythonScript` offscreen capture verification (scout-camera path may not work offscreen; SceneCapture2D fallback). An in-editor front end now exists: Tools > Overnight Batch... (show/episode/provider pickers, cancellable progress dialog over run_batch).

## 6. Semantic asset matching via embeddings  [SHIPPED]

**Impact:** Asset matching is the quality ceiling after positioning: difflib character similarity means 'canine' never finds the dog asset and falls back to a cube.

**Done:** core/asset_matcher.py - optional OpenAI text-embedding-3-small matching as PRIORITY 3 (between exact cache and fuzzy), cosine similarity >= 0.55, embeddings cached to ~/.storyboard_to_3d/embedding_cache.json keyed by text hash, batched, query cache, off by default (`asset_library.semantic_matching` + OpenAI key required), every failure falls through to the unchanged fuzzy path.

**Done (AI Librarian follow-on):** matching is only as good as the text it matches against, so the library can now describe itself. core/asset_cataloger.py describes each asset from its thumbnail (rendering one first when missing) and fills empty/placeholder descriptions plus merged aliases; core/animation_cataloger.py does the same for animation clips from a 3-pose contact sheet (10/50/90 percent scrub, SceneCapture2D chain), exposed as the `catalog_animations` MCP tool. core/animation_matcher.py gained the same embedding tier as asset_matcher (tier 3, cosine >= 0.5, own cache file `anim_embedding_cache.json`), governed by the same `asset_library.semantic_matching` toggle.

**Still open:** local-model fallback via the pytorch_server.py subprocess pattern (/embed endpoint with sentence-transformers) for keyless users.

## 7. Storyboarder (.storyboarder) and ComfyUI folder import  [SHIPPED]

**Impact:** Free inbound pipeline from the most popular free storyboard tool; ComfyUI folder import covers AI-generated boards.

**Done:** core/importers/ package - storyboarder_importer.py (boards array, image resolution, duration ms-to-s, dialogue/action returned per panel) and image_folder_importer.py (natural sort, multi-pattern glob), both importing through EpisodesManager with get-or-create show/episode.

**Still open:** register both in the Import Panels dialog (ui/main_window.py) as file-type filters; persist imported durations into panels_metadata.json (the managers only accept image paths today - importer returns the metadata for the caller).

## 8. Iteration progress UI with live score graph and cancel button  [SHIPPED]

**Impact:** A 10-20-iteration run is minutes of apparent freeze today; a visible 'iteration 7/20, score 62 to 78, $0.34 spent, Stop & keep best' panel is what makes people trust the loop.

**Done:** ui/widgets/iteration_progress.py - self-contained IterationProgressWidget with QPainter score sparkline, current-score readout, cost label, cancel button emitting a `cancelled` Signal. Integration point documented in-file.

**Still open:** none. Wired into ActivePanelWidget: instantiated under the comparison result, fed once per iteration right after _record_iteration_metrics, cancel routed to the existing capture_workflow_active / auto_iterate / batch stop flags.

## 9. USD export of the generated scene  [PARTIAL]

**Impact:** Makes the output portable to Houdini, Maya, Omniverse, and studio USD pipelines instead of trapping results inside one UE project.

**Done:** core/usd_exporter.py - export_level_usd() via AssetExportTask + LevelExporterUSD(Options), version-guarded, clear error when the USD plugin is disabled.

**Still open (needs live editor):** LevelSequence USD export (camera animation), spawnable-to-possessable conversion or transform baking before export. The menu item now exists (Tools > Export Level as USD, file picker + result dialog).

## 10. One-button A/B provider comparison mode  [PARTIAL]

**Impact:** Turns the thesis's most shareable result (Claude 83.3% vs GPT-4o 16.7% at equal confidence) into a product feature - and every run generates calibration data feeding item 1's dashboard.

**Done:** core/ab_comparison.py - snapshot/restore of StoryboardGenerated-tagged actor transforms, run-per-provider orchestration taking callables, score extraction, placed-actor counts, elapsed time, provider-failure tolerance.

**Still open:** 'Compare Providers' UI action + side-by-side results dialog (hero captures, self vs objective score, iterations, cost).

---

# July 14 additions (wow + speed round)

## 16. Mood-to-lighting pass  [SHIPPED]
core/mood_lighting.py: 10 presets + synonym/fuzzy mood resolution; finds or spawns DirectionalLight/SkyLight/fog and applies the preset. Wired into scene building behind 'scene.apply_mood_lighting' (off by default).

## 17. Animation picker  [SHIPPED]
core/animation_matcher.py + samples/animation_library.sample.json: matches per-character action text to a tagged animation library (AssetMatcher's difflib pattern) and plays the clip on skeletal spawnables in single-node mode. Behind 'scene.auto_animation' (off). Needs real AnimSequence assets pointed at by the show's animation_library.json.

## 18. Camera move picker  [SHIPPED]
core/camera_moves.py: shot type -> push-in / drift / pan keyframed on the shot camera's transform track, current-transform-aware, skips rather than keying garbage. Behind 'sequence.camera_moves' (off). Sequencer channel APIs are the most version-variant surface in UE Python: verify in a live editor per engine version.

## 19. Image transport optimization + HTTP session reuse  [SHIPPED]
utils/image_prep.py: 1288 px long edge + JPEG 85 before base64/upload (5-10x smaller, token-cheaper); keep-alive requests.Session in both providers. ON by default ('performance.optimize_images' to disable).

## 20. Adaptive capture views  [SHIPPED]
Iteration 1 captures all 7 views; refinement iterations capture hero+top+right when 'performance.reduced_refinement_views' is on (off by default). Also filters stale skipped-view PNGs from the API payload. Estimated ~60s saved per refinement iteration.

## 21. SceneCapture2D rig (viewport-free capture)  [PARTIAL - needs live editor]
ai_vision/scene_capture_rig.py: pre-placed SceneCapture2D per view with own render targets, capture-every-frame off, exports the same test_<view>.png files. All 7 views in ~a frame vs 5-10s of viewport piloting; also eliminates the scout-camera viewport-locking bug class. Open: FOV sync with the CineCamera hero, live verification, then loop wiring behind 'performance.scene_capture_rig'.

## 22. Generative 3D fallback (Meshy / Tripo3D)  [SHIPPED - experimental]
core/gen3d/: provider-abstracted text-to-3D client (Meshy verified against live docs 2026-07-14; Tripo coded defensively, marked VERIFY-BEFORE-USE), import via AssetImportTask (FBX preferred), manifest cache so an asset is never generated twice, per-run cap. Two activation points: AssetMatcher.find_best_match PRIORITY 5, and the gen3d rescue in SceneBuilder that intercepts entities about to be rejected as hallucinations, generates them, and writes them into the show's asset_library.json. Behind 'gen3d.enabled' (off), keys via MESHY_API_KEY / TRIPO_API_KEY. Needs a live API-key test before demoing.

## 23. Parallel batch analysis  [SHIPPED]
batch_runner run_batch(analysis_workers=3): analysis phase fans out on threads (per-worker client instances), generation stays strictly serial on the game thread. --workers N on the CLI.

## 24. Generative animation fallback (Tripo / DeepMotion)  [SHIPPED - experimental]
core/genanim/: mirrors core/gen3d. When the animation picker misses, TripoAnimProvider maps action text to a preset and runs animate_retarget against a pre-provisioned rig task id, or DeepMotionProvider (SayMotion, partner-gated) does true text-to-motion; the clip imports to /Game/StoryboardTo3D/GeneratedAnims, registers in the show's animation_library.json, and a sha256 manifest prevents regenerating the same action. Behind 'genanim.enabled' (off), per-run cap 'genanim.max_per_run' (default 2), Settings > Features row. Provider request/response shapes marked VERIFY-BEFORE-USE; needs a live API-key test before demoing. Clips arrive on provider skeletons; retarget via IK Retargeter.

## 25. First-run welcome, Tools menu reachability, error surfacing  [SHIPPED]
ui/main_window.py: inline welcome panel while no shows exist (create first show / load bundled sample show / Quick Start); Tools menu exposing animatic render, USD export, calibration dashboard, and overnight batch; notify_user() routing failures to a modeless box + status bar + Output Log; Analyze All gets a cancellable progress dialog, honest failure reporting, bulk persistence, and grid refresh; drag-reorder now persists via '__panel_order__' in panels_metadata.json; settings OK rebuilds the AI client without an editor restart.

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
