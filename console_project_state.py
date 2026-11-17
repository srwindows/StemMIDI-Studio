"""Canonical single-manifest persistence of the professional console.

Both channel routing and BUS FX live in <project>.stemstudio.json, not in
independent settings files. Legacy sidecars are read only for migration.
"""
from __future__ import annotations
import json
from pathlib import Path

from PySide6.QtCore import Qt,QSignalBlocker
from studio_mixer_bus_fx import BUS_DEFAULT


def _console(main):
    dock=getattr(main,"mixer_professional",None)
    if dock is None or not getattr(dock.view,"is_pro_console",False):
        return None,None
    return dock.view,getattr(dock,"_mixer_tab_presentation",None)


def snapshot(main):
    view,pres=_console(main)
    if view is None or pres is None:
        return None
    sources={}
    selected=[]
    for key in sorted(view.selected):
        path=view.sources.get(key)
        if path is not None and Path(path).is_file():
            sources[str(key)]=str(Path(path).resolve())
            selected.append(str(Path(path).resolve()))
    assignments={}
    for channel,item in view.channels.items():
        path=view.sources.get(item["source"])
        if path is not None and Path(path).is_file():
            assignments[channel]=str(Path(path).resolve())
    # Include assignments not selected by checkbox, so they survive edits.
    for channel,key in view.manual_assignments.items():
        path=view.sources.get(key)
        if path is not None and Path(path).is_file():
            assignments[channel]=str(Path(path).resolve())
    all_sources=list(dict.fromkeys([*selected,*assignments.values()]))
    channels={}
    for key,item in view.channels.items():
        strip=item["strip"]
        channels[key]={
            "controls":dict(strip.controls),
            # These are the native whole-channel states. In the professional
            # mixer the visible M/S buttons target the selected dry/FX path,
            # whose FOUR independent flags are stored under bus_fx routes.
            # Never leak a path-only Mute into the global channel snapshot.
            "mute":bool(view.checked_mutes.get(key,False)),
            "solo":bool(strip.controls.get("solo",False)),
            "arm":bool(strip.arm.isChecked()),
        }
    fx=pres.bus_fx.config_snapshot()
    fx.update({
        "version":3,
        "bus_count":pres.bus_count,
        "bus_levels":{str(k):float(v) for k,v in
                      view.transport.live._bus_levels.items()},
    })
    return {
        "version":3,
        "source_files":all_sources,
        "selected_files":selected,
        "assignments":assignments,
        "channels":channels,
        "midi_instruments":view.midi_instrument_snapshot(),
        "midi_soundfonts":view.midi_soundfont_snapshot(),
        "preview_midi_instruments":view.preview_midi_snapshot(),
        "master_pct":int(view.home.master_volume.value()),
        "selected_bus":int(view.bus_select.currentData() or 1),
        "inspected_channel":str(view.inspected_key or ""),
        "routing_page":int(view.routing_page),
        "bus_bank":int(pres._bus_bank.currentData() or 0),
        "bus_fx":fx,
    }


def legacy_snapshot(project):
    """Read older presets without changing or adding files."""
    project=Path(project)
    old=project/"presets"/"mezclador_buses_tab.json"
    if old.is_file():
        try:
            data=json.loads(old.read_text(encoding="utf-8"))
            if isinstance(data,dict) and data.get("version") in (1,2):
                return {"version":2,"bus_fx":data}
        except (OSError,ValueError,TypeError):
            pass
    return None


def restore(main,data):
    """Rebuild UI and DSP state AFTER the new project's catalog is loaded."""
    if not isinstance(data,dict) or data.get("version") not in (2,3):
        return False
    view,pres=_console(main)
    if view is None or pres is None:
        return False
    # The old callback/decoder must not retain its previous project.
    if view.transport is not None and view.transport.live.running:
        view.transport.live.stop()

    # Capture source choices as absolute paths, not transient catalog indices.
    paths=[Path(x).expanduser() for x in data.get("source_files",[])
           if isinstance(x,str) and Path(x).is_file()]
    chosen=[str(Path(x).resolve()) for x in data.get("selected_files",[])
            if isinstance(x,str) and Path(x).is_file()]
    assignments={}
    for channel,name in data.get("assignments",{}).items():
        if (channel in view.channels and isinstance(name,str)
                and Path(name).is_file()):
            assignments[channel]=str(Path(name).resolve())

    view.refresh_catalog(force=True)
    for path in paths:
        key=str(path.resolve())
        view.sources[key]=path.resolve()
        if key not in view._catalog():
            view.manual_sources[key]=path.resolve()
    view._known_auto_files.update(str(path.resolve()) for path in paths)
    # Strictly reproduce selected sources, not "all auto-detected" defaults.
    if data.get("version")==3:
        view.selected=set(chosen)
        view.manual_assignments=dict(assignments)
    else:
        view.manual_assignments={}

    channel_settings=data.get("channels",{})
    if isinstance(channel_settings,dict):
        for key,row in channel_settings.items():
            if not isinstance(row,dict) or key not in view.channels:
                continue
            controls=row.get("controls")
            if isinstance(controls,dict):
                from console_audio_engine import DEFAULT_CHANNEL
                view.control_state[key]={
                    **DEFAULT_CHANNEL,
                    **{p:v for p,v in controls.items() if p in DEFAULT_CHANNEL}}
            view.checked_mutes[key]=bool(row.get("mute",False))
    view._sync_channels(remember=False)
    for key,item in view.channels.items():
        row=channel_settings.get(key,{}) if isinstance(channel_settings,dict) else {}
        if not isinstance(row,dict):
            continue
        with QSignalBlocker(item["mute"]):
            item["mute"].setChecked(bool(row.get("mute",False)))
        with QSignalBlocker(item["solo"]):
            item["solo"].setChecked(bool(row.get("solo",False)))
        with QSignalBlocker(item["record"]):
            item["record"].setChecked(bool(row.get("arm",False)))
    view.apply_midi_soundfonts(data.get("midi_soundfonts",{}))
    view.apply_midi_instruments(data.get("midi_instruments",{}))
    view.restore_preview_midi_snapshot(data.get("preview_midi_instruments",{}))
    if view.transport:
        view._apply_live_controls()

    # Load everything from the single manifest. Restore is idempotent and
    # clears DSP/plugins for the previous project before building the new set.
    bus=data.get("bus_fx",{})
    if isinstance(bus,dict):
        pres.load_project_bus_state(bus)
    view.home.master_volume.setValue(
        max(0,min(100,int(data.get("master_pct",100)))))
    selected_bus=int(data.get("selected_bus",1))
    select=view.bus_select.findData(selected_bus)
    if select>=0:
        with QSignalBlocker(view.bus_select):
            view.bus_select.setCurrentIndex(select)
    view._bus_changed()
    if pres.active:
        pres._update_bus_inspector()
    inspected=data.get("inspected_channel")
    if inspected in view.channels:
        view.select_channel(inspected)
    page=int(data.get("routing_page",0))
    if 0<=page<max(1,(len(view.visible_strips)+15)//16):
        view.routing_page=page
    bank=int(data.get("bus_bank",0))
    idx=pres._bus_bank.findData(bank)
    if idx>=0:
        pres._bus_bank.setCurrentIndex(idx)
    if hasattr(view,"_refresh_file_checks"):
        view._refresh_file_checks()
    if hasattr(view,"_update_available_files"):
        view._update_available_files()
    if hasattr(view,"_sync_wave_sources"):
        view._sync_wave_sources()
    return True
