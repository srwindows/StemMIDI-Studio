#!/usr/bin/env python3
"""DSP: bypass, 48k/16k/mono/estéreo, protección de originales y errores."""
import os,sys,tempfile,hashlib,subprocess,wave
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(R))
from recording_lab_engine import DEFAULT,validated,command,probe_audio,filter_chain

def read(path):
    return np.frombuffer(subprocess.run(["ffmpeg","-v","error","-i",str(path),
        "-f","f32le","-ac","1","-ar","16000","pipe:1"],
        capture_output=True,check=True,timeout=15).stdout,dtype="<f4")

with tempfile.TemporaryDirectory(prefix="stemmidi_engine_lab_quality_") as td:
 base=Path(td)
 for sr,channels in ((16000,1),(48000,2)):
    t=np.arange(sr*2)/sr
    a=(.14*np.sin(2*np.pi*320*t)+.027*np.sin(2*np.pi*1900*t)+
       np.random.default_rng(3).normal(0,.005,len(t)))
    samples=np.tile(a[:,None],(1,channels))
    p=base/f"entrada_{sr}_{channels}.wav"
    with wave.open(str(p),"wb") as f:
        f.setnchannels(channels);f.setsampwidth(2);f.setframerate(sr)
        f.writeframes((np.clip(samples,-1,1)*30000).astype("<i2").tobytes())
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    settings=dict(DEFAULT,highpass=0,limiter=False)
    out=base/f"sin_efecto_{sr}.flac"
    proc=subprocess.run(command(p,out,settings),capture_output=True,timeout=35)
    assert proc.returncode==0,proc.stderr[-500:]
    assert probe_audio(out)==(sr,channels),(sr,probe_audio(out))
    diff=float(np.max(np.abs(read(p)-read(out))))
    assert diff<.00008,("BY_PASS modifies source",sr,diff)
    print("BY_PASS_FILTER_NONE_SR_CHANNEL_PRESERVED",sr,channels,round(diff,7),flush=True)
    processed=base/f"procesado_{sr}.flac"
    strong=dict(DEFAULT,denoise=10,declick=True,gate_enabled=True,
        lowpass_enabled=True,lowpass=7500,comp_enabled=True,
        comp_threshold=-25,comp_ratio=4,deesser=40,
        bass=2,lowmid=-4,highmid=3,treble=2,limiter=True,
        loudnorm_enabled=True,target_lufs=-16,stereo_width=110,output_gain=2)
    result=subprocess.run(command(p,processed,strong),
                          capture_output=True,timeout=35)
    assert result.returncode==0,result.stderr[-600:]
    assert probe_audio(processed)==(sr,channels),(sr,probe_audio(processed))
    difference=float(np.sqrt(np.mean((read(processed)-read(p))**2)))
    assert difference>.001,difference
    assert hashlib.sha256(p.read_bytes()).hexdigest()==digest
    print("ALL_FX_REAL_OUTPUT_STEREO_MONO_PROTECTED",sr,channels,round(difference,5),flush=True)
    try:command(p,p,settings)
    except ValueError:pass
    else:raise AssertionError("self-overwriting allowed")
    try:command(p,out,settings)
    except ValueError:pass
    else:raise AssertionError("existing destination allowed")
    try:validated(dict(DEFAULT,denoise=1000))
    except ValueError:pass
    else:raise AssertionError("invalid bounds not stopped")
print("PRO_AUDIO_LAB_DSP_CONTRACT_PASS",flush=True)
