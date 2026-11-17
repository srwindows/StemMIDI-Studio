// StemMIDI Native CoreAudio Output - bridge C ABI, stable ABI for Python worker.
// The CoreAudio render thread runs ONLY C++; no Python, locks or heap allocation.
// One producer thread writes stereo interleaved float32. Up to 4 output channels.
// Copyright: StemMIDI Studio contributors.
#include <AudioUnit/AudioUnit.h>
#include <CoreAudio/CoreAudio.h>
#include <CoreFoundation/CoreFoundation.h>
#include <atomic>
#include <cstdint>
#include <cstring>
#include <vector>
#include <new>
#include <algorithm>
#include <cstdio>

struct StemOutput {
    AudioComponentInstance unit = nullptr;
    std::vector<float> pcm;
    uint64_t cap = 0;
    std::atomic<uint64_t> written{0}, read{0}, underruns{0};
    unsigned channels = 2;
    double rate = 48000.;
    bool started = false;
};
static AudioDeviceID resolve_device(const char* wanted) {
    if (!wanted || !wanted[0]) return kAudioObjectUnknown;
    AudioObjectPropertyAddress p = {kAudioHardwarePropertyDevices,
        kAudioObjectPropertyScopeGlobal,kAudioObjectPropertyElementMain};
    UInt32 bytes=0;
    if (AudioObjectGetPropertyDataSize(kAudioObjectSystemObject,&p,0,nullptr,&bytes)!=noErr)
        return kAudioObjectUnknown;
    std::vector<AudioDeviceID> ids(bytes/sizeof(AudioDeviceID));
    if (AudioObjectGetPropertyData(kAudioObjectSystemObject,&p,0,nullptr,&bytes,ids.data())!=noErr)
        return kAudioObjectUnknown;
    for (auto id : ids) {
        AudioObjectPropertyAddress np={kAudioObjectPropertyName,kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMain};
        CFStringRef value=nullptr;
        UInt32 size=sizeof(value);
        if (AudioObjectGetPropertyData(id,&np,0,nullptr,&size,&value)!=noErr || !value) continue;
        char label[512]={};
        CFStringGetCString(value,label,sizeof(label),kCFStringEncodingUTF8);
        CFRelease(value);
        if (std::strcmp(label,wanted)!=0) continue;
        // macOS often exposes two separate devices with the SAME label:
        // USB input-only and USB output. Only choose a genuine output.
        AudioObjectPropertyAddress cp={kAudioDevicePropertyStreamConfiguration,
            kAudioDevicePropertyScopeOutput,kAudioObjectPropertyElementMain};
        UInt32 cb=0;
        if (AudioObjectGetPropertyDataSize(id,&cp,0,nullptr,&cb)!=noErr || cb==0) continue;
        std::vector<unsigned char> storage(cb);
        if (AudioObjectGetPropertyData(id,&cp,0,nullptr,&cb,storage.data())!=noErr) continue;
        auto* list=reinterpret_cast<const AudioBufferList*>(storage.data());
        unsigned outputs=0;
        for(UInt32 j=0;j<list->mNumberBuffers;++j)
            outputs+=list->mBuffers[j].mNumberChannels;
        if(outputs>=2) return id;
    }
    return kAudioObjectUnknown;
}
static OSStatus render_cb(void* ctx,AudioUnitRenderActionFlags*,const AudioTimeStamp*,
    UInt32,UInt32 frames,AudioBufferList* io) {
    auto* s=static_cast<StemOutput*>(ctx);
    if (!io || !io->mNumberBuffers) return noErr;
    for (UInt32 j=0;j<io->mNumberBuffers;++j)
        if (io->mBuffers[j].mData) std::memset(io->mBuffers[j].mData,0,io->mBuffers[j].mDataByteSize);
    const uint64_t r=s->read.load(std::memory_order_relaxed);
    const uint64_t w=s->written.load(std::memory_order_acquire);
    uint64_t available=(w>=r ? w-r : 0);
    UInt32 take=static_cast<UInt32>(std::min<uint64_t>(available,frames));
    if (take<frames) s->underruns.fetch_add(1,std::memory_order_relaxed);
    // AudioBufferList may expose interleaved stereo/quad OR multiple
    // non-interleaved channel buffers. Honor mNumberChannels for every buffer.
    unsigned first_channel=0;
    for(UInt32 j=0;j<io->mNumberBuffers;++j) {
        const AudioBuffer& b=io->mBuffers[j];
        const unsigned nc=b.mNumberChannels;
        if(!nc||!b.mData) {first_channel+=nc;continue;}
        const uint64_t capacity=b.mDataByteSize/(sizeof(float)*nc);
        take=static_cast<UInt32>(std::min<uint64_t>(take,capacity));
        auto* dst=static_cast<float*>(b.mData);
        for(UInt32 i=0;i<take;++i) {
            const uint64_t pos=((r+i)%s->cap)*2;
            for(unsigned c=0;c<nc;++c) {
                const unsigned outch=first_channel+c;
                if(outch<2) dst[static_cast<size_t>(i)*nc+c]=s->pcm[pos+outch];
            }
        }
        first_channel+=nc;
    }
    s->read.store(r+take,std::memory_order_release);
    return noErr;
}
extern "C" {
void* stem_output_open(const char* dev_name, int rate,int channels,int ring_frames) {
    if (rate<8000||rate>192000||!(channels==2||channels==4)||ring_frames<2048) return nullptr;
    auto* s=new(std::nothrow) StemOutput;
    if (!s) return nullptr;
    s->channels=static_cast<unsigned>(channels);
    s->rate=static_cast<double>(rate);
    s->cap=static_cast<unsigned>(ring_frames);
    s->pcm.resize(s->cap*2);
    AudioComponentDescription desc={kAudioUnitType_Output,kAudioUnitSubType_HALOutput,
        kAudioUnitManufacturer_Apple,0,0};
    AudioComponent comp=AudioComponentFindNext(nullptr,&desc);
    if (!comp || AudioComponentInstanceNew(comp,&s->unit)!=noErr) {std::fprintf(stderr,"NATIVE_AU_ERROR component new\n");delete s;return nullptr;}
    UInt32 one=1,zero=0;
    {const OSStatus e=AudioUnitSetProperty(s->unit,kAudioOutputUnitProperty_EnableIO,
        kAudioUnitScope_Output,0,&one,sizeof(one));
     if(e!=noErr){std::fprintf(stderr,"NATIVE_AU_ERROR output-enable %d\n",(int)e);goto fail;}}
    {const OSStatus e=AudioUnitSetProperty(s->unit,kAudioOutputUnitProperty_EnableIO,
        kAudioUnitScope_Input,1,&zero,sizeof(zero));
     if(e!=noErr){std::fprintf(stderr,"NATIVE_AU_ERROR input-disable %d\n",(int)e);goto fail;}}
    {
        AudioDeviceID id=resolve_device(dev_name);
        if(id==kAudioObjectUnknown){std::fprintf(stderr,"NATIVE_AU_ERROR device not found: %s\n",dev_name?dev_name:"null");goto fail;}
        const OSStatus e=AudioUnitSetProperty(s->unit,kAudioOutputUnitProperty_CurrentDevice,
                kAudioUnitScope_Global,0,&id,sizeof(id));
        if(e!=noErr){std::fprintf(stderr,"NATIVE_AU_ERROR device-set %d\n",(int)e);goto fail;}
    }
    {
        AudioStreamBasicDescription fmt={};
        fmt.mSampleRate=static_cast<Float64>(rate);
        fmt.mFormatID=kAudioFormatLinearPCM;
        fmt.mFormatFlags=kAudioFormatFlagIsFloat|kAudioFormatFlagIsPacked;
        fmt.mFramesPerPacket=1;fmt.mChannelsPerFrame=channels;
        fmt.mBitsPerChannel=32;
        fmt.mBytesPerFrame=channels*sizeof(float);
        fmt.mBytesPerPacket=fmt.mBytesPerFrame;
        const OSStatus e=AudioUnitSetProperty(s->unit,kAudioUnitProperty_StreamFormat,
                kAudioUnitScope_Input,0,&fmt,sizeof(fmt));
        if(e!=noErr){std::fprintf(stderr,"NATIVE_AU_ERROR format %d\n",(int)e);goto fail;}
    }
    {
        AURenderCallbackStruct cb={render_cb,s};
        const OSStatus e=AudioUnitSetProperty(s->unit,kAudioUnitProperty_SetRenderCallback,
                kAudioUnitScope_Input,0,&cb,sizeof(cb));
        if(e!=noErr){std::fprintf(stderr,"NATIVE_AU_ERROR callback %d\n",(int)e);goto fail;}
    }
    {const OSStatus e=AudioUnitInitialize(s->unit);
     if(e!=noErr){std::fprintf(stderr,"NATIVE_AU_ERROR initialize %d\n",(int)e);goto fail;}}
    return s;
fail:
    if (s->unit) AudioComponentInstanceDispose(s->unit);
    delete s;
    return nullptr;
}
int stem_output_start(void* handle) {
    if(!handle) return -1;auto* s=static_cast<StemOutput*>(handle);
    if (s->started) return 0;
    OSStatus err=AudioOutputUnitStart(s->unit);
    if(err==noErr)s->started=true;
    return err;
}
void stem_output_stop(void* handle) {
    if(!handle)return;auto* s=static_cast<StemOutput*>(handle);
    if(s->started){AudioOutputUnitStop(s->unit);s->started=false;}
}
void stem_output_close(void* handle) {
    if(!handle)return;auto* s=static_cast<StemOutput*>(handle);
    stem_output_stop(handle);AudioUnitUninitialize(s->unit);
    AudioComponentInstanceDispose(s->unit);delete s;
}
int stem_output_write(void* handle,const float* pcm,int frames) {
    if(!handle||!pcm||frames<=0)return 0;
    auto* s=static_cast<StemOutput*>(handle);
    uint64_t w=s->written.load(std::memory_order_relaxed);
    uint64_t r=s->read.load(std::memory_order_acquire);
    if(w<r||static_cast<uint64_t>(frames)>s->cap-(w-r))return 0;
    for (int i=0;i<frames;++i) {
        uint64_t pos=((w+static_cast<uint64_t>(i))%s->cap)*2;
        s->pcm[pos]=pcm[i*2];s->pcm[pos+1]=pcm[i*2+1];
    }
    s->written.store(w+static_cast<uint64_t>(frames),std::memory_order_release);
    return frames;
}
int stem_output_buffered(void* handle) {
    if(!handle)return 0;
    auto* s=static_cast<StemOutput*>(handle);
    const auto w=s->written.load(std::memory_order_acquire);
    const auto r=s->read.load(std::memory_order_acquire);
    return static_cast<int>(w>=r ? std::min<uint64_t>(w-r,s->cap):0);
}
uint64_t stem_output_underruns(void* handle) {
    if(!handle)return 0;
    return static_cast<StemOutput*>(handle)->underruns.load(std::memory_order_relaxed);
}
double stem_output_device_latency_ms(void* handle) {
    if(!handle)return -1.;
    auto* s=static_cast<StemOutput*>(handle);
    AudioDeviceID id=kAudioObjectUnknown;UInt32 size=sizeof(id);
    if(AudioUnitGetProperty(s->unit,kAudioOutputUnitProperty_CurrentDevice,
          kAudioUnitScope_Global,0,&id,&size)!=noErr)return -1.;
    const AudioObjectPropertySelector props[]={
        kAudioDevicePropertyBufferFrameSize,
        kAudioDevicePropertySafetyOffset,
        kAudioDevicePropertyLatency};
    uint64_t frames=0;
    for(auto prop:props){
        AudioObjectPropertyAddress a={prop,kAudioDevicePropertyScopeOutput,
            kAudioObjectPropertyElementMain};
        UInt32 value=0;size=sizeof(value);
        if(AudioObjectGetPropertyData(id,&a,0,nullptr,&size,&value)==noErr)
            frames+=value;
    }
    return static_cast<double>(frames)*1000./s->rate;
}
double stem_output_unit_latency_ms(void* handle) {
    if(!handle)return -1;
    auto* s=static_cast<StemOutput*>(handle);
    Float64 seconds=0;UInt32 size=sizeof(seconds);
    if(AudioUnitGetProperty(s->unit,kAudioUnitProperty_Latency,kAudioUnitScope_Global,
        0,&seconds,&size)!=noErr)return -1;
    return seconds*1000.;
}
}
