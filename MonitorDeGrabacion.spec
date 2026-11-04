# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
ROOT=Path(SPECPATH).resolve()
a = Analysis(
    [str(ROOT/'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT/'assets'),'assets'),
        (str(ROOT/'composition_learned_model.json'),'.'),
        (str(ROOT/'modelos_publicos/multinstrumental_markov_v1.json'),
         'modelos_publicos'),
    ],
    hiddenimports=['compositor_session', 'compositor_render', 'compositor_tab', 'compositor_professional_layout', 'compositor_preview_shapes', 'compositor_meters', 'studio_vu_unified', 'home_vocal_studio', 'home_workspace', 'studio_shared_tabs', 'results_dragdrop', 'capture_eq', 'capture_live_listen', 'vocal_preset_catalog', 'composition_learned', 'composition_style_library', 'composition_registers', 'composition_ligatures', 'composition_pedal', 'composition_personal_learned', 'studio_home', 'studio_shell', 'home_tab_sync', 'project_transaction', 'project_progress', 'engine_task_indicator', 'result_file_details', 'global_midi_transport', 'midi_to_audio_card', 'midi_to_audio_expanded', 'midi_to_audio_engine_options', 'midi_render_instrument', 'midi_adsr_envelope', 'midi_compact_vu', 'midi_live_synth', 'midi_offline_render', 'soundfont_catalog', 'midi_gm_programs', 'midi_quant_render', 'home_fit_view', 'safe_file_delete', 'studio_paths', 'intro_video', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtSvg', 'native_capture', 'workspace_ui', 'midi_dialog', 'midi_factory_presets', 'piano_roll', 'separador', 'mezclador', 'task_staging', 'drum_module', 'audio_import_gui', 'audio_import', 'vocal_tune_module', 'file_dialogs', 'studio_file_browser', 'ui_polish', 'ui_hover_help', 'professional_help_content', 'recording_lab', 'recording_lab_engine', 'preview_player', 'help_center', 'drum_studio', 'drum_mixer_console', 'studio_slider_spin', 'studio_compact_ui', 'studio_workspace_cards', 'separation_compact_ui', 'separation_pro_controls', 'separation_dashboard_layout', 'separation_extended_ui', 'home_floating_cards', 'home_separation_expanded', 'home_other_expanded', 'studio_transport', 'playback_vu', 'home_record_review', 'dialog_guard', 'floating_transport', 'home_midi_browser', 'midi_stem_listen', 'live_stem_mixer', 'low_latency_stem_mixer', 'vocal_catalog', 'sounddevice', 'vocal_split_stems', 'model_registry', 'model_manager', 'project_flow', 'studio_settings_library', 'project_layout', 'project_status_dialog', 'export_dialog', 'project_session'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['torch', 'tensorflow', 'librosa', 'numba', 'scipy', 'basic_pitch', 'onnxruntime', 'torchvision'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MonitorDeGrabacion',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MonitorDeGrabacion',
)
