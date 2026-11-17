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
static volatile sig_atomic_t g_stop=0;
static void stopHandler(int signum) { g_stop=1; }
static int writeAll(const void *data,size_t bytes) {
    const char *p=data; size_t left=bytes;
    while (left>0 && !g_stop) {
        ssize_t n=write(STDOUT_FILENO,p,left);
        if(n>0){left-=(size_t)n;p+=n;}
        else if(n<0 && errno==EINTR)continue;
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
int main(int argc,const char **argv) {
    @autoreleasepool {
        int sampleRate=(argc>1)?atoi(argv[1]):48000;
        if(sampleRate<8000 || sampleRate>192000)sampleRate=48000;
        if(argc>1 && strcmp(argv[1],"--permission")==0){
            BOOL allowed=CGPreflightScreenCaptureAccess();
            fprintf(stderr,"SCK_SCREEN_AUDIO_PERMISSION=%d\\n",(int)allowed);
            return allowed?0:4;
        }
        signal(SIGINT,stopHandler);signal(SIGTERM,stopHandler);signal(SIGPIPE,SIG_IGN);
        // No volver a pedir permisos en cada inicio. CGRequest... abre
        // Ajustes incluso si la captura de audio ya fue autorizada y la
        // identidad de un helper ad-hoc no coincide con la del proceso GUI.
        // Dejar que ScreenCaptureKit utilice la autorización existente.
        // Ante una denegación real, informar a la GUI; no abrir Ajustes.
        BOOL preflight=CGPreflightScreenCaptureAccess();
        fprintf(stderr,"SCK_HELPER_STARTED screen_preflight=%d; no_permission_request\n",
                (int)preflight);
        fflush(stderr);
        __block CaptureAudio *receiver=[[CaptureAudio alloc]init];
        __block BOOL setupCompleted=NO;
        [SCShareableContent getShareableContentExcludingDesktopWindows:NO
             onScreenWindowsOnly:NO completionHandler:^(SCShareableContent *content,NSError *error){
             if(error || content.displays.count==0){
                fprintf(stderr,"SCK_CONTENT_ERROR %s\n",[[error description] UTF8String]);
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
                 fprintf(stderr,"SCK_OUTPUT_ERROR %s\n",[[addError description] UTF8String]);
                 g_stop=1;setupCompleted=YES;return;
             }
             [stream startCaptureWithCompletionHandler:^(NSError *error){
                if(error){fprintf(stderr,"SCK_START_ERROR %s\n",[[error description] UTF8String]);g_stop=1;}
                else {fprintf(stderr,"SCK_STARTED_AUDIO_ONLY\n");}
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
        fflush(stderr);
        return receiver.framesSeen ? 0 : 3;
    }
}
