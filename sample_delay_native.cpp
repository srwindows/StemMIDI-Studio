// ABI estable del Sample Delay interno. DSP implementado en sample_delay_core.h.
#include "sample_delay_core.h"
#include <new>
extern "C" {
void* stem_sample_delay_create() noexcept {
    return new (std::nothrow) stemmidi::SampleDelayCore();
}
void stem_sample_delay_destroy(void* x) noexcept {
    delete static_cast<stemmidi::SampleDelayCore*>(x);
}
void stem_sample_delay_reset(void* x) noexcept {
    if (x) static_cast<stemmidi::SampleDelayCore*>(x)->reset();
}
void stem_sample_delay_set(void* x, int left, int right) noexcept {
    if (!x) return;
    auto* p = static_cast<stemmidi::SampleDelayCore*>(x);
    p->setLeft(left);
    p->setRight(right);
}
void stem_sample_delay_process(void* x, const float* input, float* output, int frames) noexcept {
    if (x) static_cast<stemmidi::SampleDelayCore*>(x)->process(input, output, frames);
}
}
