// Captura de audio de salida de macOS con ScreenCaptureKit.
// Salida: PCM float32 LE intercalado 48000 Hz, estéreo, por stdout.
// Diagnósticos exclusivamente por stderr; no modifica la salida de audio.
#import <Foundation/Foundation.h>
#import <ScreenCaptureKit/ScreenCaptureKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <CoreMedia/CoreMedia.h>
#import <AudioToolbox/AudioToolbox.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
// Nombre de la salida CoreAudio sin inspeccionar entradas ni solicitar
// acceso al micrófono. Solo se usa para etiquetar la ruta de YouTube.
const char *stemmidi_system_output_name(void) {
    static char name[256]="salida actual de macOS";
    AudioObjectID output=0;
    AudioObjectPropertyAddress address={
        kAudioHardwarePropertyDefaultOutputDevice,
        kAudioObjectPropertyScopeGlobal,
        kAudioObjectPropertyElementMain
    };
    UInt32 size=sizeof(output);
    if(AudioObjectGetPropertyData(kAudioObjectSystemObject,&address,
            0,NULL,&size,&output)!=noErr || output==0)return name;
    address.mSelector=kAudioObjectPropertyName;
    CFStringRef description=NULL;
    size=sizeof(description);
    if(AudioObjectGetPropertyData(output,&address,0,NULL,&size,
                                  &description)==noErr && description!=NULL){
        CFStringGetCString(description,name,sizeof(name),kCFStringEncodingUTF8);
        CFRelease(description);
    }
    return name;
}

/* Enumerar las entradas físicas mediante propiedades de CoreAudio sin
   crear ningún AudioUnit, stream de entrada ni conexión de micrófono.
   Devuelve JSON simple para el desplegable del Monitor. */
const char *stemmidi_input_devices_json(void) {
    static char jsonBuf[8192]="[]";
    @autoreleasepool {
        AudioObjectPropertyAddress addr={
            kAudioHardwarePropertyDevices,
            kAudioObjectPropertyScopeGlobal,
            kAudioObjectPropertyElementMain};
        UInt32 bytes=0;
        OSStatus err=AudioObjectGetPropertyDataSize(kAudioObjectSystemObject,
                                                   &addr,0,NULL,&bytes);
        if(err!=noErr || bytes<sizeof(AudioDeviceID))return jsonBuf;
        AudioDeviceID *devices=malloc(bytes);
        if(!devices)return jsonBuf;
        err=AudioObjectGetPropertyData(kAudioObjectSystemObject,&addr,0,NULL,
                                       &bytes,devices);
        if(err!=noErr){free(devices);return jsonBuf;}
        NSMutableArray *found=[NSMutableArray array];
        size_t n=bytes/sizeof(AudioDeviceID);
        for(size_t i=0;i<n;i++) {
            AudioObjectPropertyAddress input={
                kAudioDevicePropertyStreamConfiguration,
                kAudioObjectPropertyScopeInput,
                kAudioObjectPropertyElementMain};
            UInt32 listSize=0;
            if(AudioObjectGetPropertyDataSize(devices[i],&input,0,NULL,
                                              &listSize)!=noErr ||
                listSize<sizeof(AudioBufferList))continue;
            AudioBufferList *buffers=malloc(listSize);
            if(!buffers)continue;
            UInt32 capacity=listSize;
            UInt32 channels=0;
            if(AudioObjectGetPropertyData(devices[i],&input,0,NULL,
                                          &capacity,buffers)==noErr){
                for(UInt32 j=0;j<buffers->mNumberBuffers;j++)
                    channels+=buffers->mBuffers[j].mNumberChannels;
            }
            free(buffers);
            if(!channels)continue;
            AudioObjectPropertyAddress desc={
                kAudioObjectPropertyName,
                kAudioObjectPropertyScopeGlobal,
                kAudioObjectPropertyElementMain};
            CFStringRef cfname=NULL;
            UInt32 length=sizeof(cfname);
            if(AudioObjectGetPropertyData(devices[i],&desc,0,NULL,
                                          &length,&cfname)!=noErr ||
                cfname==NULL)continue;
            NSString *name=(__bridge_transfer NSString *)cfname;
            if(name.length)
                [found addObject:@{@"name":name,@"channels":@(channels)}];
        }
        free(devices);
        NSData *encoded=[NSJSONSerialization dataWithJSONObject:found
                                                        options:0 error:NULL];
        if(encoded && encoded.length<sizeof(jsonBuf)){
            memcpy(jsonBuf,encoded.bytes,encoded.length);
            jsonBuf[encoded.length]='\0';
        }
    }
    return jsonBuf;
}

static volatile sig_atomic_t g_stop=0;
static int g_output_fd=1;
static char g_last_error[1024]={0};
const char *stemmidi_sck_last_error(void) {return g_last_error;}
// Consulta de permiso TCC sin solicitarlo ni abrir Ajustes.
int stemmidi_sck_permission_granted(void) {
    return CGPreflightScreenCaptureAccess() ? 1 : 0;
}
static void sck_diag(const char *format,...) {
    @autoreleasepool {
        NSString *base=[NSHomeDirectory() stringByAppendingPathComponent:@"Library/Logs/StemMIDI Studio"];
        [[NSFileManager defaultManager] createDirectoryAtPath:base
            withIntermediateDirectories:YES attributes:nil error:NULL];
        NSString *path=[base stringByAppendingPathComponent:@"captura_sistema.log"];
        FILE *f=fopen(path.fileSystemRepresentation,"a");
        if(!f)return;
        fprintf(f,"%s | ",[[NSDate date].description UTF8String]);
        va_list args;
        va_start(args,format);
        vfprintf(f,format,args);
        va_end(args);
        fprintf(f,"\n");
        fclose(f);
    }
}
static void stopHandler(int signum) { g_stop=1; }
static int writeAll(const void *data,size_t bytes) {
    const char *p=data; size_t left=bytes;
    while (left>0 && !g_stop) {
        ssize_t n=write(g_output_fd,p,left);
        if(n>0){left-=(size_t)n;p+=n;}
        else if(n<0 && errno==EINTR)continue;
        else if(n<0 && (errno==EAGAIN || errno==EWOULDBLOCK)) {
            usleep(2500);
            continue;
        }
        else {g_stop=1;return 0;}
    }
    return left==0;
}
@interface CaptureAudio : NSObject <SCStreamOutput,SCStreamDelegate>
@property(nonatomic,strong) SCStream *stream;
@property(nonatomic,assign) unsigned long long framesSeen;
@property(nonatomic,assign) double sumSq;
@property(nonatomic,assign) float peak;
@property(nonatomic,assign) BOOL formatLogged;
@end
@implementation CaptureAudio
- (void)stream:(SCStream *)stream didOutputSampleBuffer:(CMSampleBufferRef)sb ofType:(SCStreamOutputType)type {
    if(type!=SCStreamOutputTypeAudio || g_stop || !CMSampleBufferDataIsReady(sb))return;
    CMFormatDescriptionRef fmt=CMSampleBufferGetFormatDescription(sb);
    if(!fmt)return;
    const AudioStreamBasicDescription *asbd=CMAudioFormatDescriptionGetStreamBasicDescription(fmt);
    if(!asbd || asbd->mFormatID!=kAudioFormatLinearPCM ||
       !(asbd->mFormatFlags & kAudioFormatFlagIsFloat) ||
       asbd->mBitsPerChannel!=32) {
        if(!self.formatLogged){fprintf(stderr,"SCK_BAD_FORMAT id=%u bits=%u flags=%u\n",
          asbd?asbd->mFormatID:0,asbd?asbd->mBitsPerChannel:0,
          asbd?asbd->mFormatFlags:0);self.formatLogged=YES;}
        return;
    }
    if(!self.formatLogged) {
        fprintf(stderr,"SCK_FORMAT sample_rate=%.0f channels=%u flags=%u bytesPerFrame=%u\n",
          asbd->mSampleRate,asbd->mChannelsPerFrame,asbd->mFormatFlags,asbd->mBytesPerFrame);
        fflush(stderr);self.formatLogged=YES;
    }
    size_t needed=0;
    CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sb,&needed,NULL,0,
           NULL,NULL,0,NULL);
    if(needed<sizeof(AudioBufferList))needed=sizeof(AudioBufferList);
    AudioBufferList *list=malloc(needed);
    if(!list)return;
    CMBlockBufferRef block=NULL;
    OSStatus status=CMSampleBufferGetAudioBufferListWithRetainedBlockBuffer(sb,
        NULL,list,needed,NULL,NULL,
        kCMSampleBufferFlag_AudioBufferList_Assure16ByteAlignment,&block);
    if(status!=noErr){fprintf(stderr,"SCK_BUFFER_ERROR %d\n",(int)status);free(list);return;}
    CMItemCount n=CMSampleBufferGetNumSamples(sb);
    if(n<=0){if(block)CFRelease(block);free(list);return;}
    const int count=(int)n;
    float *interleaved=malloc((size_t)count*2*sizeof(float));
    if(!interleaved){if(block)CFRelease(block);free(list);return;}
    BOOL planar=(asbd->mFormatFlags & kAudioFormatFlagIsNonInterleaved)!=0;
    if(planar && list->mNumberBuffers>=2) {
        const float *left=list->mBuffers[0].mData;
        const float *right=list->mBuffers[1].mData;
        if(left&&right){
            for(int i=0;i<count;i++){interleaved[2*i]=left[i];interleaved[2*i+1]=right[i];}
        }else { free(interleaved);if(block)CFRelease(block);free(list);return;}
    } else if(list->mNumberBuffers>=1 && list->mBuffers[0].mData) {
        const float *src=list->mBuffers[0].mData;
        if(asbd->mChannelsPerFrame>=2 && list->mBuffers[0].mDataByteSize>=count*2*sizeof(float)){
            memcpy(interleaved,src,(size_t)count*2*sizeof(float));
        }else if(asbd->mChannelsPerFrame==1 && list->mBuffers[0].mDataByteSize>=count*sizeof(float)) {
            for(int i=0;i<count;i++){interleaved[i*2]=src[i];interleaved[i*2+1]=src[i];}
        }else {
            free(interleaved);if(block)CFRelease(block);free(list);return;
        }
    }else{free(interleaved);if(block)CFRelease(block);free(list);return;}
    for(int i=0;i<count*2;i++){
       float v=interleaved[i];
       if(isfinite(v)){
           float mag=fabsf(v);if(mag>self.peak)self.peak=mag;
           self.sumSq+=(double)v*v;
       }
    }
    self.framesSeen+=(unsigned long long)count;
    if(self.framesSeen>=48000 && self.framesSeen%(48000*2)<(unsigned long long)count){
       double rms=sqrt(self.sumSq/(double)(self.framesSeen*2));
       fprintf(stderr,"SCK_AUDIO frames=%llu peak=%.5f rms=%.6f\n",
           self.framesSeen,self.peak,rms);fflush(stderr);
       sck_diag("audio recibido: %llu frames, peak=%.5f rms=%.6f",
           self.framesSeen,self.peak,rms);
    }
    writeAll(interleaved,(size_t)count*2*sizeof(float));
    free(interleaved);
    if(block)CFRelease(block);
    free(list);
}
- (void)stream:(SCStream *)stream didStopWithError:(NSError *)error {
    fprintf(stderr,"SCK_STOPPED %s\n",[[error description] UTF8String]);fflush(stderr);
    g_stop=1;
}
@end
int stemmidi_sck_run(int sampleRate,int output_fd) {
    @autoreleasepool {
        g_stop=0;g_output_fd=output_fd;g_last_error[0]=0;
        if(sampleRate<8000 || sampleRate>192000)sampleRate=48000;

        // No volver a pedir permisos en cada inicio. CGRequest... abre
        // Ajustes incluso si la captura de audio ya fue autorizada y la
        // identidad de un helper ad-hoc no coincide con la del proceso GUI.
        // Dejar que ScreenCaptureKit utilice la autorización existente.
        // Ante una denegación real, informar a la GUI; no abrir Ajustes.
        BOOL preflight=CGPreflightScreenCaptureAccess();
        fprintf(stderr,"SCK_IN_PROCESS_STARTED screen_preflight=%d; no_permission_request\n",
                (int)preflight);
        sck_diag("inicio dentro de la app: permiso previo=%d; sin solicitud automática",(int)preflight);
        fflush(stderr);
        __block CaptureAudio *receiver=[[CaptureAudio alloc]init];
        __block BOOL setupCompleted=NO;
        [SCShareableContent getShareableContentExcludingDesktopWindows:NO
             onScreenWindowsOnly:NO completionHandler:^(SCShareableContent *content,NSError *error){
             if(error || content.displays.count==0){
                snprintf(g_last_error,sizeof(g_last_error),"ScreenCaptureKit: acceso o contenido rechazado: %s",[[error description] UTF8String] ?: "sin pantallas");
                fprintf(stderr,"SCK_CONTENT_ERROR %s\n",g_last_error);
                sck_diag("ERROR contenido: %s",g_last_error);
                g_stop=1;setupCompleted=YES;return;
             }
             SCDisplay *display=content.displays.firstObject;
             SCContentFilter *filter=[[SCContentFilter alloc] initWithDisplay:display excludingWindows:@[]];
             SCStreamConfiguration *config=[[SCStreamConfiguration alloc]init];
             config.capturesAudio=YES;
             config.excludesCurrentProcessAudio=YES;
             config.sampleRate=sampleRate;
             config.channelCount=2;
             config.width=2;
             config.height=2;
             config.showsCursor=NO;
             SCStream *stream=[[SCStream alloc]initWithFilter:filter configuration:config delegate:receiver];
             receiver.stream=stream;
             NSError *addError=nil;
             BOOL added=[stream addStreamOutput:receiver type:SCStreamOutputTypeAudio
                               sampleHandlerQueue:dispatch_queue_create("stemmidi.sck.audio",DISPATCH_QUEUE_SERIAL)
                                           error:&addError];
             if(!added){
                 snprintf(g_last_error,sizeof(g_last_error),"ScreenCaptureKit output: %s",[[addError description] UTF8String] ?: "sin datos");
                 fprintf(stderr,"SCK_OUTPUT_ERROR %s\n",g_last_error);
                 sck_diag("ERROR salida: %s",g_last_error);
                 g_stop=1;setupCompleted=YES;return;
             }
             [stream startCaptureWithCompletionHandler:^(NSError *error){
                if(error){
                    snprintf(g_last_error,sizeof(g_last_error),"ScreenCaptureKit inicio: %s",[[error description] UTF8String]);
                    fprintf(stderr,"SCK_START_ERROR %s\n",g_last_error);
                    sck_diag("ERROR inicio: %s",g_last_error);g_stop=1;
                }
                else {fprintf(stderr,"SCK_STARTED_AUDIO_ONLY\n");
                      sck_diag("captura de audio iniciada");}
                fflush(stderr);setupCompleted=YES;
             }];
        }];
        while(!g_stop){
            @autoreleasepool{
                [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.1]];
            }
        }
        if(receiver.stream){
            [receiver.stream stopCaptureWithCompletionHandler:^(NSError *error){}];
        }
        fprintf(stderr,"SCK_HELPER_EXIT frames=%llu peak=%.5f\n",receiver.framesSeen,receiver.peak);
        sck_diag("captura detenida: %llu frames, peak=%.5f",receiver.framesSeen,receiver.peak);
        fflush(stderr);
        return receiver.framesSeen ? 0 : 3;
    }
}

void stemmidi_sck_stop(void) {g_stop=1;}
