"""DSP real de entrada/monitor: capturas f32le, filtros FIR y salida WAV."""
from __future__ import annotations
import hashlib,math,os,subprocess,sys,tempfile,time,wave
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from audio_engine import CaptureWorker,recorded_seconds
from capture_eq import StereoCaptureEQ

sample_rate=48000
frames=48000
timeline=np.arange(frames,dtype=np.float64)/sample_rate

def stereo_at(frequency,amplitude=.12):
    sine=(amplitude*np.sin(2*np.pi*frequency*timeline)).astype("<f4")
    return np.column_stack((sine,sine)).astype("<f4")

def run_eq(frames,settings,block=2048):
    fx=StereoCaptureEQ(sample_rate)
    return np.concatenate([fx.process(frames[n:n+block],True,*settings)
                           for n in range(0,len(frames),block)])

def ratio_db(after,before):
    def rms(a):
        return np.sqrt(np.mean(np.square(a[3000:,0].astype(np.float64))))
    return 20*np.log10(rms(after)/rms(before))

# Bypass exacto, sin alterar los datos originales y todos los canales.
sample=stereo_at(1220)
fx=StereoCaptureEQ(sample_rate)
assert np.array_equal(fx.process(sample),sample)
assert np.array_equal(fx.process(sample,True,0,0,0),sample)
print("FLAT_EQ_BIT_EXACT_BYPASS_PASS",flush=True)

# Graves, medios, agudos han de afectar solamente a su zona real de frecuencia.
low=stereo_at(120)
mid=stereo_at(1200)
high=stereo_at(6500)
print("ACTUAL_RESPONSE_DB",flush=True)
for signal,boost,unrelated,expected in (
    (low,(12,0,0),(0,0,9),7.5),
    (mid,(0,6,0),(12,0,0),4.5),
    (high,(0,0,9),(12,0,0),5.5),
):
    actual=ratio_db(run_eq(signal,boost),signal)
    ignored=ratio_db(run_eq(signal,unrelated),signal)
    print(boost,"BOOST",round(actual,2),"OFF_BAND",round(ignored,2),flush=True)
    assert actual>=expected,(boost,actual)
    assert abs(ignored)<1.,(boost,unrelated,ignored)
assert ratio_db(run_eq(low,(-12,0,0)),low)<-6
print("REAL_SPECTRAL_EQ_ALL_THREE_BANDS_AND_ATTENUATION_PASS",flush=True)

# Continuidad de un seno que atraviesa muchos bloques pequeños.
fx=StereoCaptureEQ(sample_rate)
dense=run_eq(stereo_at(1200),(0,7,0),block=2048)
tiny=np.concatenate([fx.process(mid[n:n+237],True,0,7,0)
                     for n in range(0,len(mid),237)])
assert len(dense)==len(tiny)
assert np.max(np.abs(dense-tiny))<1.e-5
print("STREAMING_EQ_BLOCK_INDEPENDENCE_AND_STEREO_PASS",flush=True)

worker=CaptureWorker("Prueba sin abrir PipeWire",sample_rate=sample_rate)
worker.set_input_controls(-6,25)
worker.set_input_eq(True,12,0,0)
pcm=low[:2048].tobytes()
processed=worker._processed_chunk(pcm)
assert len(processed)==len(pcm) and processed!=pcm
assert worker._eq_settings==(True,12,0,0)
assert worker._gain_db==-6 and worker._balance==25
assert len(np.frombuffer(processed,dtype="<f4"))==4096
worker.set_input_eq(False,12,0,0)
worker.set_input_controls(0,0)
assert worker._processed_chunk(pcm)==pcm
print("CAPTURE_ENGINE_LIVE_GAIN_BALANCE_EQ_AND_BYPASS_PASS",flush=True)

# El camino PCM de grabación genera audio real en disco sin hardware:
# inyectamos los mismos chunks sobre la salida FFmpeg, no creamos datos falsos.
with tempfile.TemporaryDirectory(prefix="stemmidi_capture_eq_export_") as temp:
    source=Path(temp)/"original.raw"
    source.write_bytes(mid.tobytes())
    original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    output=Path(temp)/"procesado.wav"
    worker=CaptureWorker("sistema-desconectado",sample_rate=sample_rate)
    worker.set_input_controls(-3,0)
    worker.set_input_eq(True,0,9,0)
    worker._open_encoder(str(output),"WAV (PCM 24 bits · estudio)")
    for n in range(0,len(mid),2048):
        raw=mid[n:n+2048].tobytes()
        encoded=worker._processed_chunk(raw)
        worker._rec.stdin.write(encoded)
        worker._rec_bytes+=len(encoded)
    assert abs(recorded_seconds(worker._rec_bytes,sample_rate)-1.)<.001
    worker._close_encoder()
    assert output.is_file() and output.stat().st_size>140000
    probe=subprocess.run(
        ["ffprobe","-v","error","-select_streams","a:0",
         "-show_entries","stream=codec_name,sample_rate,channels,bits_per_raw_sample",
         "-of","default=noprint_wrappers=1",str(output)],
        capture_output=True,text=True,timeout=12,check=True)
    assert "pcm_s24le" in probe.stdout,probe.stdout
    assert "48000" in probe.stdout and "channels=2" in probe.stdout
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
    print("CAPTURE_EQ_REAL_WAV_24BIT_ENCODE_AND_ORIGINAL_NOT_CHANGED_PASS",flush=True)
print("CAPTURE_EQ_AUDIO_REGRESSIONS_ALL_PASS",flush=True)
