# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import os
ROOT=Path(SPECPATH).resolve()
INTRO_FILE=ROOT/'intro'/'StemMIDI_Intro_Definitiva.mp4'
if not INTRO_FILE.is_file():
    raise SystemExit('ERROR: Falta el video aprobado de la intro; no generar paquete incompleto')
NATIVE_ROOT=Path(os.environ.get('STEMMIDI_MAC_NATIVE_ROOT',
                               str(ROOT.parent/'native'))).expanduser().resolve()
NATIVE_BIN=NATIVE_ROOT/'bin'
NATIVE_LIB=NATIVE_ROOT/'lib'
NATIVE_CMDS=('ffmpeg','ffprobe','ffplay','fluidsynth')
missing=[str(NATIVE_BIN/name) for name in NATIVE_CMDS
         if not (NATIVE_BIN/name).is_file()]
if not NATIVE_LIB.is_dir():
    missing.append(str(NATIVE_LIB))
if missing:
    raise SystemExit('ERROR: faltan dependencias nativas macOS: '+', '.join(missing))
# Los trabajadores Python se ejecutan con entorno_ia/bin/python, NO con
# el binario congelado de PyInstaller. Solo se incluyen fuentes .py, nunca
# modelos, canciones, grabaciones ni datos de entrenamiento privados.
WORKER_SOURCES=[(str(path),'workers') for path in ROOT.glob('*.py')
                if path.name!='macos_runtime_hook.py']
NATIVE_DATA=[(str(NATIVE_BIN/name),'vendor/native/bin')
             for name in NATIVE_CMDS]
NATIVE_DATA.append((str(NATIVE_LIB),'vendor/native/lib'))
NATIVE_DATA.append((str(ROOT/'libstemmidi_coreaudio.dylib'),'vendor/native/lib'))
NATIVE_DATA.append((str(ROOT/'libstemmidi_sample_delay.dylib'),'vendor/native/lib'))
NATIVE_DATA.append((str(ROOT/'libstemmidi_channel_eq.dylib'),'vendor/native/lib'))
# sdl2-compat carga SDL3 con dlopen(@executable_path/libSDL3.dylib).
# FFplay necesita encontrar esta biblioteca también junto al ejecutable.
SDL3_LOADER=NATIVE_LIB/'libSDL3.dylib'
if not SDL3_LOADER.is_file():
    raise SystemExit('ERROR: falta SDL3 requerida por ffplay: '+str(SDL3_LOADER))
NATIVE_DATA.append((str(SDL3_LOADER),'vendor/native/bin'))
# Captura del audio de macOS vía ScreenCaptureKit: evita depender de
# BlackHole o de que General MIDI devuelva el sonido de YouTube por USB.
SCK_AUDIO_CAPTURE=NATIVE_BIN/'stemmidi-system-audio'
if not SCK_AUDIO_CAPTURE.is_file():
    raise SystemExit('ERROR: falta motor ScreenCaptureKit: '+str(SCK_AUDIO_CAPTURE))
NATIVE_DATA.append((str(SCK_AUDIO_CAPTURE),'vendor/native/bin'))
# La captura principal se realiza dentro del proceso StemMIDI, que es
# titular de los permisos TCC. El helper independiente era otra identidad.
SCK_LIBRARY=NATIVE_LIB/'libstemmidi-capture.dylib'
if not SCK_LIBRARY.is_file():
    raise SystemExit('ERROR: falta la biblioteca ScreenCaptureKit integrada: '+str(SCK_LIBRARY))
PORTABLE_ROOT=Path(os.environ.get('STEMMIDI_MAC_PORTABLE_ROOT',
                                  str(ROOT.parent/'portable_resources'))).expanduser().resolve()
IA_RUNTIME=PORTABLE_ROOT/'ia_runtime'
AI_PYTHON=IA_RUNTIME/'python311'/'bin'/'python3.11'
AI_CLI=IA_RUNTIME/'bin'/'audio-separator'
AI_MODELS=PORTABLE_ROOT/'ai_models'
SOUNDFONT=PORTABLE_ROOT/'soundfonts'/'FluidR3_GM.sf2'
SOUNDFONT_LICENSE=PORTABLE_ROOT/'soundfonts'/'FluidR3_GM_LICENSE.txt'
BUNDLED_MODELS=('htdemucs.yaml','955717e8-8726e21a.th','download_checks.json','catalogo_audio_separator.json')
# Perfil LOCAL autónomo: incorpora todos los modelos libres descargados para
# verificación en este Mac. NO se activa en paquetes públicos ni en GitHub:
# cada autor externo mantiene sus condiciones de redistribución.
LOCAL_FULL_MODELS=os.environ.get('STEMMIDI_MAC_BUNDLE_ALL_MODELS')=='1'
LOCAL_MODEL_ROOT=Path(os.environ.get('STEMMIDI_MAC_MODEL_ROOT',
    str(Path.home()/'Library/Application Support/StemMIDI Studio/modelos'))).expanduser().resolve()
LOCAL_BUNDLED_MODELS={
 '':('htdemucs_6s.yaml','5c90dfd2-34c22ccb.th',
     'htdemucs_ft.yaml','04573f0d-f3cf25b2.th','92cfc3b6-ef3bcb9c.th',
     'd12395a8-e57c48e6.th','f7e0c4bc-ba3fe64a.th',
     'UVR-MDX-NET-Inst_HQ_3.onnx',
     'model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt',
     'model_mel_band_roformer_ep_3005_sdr_11.4360.yaml'),
 'voces':('mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt',
          'mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956_config.yaml',
          'bs_roformer_male_female_by_aufr33_sdr_7.2889.ckpt',
          'config_chorus_male_female_bs_roformer.yaml'),
 'bateria':('aufr33-jarredou_DrumSep_model_mdx23c_ep_141_sdr_10.8059.ckpt',
           'aufr33-jarredou_DrumSep_model_mdx23c_ep_141_sdr_10.8059.yaml'),
}

missing=[str(p) for p in (AI_PYTHON,AI_CLI,IA_RUNTIME/'bin'/'python-ia',SOUNDFONT,SOUNDFONT_LICENSE)
         if not p.is_file()]
missing += [str(AI_MODELS/name) for name in BUNDLED_MODELS
            if not (AI_MODELS/name).is_file()]
if missing:
    raise SystemExit('ERROR: distribución autónoma incompleta: '+', '.join(missing))
# Se incluyen los paquetes de IA y modelos públicos; nunca las bibliotecas
# personales, archivos MIDI/KAR ni los 59 ritmos privados del usuario.
LOCAL_MODEL_DATA=[]
if LOCAL_FULL_MODELS:
    for group,names in LOCAL_BUNDLED_MODELS.items():
        for name in names:
            path=LOCAL_MODEL_ROOT/group/name
            minimum=1024 if path.suffix.lower() in ('.ckpt','.th','.onnx','.pth') else 1
            if not path.is_file() or path.stat().st_size<minimum:
                raise SystemExit('ERROR: modelo local incompleto: '+str(path))
            LOCAL_MODEL_DATA.append((str(path),
                'ai_models/'+group if group else 'ai_models'))
PORTABLE_DATA=[
    (str(IA_RUNTIME),'ia_runtime'),
    (str(AI_MODELS),'ai_models'),
    *LOCAL_MODEL_DATA,
    (str(SOUNDFONT),'soundfonts'),
    (str(SOUNDFONT_LICENSE),'licenses'),
    (str(PORTABLE_ROOT/'licenses'/'mdxnet-infer-MIT.txt'),'licenses'),
    (str(PORTABLE_ROOT/'THIRD_PARTY_NOTICES.txt'),'.'),
]
a = Analysis(
    [str(ROOT/'main.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        *NATIVE_DATA,
        *PORTABLE_DATA,
        *WORKER_SOURCES,
        (str(ROOT/'assets'),'assets'),
        (str(INTRO_FILE),'intro'),
        (str(ROOT/'LICENSE'),'.'),
        (str(ROOT/'README.md'),'.'),
        (str(ROOT/'composition_learned_model.json'),'.'),
        (str(ROOT/'modelos_publicos/multinstrumental_markov_v1.json'),
         'modelos_publicos'),
    ],
    hiddenimports=['stemmidi_channel_eq','channel_eq_controls','stemmidi_sample_delay','sample_delay_controls','native_coreaudio_stream','studio_mixer_tab_presentation','studio_mixer_bus_fx','studio_mixer_bus_ui','studio_mixer_channel_ui','pedalboard','pedalboard._pedalboard','soundcard','psutil','mutagen','pydub','audioop','PySide6.QtNetwork','PySide6.QtSvgWidgets','scipy.signal','scipy.ndimage','compositor_session', 'compositor_render', 'compositor_tab', 'compositor_professional_layout', 'compositor_preview_shapes', 'compositor_meters', 'studio_vu_unified', 'home_vocal_studio', 'home_workspace', 'studio_shared_tabs', 'results_dragdrop', 'capture_eq', 'capture_live_listen', 'vocal_preset_catalog', 'composition_learned', 'composition_style_library', 'composition_registers', 'composition_ligatures', 'composition_pedal', 'composition_personal_learned', 'studio_home', 'studio_shell', 'home_tab_sync', 'project_transaction', 'project_progress', 'engine_task_indicator', 'result_file_details', 'global_midi_transport', 'midi_to_audio_card', 'midi_to_audio_expanded', 'midi_to_audio_engine_options', 'midi_render_instrument', 'midi_adsr_envelope', 'midi_compact_vu', 'midi_live_synth', 'midi_offline_render', 'soundfont_catalog', 'midi_gm_programs', 'midi_quant_render', 'home_fit_view', 'safe_file_delete', 'studio_paths', 'intro_video', 'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtSvg', 'native_capture', 'workspace_ui', 'midi_dialog', 'midi_factory_presets', 'piano_roll', 'separador', 'mezclador', 'task_staging', 'drum_module', 'drum_expert_controls', 'drum_flat_workspace', 'midi_compact_workspace', 'drum_complete_workspace', 'drum_custom_models', 'audio_import_gui', 'audio_import', 'vocal_tune_module', 'file_dialogs', 'studio_file_browser', 'ui_polish', 'ui_hover_help', 'professional_help_content', 'recording_lab', 'recording_lab_engine', 'preview_player', 'help_center', 'drum_studio', 'drum_mixer_console', 'studio_slider_spin', 'studio_compact_ui', 'studio_workspace_cards', 'separation_compact_ui', 'separation_pro_controls', 'separation_dashboard_layout', 'separation_extended_ui', 'separation_sketch_layout', 'separation_advanced_tab', 'separation_final_layout', 'separation_engine_parameters', 'separation_professional_params', 'advanced_tab_parity', 'home_floating_cards', 'home_separation_expanded', 'home_other_expanded', 'studio_transport', 'playback_vu', 'home_record_review', 'dialog_guard', 'floating_transport', 'home_midi_browser', 'midi_stem_listen', 'live_stem_mixer', 'low_latency_stem_mixer', 'vocal_catalog', 'sounddevice', 'vocal_split_stems', 'model_registry', 'model_manager', 'external_model_import', 'project_flow', 'studio_settings_library', 'project_layout', 'project_status_dialog', 'export_dialog', 'project_session'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT/'macos_runtime_hook.py')],
    excludes=['torch', 'tensorflow', 'librosa', 'numba', 'basic_pitch', 'onnxruntime', 'torchvision'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='StemMIDIStudio',
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
    name='StemMIDIStudio',
)

app = BUNDLE(
    coll,
    name='StemMIDI Studio.app',
    icon=str(ROOT/'assets'/'stemmidi_icon.icns'),
    bundle_identifier='com.srwindows.stemmidi-studio',
    info_plist={
        'CFBundleShortVersionString': '1.1.0',
        'CFBundleVersion': '1.1.0',
        'LSMinimumSystemVersion': '14.0',
        'NSMicrophoneUsageDescription': 'StemMIDI Studio necesita acceso a las entradas de audio para monitorizar y grabar cuando usted lo solicite.',
        'NSScreenCaptureUsageDescription': 'StemMIDI Studio captura el audio de salida de macOS, por ejemplo YouTube reproduciéndose por interfaz MIDI USB, solo cuando activa Monitor o Grabar.',
        'NSHighResolutionCapable': True,
    },
)
