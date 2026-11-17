// StemMIDI Channel EQ: original eight-band stereo biquad DSP.
// Functional design references the public Channel EQ control layout.
// No Logic Pro binary, algorithm or visual assets copied.
#include <array>
#include <atomic>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <new>
#include <cstring>

namespace {
constexpr int kBands=8, kStages=4, kChannels=2;
constexpr double kPi=3.1415926535897932384626433832795;
struct Coeff {double b0=1,b1=0,b2=0,a1=0,a2=0;};
struct State {double z1=0,z2=0;};
enum Type {HP,LOWSHELF,PEAK,HIGHSHELF,LP};
constexpr int types[kBands]={HP,LOWSHELF,PEAK,PEAK,PEAK,PEAK,HIGHSHELF,LP};
constexpr double freqs[kBands]={35,90,250,700,2000,5500,9500,17500};
struct Band {
  std::atomic<double> hz{1000}, gain{0}, q{0.707};
  std::atomic<int> slope{12}, enabled{1};
};
struct Equalizer {
  std::array<Band,kBands> bands;
  Coeff coeff[kBands][kStages];
  State state[kBands][kStages][kChannels];
  int stages[kBands]={};
  std::atomic<double> outgain{0};
  std::atomic<int> mode{0};
  std::atomic<int> high_quality{0};
  double previous[kChannels]={};
  int applied_quality=0;
  std::atomic<unsigned> generation{1};
  unsigned current=0;
  double rate=48000;
  Equalizer() {
    for(int i=0;i<kBands;i++){
      bands[i].hz.store(freqs[i]);
      if(i==0||i==7)bands[i].enabled.store(0);
    }
  }
};
Coeff biquad(int type,double f,double g,double q,double rate) {
  f=std::clamp(f,10.0,rate*0.475);
  q=std::clamp(q,0.1,100.0);
  const double w=2*kPi*f/rate, sn=sin(w), cs=cos(w), alpha=sn/(2*q);
  const double A=pow(10.0,g/40.0);
  double b0=1,b1=0,b2=0,a0=1,a1=0,a2=0;
  if(type==PEAK){
    b0=1+alpha*A; b1=-2*cs; b2=1-alpha*A;
    a0=1+alpha/A; a1=-2*cs; a2=1-alpha/A;
  } else if(type==HP) {
    b0=(1+cs)/2; b1=-(1+cs); b2=b0;
    a0=1+alpha; a1=-2*cs; a2=1-alpha;
  } else if(type==LP) {
    b0=(1-cs)/2; b1=1-cs; b2=b0;
    a0=1+alpha; a1=-2*cs; a2=1-alpha;
  } else {
    const double shelfAlpha=sn*sqrt(2.0)/2.0, two=2*sqrt(A)*shelfAlpha;
    if(type==LOWSHELF) {
      b0=A*((A+1)-(A-1)*cs+two); b1=2*A*((A-1)-(A+1)*cs);
      b2=A*((A+1)-(A-1)*cs-two);
      a0=(A+1)+(A-1)*cs+two; a1=-2*((A-1)+(A+1)*cs);
      a2=(A+1)+(A-1)*cs-two;
    } else {
      b0=A*((A+1)+(A-1)*cs+two); b1=-2*A*((A-1)+(A+1)*cs);
      b2=A*((A+1)+(A-1)*cs-two);
      a0=(A+1)-(A-1)*cs+two; a1=2*((A-1)-(A+1)*cs);
      a2=(A+1)-(A-1)*cs-two;
    }
  }
  return {b0/a0,b1/a0,b2/a0,a1/a0,a2/a0};
}
Coeff first_order(int type,double f,double rate) {
  const double k=tan(kPi*std::clamp(f,10.,rate*.475)/rate);
  const double denominator=1.+k;
  const double b0=(type==HP?1.:k)/denominator;
  return {b0, (type==HP?-b0:b0),0.,(k-1.)/denominator,0.};
}
inline double run(double x,const Coeff& c,State& st) {
  const double y=c.b0*x+st.z1;
  st.z1=c.b1*x-c.a1*y+st.z2;
  st.z2=c.b2*x-c.a2*y;
  // Prevent denormal floating point CPU penalties.
  if(std::abs(st.z1)<1e-24)st.z1=0;
  if(std::abs(st.z2)<1e-24)st.z2=0;
  return y;
}
void refresh(Equalizer& eq) {
  const unsigned revision=eq.generation.load(std::memory_order_acquire);
  if(revision==eq.current)return;
  const int hq=eq.high_quality.load(std::memory_order_relaxed);
  if(hq!=eq.applied_quality) {
    std::memset(eq.state,0,sizeof(eq.state));
    std::fill(eq.previous,eq.previous+kChannels,0.);
    eq.applied_quality=hq;
  }
  const double internal_rate=eq.rate*(hq?2:1);
  for(int b=0;b<kBands;b++){
    const Band& p=eq.bands[b];
    const double f=p.hz.load(std::memory_order_relaxed);
    const double g=p.gain.load(std::memory_order_relaxed);
    const double user_q=p.q.load(std::memory_order_relaxed);
    int count=1;
    if(types[b]==HP||types[b]==LP){
      // 6/12/18/24/36/48 dB per octave, actual 1-8 pole cascades.
      const int poles=std::clamp(
          p.slope.load(std::memory_order_relaxed)/6,1,8);
      const int biquads=poles/2;
      count=biquads+(poles%2);
      for(int k=0;k<biquads;k++) {
        // Butterworth pole pairing; user Q controls resonance from flat.
        const double butterworth_q=1./(2.*sin(
            kPi*(2.*k+1.)/(2.*poles)));
        eq.coeff[b][k]=biquad(types[b],f,g,
            butterworth_q*(user_q/.7071067811865476),internal_rate);
      }
      if(poles%2)
        eq.coeff[b][biquads]=first_order(types[b],f,internal_rate);
    } else {
      eq.coeff[b][0]=biquad(types[b],f,g,user_q,internal_rate);
    }
    eq.stages[b]=p.enabled.load(std::memory_order_relaxed)?count:0;
  }
  eq.current=revision;
}}
extern "C" {
void* stem_eq_create(int samplerate) noexcept {
  if(samplerate<8000||samplerate>192000)return nullptr;
  auto* eq=new(std::nothrow) Equalizer;
  if(eq)eq->rate=samplerate;
  return eq;
}
void stem_eq_destroy(void* ptr) noexcept {delete static_cast<Equalizer*>(ptr);}
void stem_eq_reset(void* ptr) noexcept {
  if(!ptr)return;
  auto* eq=static_cast<Equalizer*>(ptr);
  std::memset(eq->state,0,sizeof(eq->state));
  std::fill(eq->previous,eq->previous+kChannels,0.);
}
int stem_eq_set_band(void* ptr,int band,int enabled,double hz,double gain,double q,int slope) noexcept {
  if(!ptr||band<0||band>=kBands)return 0;
  auto* eq=static_cast<Equalizer*>(ptr);
  auto& p=eq->bands[band];
  p.hz.store(std::clamp(hz,20.,std::min(20000.,eq->rate*.475)),std::memory_order_relaxed);
  p.gain.store(std::clamp(gain,-24.,24.),std::memory_order_relaxed);
  p.q.store(std::clamp(q,.1,100.),std::memory_order_relaxed);
  const int slopes[]={6,12,18,24,36,48};
  const auto choice=std::min_element(std::begin(slopes),std::end(slopes),
      [slope](int a,int b){return std::abs(a-slope)<std::abs(b-slope);});
  p.slope.store(*choice,std::memory_order_relaxed);
  p.enabled.store(enabled?1:0,std::memory_order_relaxed);
  eq->generation.fetch_add(1,std::memory_order_release);
  return 1;
}
void stem_eq_set_gain(void* ptr,double gain) noexcept {
  if(!ptr)return;
  static_cast<Equalizer*>(ptr)->outgain.store(std::clamp(gain,-24.,24.));
}
void stem_eq_set_mode(void* ptr,int mode) noexcept {
  if(!ptr)return;
  static_cast<Equalizer*>(ptr)->mode.store(std::clamp(mode,0,4));
}
void stem_eq_set_hq(void* ptr,int enabled) noexcept {
  if(!ptr)return;
  auto& eq=*static_cast<Equalizer*>(ptr);
  eq.high_quality.store(enabled?1:0,std::memory_order_relaxed);
  eq.generation.fetch_add(1,std::memory_order_release);
}
void stem_eq_process(void* ptr,const float* input,float* output,int frames) noexcept {
  if(!ptr||!input||!output||frames<=0)return;
  auto& eq=*static_cast<Equalizer*>(ptr);
  refresh(eq);
  const int mode=eq.mode.load(std::memory_order_relaxed);
  const double gain=pow(10.,eq.outgain.load(std::memory_order_relaxed)/20.);
  for(int i=0;i<frames;i++){
    const double a=input[static_cast<size_t>(i)*2], b=input[static_cast<size_t>(i)*2+1];
    double l=a,r=b;
    if(mode==3||mode==4){l=(a+b)*.5;r=(a-b)*.5;}
    for(int ch=0;ch<2;ch++){
      if(mode==1&&ch==1)continue;
      if(mode==2&&ch==0)continue;
      if(mode==3&&ch==1)continue;
      if(mode==4&&ch==0)continue;
      const double raw=(ch==0?l:r);
      const int factor=eq.applied_quality?2:1;
      double x=raw;
      for(int sub=0;sub<factor;sub++){
        x=(factor==2&&sub==0)?(eq.previous[ch]+raw)*.5:raw;
        for(int band=0;band<kBands;band++)
          for(int k=0;k<eq.stages[band];k++)
            x=run(x,eq.coeff[band][k],eq.state[band][k][ch]);
      }
      eq.previous[ch]=raw;
      if(ch==0)l=x;else r=x;
    }
    if(mode==3||mode==4){
      output[static_cast<size_t>(i)*2]=static_cast<float>((l+r)*gain);
      output[static_cast<size_t>(i)*2+1]=static_cast<float>((l-r)*gain);
    }else{
      output[static_cast<size_t>(i)*2]=static_cast<float>(l*gain);
      output[static_cast<size_t>(i)*2+1]=static_cast<float>(r*gain);
    }
  }
}
}
