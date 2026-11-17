"""Transferencia local de rasgos tímbricos y expresivos entre voces autorizadas.

Procesamiento DSP, NO clonación de identidad mediante redes neuronales.
No modifica el original ni ejecuta pesos externos. Resultados aproximados;
requiere una pista vocal solista limpia para cada fuente.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d
from scipy.signal import stft, istft

PARAM_RANGES={
    "similarity":(0,100), "timbre":(0,100),
    "pitch":(-12,12), "formants":(-8,8),
    "resonance":(0,100), "brightness":(-100,100),
    "dynamics":(0,100), "articulation":(0,100),
    "air":(0,100), "rasp":(0,100),
    "vibrato":(0,100), "stereo":(0,200)
}

def _envelope(samples,sample_rate,nfft=2048,hop=512):
    """Espectro suavizado medio de regiones con voz, sin copiar muestras."""
    audio=np.asarray(samples[:min(len(samples),sample_rate*28)],dtype=np.float32)
    if len(audio)<nfft:raise ValueError("La voz de referencia es demasiado corta.")
    _,_,frames=stft(audio,fs=sample_rate,nperseg=nfft,
        noverlap=nfft-hop,boundary="zeros")
    mag=np.abs(frames)
    rms=np.sqrt(np.mean(mag*mag,axis=0))
    good=rms>max(np.max(rms)*.045,1e-7)
    if np.count_nonzero(good)<4:
        raise ValueError("La voz tiene demasiados silencios para analizar su timbre.")
    spectrum=np.mean(mag[:,good],axis=1)
    return gaussian_filter1d(np.log(np.maximum(spectrum,1e-8)),9)

def _curve(mono,sr):
    """Envolvente de amplitud temporal suavizada a aproximadamente 50 Hz."""
    block=max(1,round(sr*.020))
    pad=(-len(mono))%block
    padded=np.pad(mono,(0,pad))
    rms=np.sqrt(np.mean(padded.reshape(-1,block).astype(np.float64)**2,
                        axis=1)+1e-10)
    return gaussian_filter1d(rms,2.8)

def _vibrato_mod(samples,sr,depth):
    if depth<=0:return samples
    # Modulación periódica de unos 0..25 cents alrededor de la altura actual.
    n=len(samples)
    t=np.arange(n,dtype=np.float64)/sr
    f=5.1
    cents=25.*depth/100.
    tau=(cents*np.log(2)/1200.)/(2*np.pi*f)
    indices=np.arange(n,dtype=np.float64)+sr*tau*np.sin(2*np.pi*f*t)
    return np.interp(indices,np.arange(n),samples).astype(np.float32)

def _tone_channel(samples,sr,ratio_curve,params,ref_curve):
    nfft=2048; hop=512
    _,_,frames=stft(samples,fs=sr,nperseg=nfft,
        noverlap=nfft-hop,boundary="zeros")
    spectral_gain=np.exp(ratio_curve).astype(np.float32)
    if frames.shape[0]!=len(spectral_gain):
        raise ValueError("Espectro de procesamiento incompatible.")
    frames*=spectral_gain[:,None]
    _,result=istft(frames,fs=sr,nperseg=nfft,
        noverlap=nfft-hop,input_onesided=True,boundary=True)
    result=np.asarray(result[:len(samples)],dtype=np.float32)
    if len(result)!=len(samples):
        result=np.pad(result,(0,len(samples)-len(result)))
    amount=float(params["dynamics"])/100.
    articulation=float(params["articulation"])/100.
    if amount or articulation:
        src=_curve(result,sr)
        levels=np.maximum(np.median(src[src>1e-5]) if np.any(src>1e-5) else .01,1e-5)
        if amount:
            # La referencia suministra solo dinámica relativa, nunca fragmentos.
            target=np.interp(np.linspace(0,len(ref_curve)-1,len(src)),
                             np.arange(len(ref_curve)),ref_curve)
            median=np.median(target[target>1e-5]) if np.any(target>1e-5) else 1.
            target=np.maximum(target/max(median,1e-5),.1)
            target=np.clip(target,.6,1.6)
            gain=np.power(target,amount*.65)
        else:gain=np.ones_like(src)
        if articulation:
            change=np.gradient(np.log(np.maximum(src,1e-5)))
            gain*=np.clip(1+change*articulation*9,.70,1.30)
        gain=gaussian_filter1d(gain,2)
        result*=np.interp(np.arange(len(result))/max(1,sr*.020),
                          np.arange(len(gain)),gain,right=gain[-1])
    rasp=float(params["rasp"])/100.
    if rasp:
        saturated=np.tanh(result*(1.7+rasp*4))/(1.7+rasp*4)
        result=(1-.65*rasp)*result+.65*rasp*saturated
    if params["vibrato"]:
        result=_vibrato_mod(result,sr,float(params["vibrato"]))
    return result

def spectral_profile(source,reference,sr,params):
    """Crea una ganancia espectral acotada de transformación tímbrica."""
    nfft=2048
    original=_envelope(source,sr,nfft)
    model=_envelope(reference,sr,nfft)
    frequencies=np.fft.rfftfreq(nfft,d=1/sr)
    semitones=float(params["formants"])
    if semitones:
        factor=2**(semitones/12)
        model=np.interp(frequencies/factor,frequencies,model,
                        left=model[0],right=model[-1])
    broad=gaussian_filter1d(model-original,19)
    fine=gaussian_filter1d(model-original,5)-broad
    similarity=float(params["similarity"])/100.
    timbre=float(params["timbre"])/100.
    transform=similarity*(broad+fine*timbre)*.85
    # Desplazamiento de formantes propio, incluso sin similaridad de referencia.
    if semitones:
        shifted=np.interp(frequencies/(2**(semitones/12)),frequencies,
                          original,left=original[0],right=original[-1])
        transform+=.5*(shifted-original)
    resonance=float(params["resonance"])/100.
    if resonance:
        formant_peaks=gaussian_filter1d(model,5)-gaussian_filter1d(model,30)
        transform+=formant_peaks*.8*resonance
    bright=float(params["brightness"])/100.
    if bright:
        tilt=np.clip(np.log2(np.maximum(frequencies,85)/1350),-3,2.8)
        transform+=np.log(10)/20 * bright * 2.8 * tilt
    airy=float(params["air"])/100.
    if airy:
        shelf=np.clip((frequencies-3100)/4100,0,1)
        transform+=np.log(10)/20*airy*7.5*shelf
    transform=np.clip(transform,-np.log(4.0),np.log(4.0))
    transform[0]=0.
    return transform

def convert(source,reference,target,**params):
    from vocal_tune_engine import decode
    values={k:float(params.get(k,(lo+hi)/2)) for k,(lo,hi) in PARAM_RANGES.items()}
    for k,(lo,hi) in PARAM_RANGES.items():
        if not lo<=values[k]<=hi or not np.isfinite(values[k]):
            raise ValueError("Valor fuera de rango: "+k)
    a=Path(source).expanduser().resolve()
    b=Path(reference).expanduser().resolve()
    dest=Path(target).expanduser().resolve()
    if not a.is_file() or not b.is_file() or a==b:
        raise ValueError("Selecciona dos archivos de voz distintos.")
    if dest in (a,b) or dest.exists():
        raise ValueError("No se pueden sobrescribir voces o resultados anteriores.")
    print("ETAPA Decodificando pista vocal y referencia autorizada…",flush=True)
    source_audio,sr=decode(a)
    ref,ref_sr=decode(b)
    if source_audio.shape[1]/sr>5*60:
        raise ValueError("El procesamiento admite hasta cinco minutos por toma.")
    if ref.shape[1]/ref_sr>5*60:
        raise ValueError("La referencia supera cinco minutos.")
    original=source_audio.T.astype(np.float32)
    sample_ref=np.mean(ref,axis=0)
    if sr!=ref_sr:
        from scipy.signal import resample_poly
        from math import gcd
        divisor=gcd(sr,ref_sr)
        sample_ref=resample_poly(sample_ref,sr//divisor,ref_sr//divisor).astype(np.float32)
    sample_src=np.mean(original,axis=1)
    if max(np.max(np.abs(sample_src)),np.max(np.abs(sample_ref)))<.002:
        raise ValueError("No hay señal vocal suficiente.")
    print("ETAPA Analizando envolventes de timbre y dinámica…",flush=True)
    shape=spectral_profile(sample_src,sample_ref,sr,values)
    reference_curve=_curve(sample_ref,sr)
    print("ETAPA Aplicando color vocal y expresividad sin copiar voz original…",flush=True)
    processed=np.stack([_tone_channel(original[:,i],sr,shape,values,reference_curve)
                        for i in range(original.shape[1])],axis=1)
    # El desplazamiento de tono usa phase vocoder, preservando duración.
    if values["pitch"]:
        import librosa
        for ch in range(processed.shape[1]):
            processed[:,ch]=librosa.effects.pitch_shift(
                processed[:,ch],sr=sr,n_steps=values["pitch"])
    if processed.shape[1]==2 and values["stereo"]!=100:
        mid=(processed[:,0]+processed[:,1])*.5
        side=(processed[:,0]-processed[:,1])*.5*(values["stereo"]/100.)
        processed[:,0]=mid+side
        processed[:,1]=mid-side
    if not np.all(np.isfinite(processed)):
        raise ValueError("El DSP produjo muestras no finitas.")
    peak=np.max(np.abs(processed))
    if peak>.985:processed*=.985/peak
    dest.parent.mkdir(parents=True,exist_ok=True)
    sf.write(str(dest),processed,sr,format="FLAC",subtype="PCM_24")
    if dest.stat().st_size<1000:raise RuntimeError("FLAC de salida incompleto.")
    print("RESULTADO "+json.dumps({
        "method":"spectral_timbre_transfer_not_neural_cloning",
        "sample_rate":sr,"channels":processed.shape[1],
        "seconds":round(len(processed)/sr,2),
        "parameters":values},ensure_ascii=False),flush=True)
    return dest

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",required=True)
    parser.add_argument("--reference",required=True)
    parser.add_argument("--output",required=True)
    for key,(lo,hi) in PARAM_RANGES.items():
        parser.add_argument("--"+key.replace("_","-"),type=float,
                            default=(lo+hi)/2)
    options=vars(parser.parse_args(argv))
    source=options.pop("source");reference=options.pop("reference")
    target=options.pop("output")
    convert(source,reference,target,**options)

if __name__=="__main__":
    try:main()
    except Exception as error:
        print("ERROR VOCAL: "+str(error),file=sys.stderr,flush=True)
        sys.exit(1)
