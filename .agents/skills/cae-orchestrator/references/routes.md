# Alle Routen des CAE-Orchestrators

Erzeugt aus `cae_orchestrator/server.py`. Aufruf über

`python3 cae_cli.py raw <GET|POST> <pfad> [--data '<json>']`.


Insgesamt 135 Routen in 40 Bereichen.


## project  (29)

- `POST /project/<pid>/activate` — activate_project
- `POST /project/<pid>/attachments` — project_attachments
- `GET  /project/<pid>/bundle` — project_bundle
- `POST /project/<pid>/clone` — project_clone
- `POST /project/<pid>/delete` — delete_project
- `GET  /project/<pid>/em_field` — project_em_field
- `POST /project/<pid>/links` — project_links
- `POST /project/<pid>/links/remove` — project_links_remove
- `GET  /project/<pid>/load` — load_project
- `GET  /project/<pid>/manifest` — project_manifest
- `POST /project/<pid>/meta` — project_meta_update
- `GET  /project/<pid>/oilspray` — project_oilspray
- `GET  /project/<pid>/oilspray/saved` — project_oilspray_saved_list
- `GET  /project/<pid>/oilspray/saved/<rid>` — project_oilspray_saved_load
- `POST /project/<pid>/oilspray/saved/<rid>/delete` — project_oilspray_saved_delete
- `GET  /project/<pid>/oilspray/saved/<rid>/video` — project_oilspray_saved_video
- `GET  /project/<pid>/rag` — project_rag_list
- `POST /project/<pid>/rag/<doc_id>/delete` — project_rag_delete
- `POST /project/<pid>/rag/add` — project_rag_add
- `POST /project/<pid>/rating` — project_rating
- `POST /project/<pid>/recompute` — project_recompute
- `POST /project/<pid>/report` — make_report
- `GET  /project/<pid>/report/download` — download_report
- `GET  /project/<pid>/report/rag_md` — download_report_rag_md
- `POST /project/<pid>/report/rag_md/add` — add_report_rag_md
- `GET  /project/<pid>/template` — project_template
- `GET  /project/<pid>/thumb` — project_thumb
- `GET  /project/<pid>/video/<mode>` — project_video
- `POST /project/new` — project_new

## em3d  (14)

- `POST /em3d` — em3d_start
- `POST /em3d/abort` — em3d_abort
- `GET  /em3d/paraview` — em3d_paraview
- `POST /em3d/preview` — em3d_preview
- `POST /em3d/save` — em3d_save
- `GET  /em3d/saved` — em3d_saved_list
- `GET  /em3d/saved/<rid>` — em3d_saved_load
- `POST /em3d/saved/<rid>/delete` — em3d_saved_delete
- `POST /em3d/sector` — em3d_sector_start
- `GET  /em3d/status` — em3d_status
- `GET  /em3d/streamlines` — em3d_streamlines
- `POST /em3d/submodel` — em3d_submodel
- `GET  /em3d/vtp` — em3d_vtp
- `GET  /em3d/vtu` — em3d_vtu

## spraytest  (11)

- `POST /spraytest` — spraytest_start
- `POST /spraytest/abort` — spraytest_abort
- `POST /spraytest/beauty` — spraytest_beauty
- `POST /spraytest/favorites` — spraytest_favorites
- `POST /spraytest/favorites/<fid>/delete` — spraytest_favorite_delete
- `GET  /spraytest/round/<rid>` — spraytest_round
- `POST /spraytest/round/<rid>/delete` — spraytest_round_delete
- `POST /spraytest/round/<rid>/marked` — spraytest_round_marked
- `GET  /spraytest/rounds` — spraytest_rounds
- `GET  /spraytest/status` — spraytest_status
- `GET  /spraytest/video/<rid>/<vid>` — spraytest_video

## param_study  (7)

- `POST /param_study` — param_study_start
- `GET  /param_study/csv` — param_study_csv
- `POST /param_study/report` — param_study_report
- `GET  /param_study/report/download` — param_study_report_download
- `GET  /param_study/report/status` — param_study_report_status
- `GET  /param_study/status` — param_study_status
- `GET  /param_study/video` — param_study_video

## oilspray  (6)

- `POST /oilspray` — oilspray_start
- `POST /oilspray/abort` — oilspray_abort
- `POST /oilspray/presets` — oilspray_presets
- `POST /oilspray/presets/<pid>/delete` — oilspray_preset_delete
- `POST /oilspray/preview` — oilspray_preview
- `GET  /oilspray/status` — oilspray_status

## rag  (6)

- `POST /rag/add` — rag_add
- `POST /rag/delete` — rag_delete_many
- `POST /rag/delete/<doc_id>` — rag_delete
- `GET  /rag/list` — rag_list
- `GET  /rag/search` — rag_search
- `POST /rag/upload` — rag_upload

## jobs  (5)

- `GET  /jobs` — jobs_list
- `POST /jobs/<jid>/cancel` — jobs_cancel
- `POST /jobs/add` — jobs_add
- `POST /jobs/clear_done` — jobs_clear_done
- `POST /jobs/config` — jobs_config

## training  (5)

- `POST /training/design_rejected` — training_design_rejected
- `GET  /training/download` — training_download
- `GET  /training/stats` — training_stats
- `GET  /training/vlm/download` — training_vlm_download
- `POST /training/vlm/export` — training_vlm_export

## cfd  (4)

- `POST /cfd` — cfd_start
- `POST /cfd/abort` — cfd_abort
- `GET  /cfd/status` — cfd_status
- `GET  /cfd/vtp` — cfd_vtp

## variants  (4)

- `POST /variants/delete/<name>` — variants_delete
- `GET  /variants/list` — variants_list
- `GET  /variants/load/<name>` — variants_load
- `POST /variants/save` — variants_save

## compare  (3)

- `GET  /compare` — compare
- `POST /compare/report` — compare_report
- `GET  /compare/report/download` — compare_report_download

## ki_training  (3)

- `GET  /ki_training/chart` — ki_training_chart
- `GET  /ki_training/log/<name>` — ki_training_log
- `GET  /ki_training/runs` — ki_training_runs

## optimize  (3)

- `POST /optimize` — optimize_start
- `GET  /optimize/meta` — optimize_meta
- `GET  /optimize/status` — optimize_status

## session  (3)

- `POST /session/clear` — session_clear
- `GET  /session/load` — session_load
- `POST /session/save` — session_save

## cad_preview  (2)

- `POST /cad_preview` — cad_preview
- `GET  /cad_preview/status` — cad_preview_status

## design_ai  (2)

- `POST /design_ai` — design_ai_start
- `GET  /design_ai/status` — design_ai_status

## design_optimize  (2)

- `POST /design_optimize` — design_optimize_start
- `GET  /design_optimize/status` — design_optimize_status

## field  (2)

- `GET  /field/<int:n>` — field_frame
- `GET  /field/<mode>/<int:n>` — field_frame_mode

## import_step  (2)

- `POST /import_step` — import_step
- `GET  /import_step/status` — import_step_status

## smoke_test  (2)

- `POST /smoke_test` — smoke_test_run
- `GET  /smoke_test/status` — smoke_test_status

## (wurzel)  (1)

- `GET  /` — index

## analyse  (1)

- `POST /analyse` — analyse

## cad_image  (1)

- `GET  /cad_image/<path:name>` — cad_image

## chart  (1)

- `GET  /chart/<path:name>` — chart_image

## chat  (1)

- `POST /chat` — chat

## design_ai_ranged  (1)

- `POST /design_ai_ranged` — design_ai_ranged_start

## download_step  (1)

- `GET  /download_step` — download_step

## em3d_sweep  (1)

- `POST /em3d_sweep` — em3d_sweep_start

## export_step  (1)

- `GET  /export_step` — export_step

## file  (1)

- `GET  /file/<path:name>` — project_file

## import_bundle  (1)

- `POST /import_bundle` — import_bundle

## open_freecad  (1)

- `GET  /open_freecad` — open_freecad

## param_schema  (1)

- `GET  /param_schema` — param_schema

## preview_field  (1)

- `POST /preview_field` — preview_field

## projects  (1)

- `GET  /projects` — list_projects

## report  (1)

- `GET  /report/status` — report_status

## results  (1)

- `GET  /results` — results

## status  (1)

- `GET  /status` — status

## text2ema  (1)

- `POST /text2ema` — text2ema

## vendor  (1)

- `GET  /vendor/<path:name>` — vendor_file
