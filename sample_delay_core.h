// Original StemMIDI Sample Delay DSP core.
// Can be used by the standalone JUCE wrapper or the internal mixer bridge.
// No Logic Pro code, private binaries, or Apple assets are used.
#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <vector>

namespace stemmidi {
constexpr int kMaximumDelaySamples = 10000;

class SampleDelayCore {
public:
    SampleDelayCore()
        : history_(static_cast<size_t>(kMaximumDelaySamples + 1) * 2, 0.0f) {}

    void setLeft(int n) noexcept {
        left_.store(std::clamp(n, 0, kMaximumDelaySamples), std::memory_order_relaxed);
    }
    void setRight(int n) noexcept {
        right_.store(std::clamp(n, 0, kMaximumDelaySamples), std::memory_order_relaxed);
    }
    int left() const noexcept {return left_.load(std::memory_order_relaxed);}
    int right() const noexcept {return right_.load(std::memory_order_relaxed);}

    void reset() noexcept {
        std::fill(history_.begin(), history_.end(), 0.0f);
        write_ = 0;
    }

    // Stereo interleaved; input and output are permitted to alias.
    // No allocation, lock, interpreter call, or sample-rate conversion.
    void process(const float* in, float* out, int frames) noexcept {
        if (!in || !out || frames <= 0) return;
        const int delayL = left();
        const int delayR = right();
        constexpr int cap = kMaximumDelaySamples + 1;
        for (int i = 0; i < frames; ++i) {
            const float l = in[i * 2];
            const float r = in[i * 2 + 1];
            history_[static_cast<size_t>(write_) * 2] = l;
            history_[static_cast<size_t>(write_) * 2 + 1] = r;
            const int readL = (write_ + cap - delayL) % cap;
            const int readR = (write_ + cap - delayR) % cap;
            out[i * 2] = history_[static_cast<size_t>(readL) * 2];
            out[i * 2 + 1] = history_[static_cast<size_t>(readR) * 2 + 1];
            if (++write_ == cap) write_ = 0;
        }
    }
private:
    std::vector<float> history_;
    std::atomic<int> left_{0}, right_{0};
    int write_ = 0;
};
}  // namespace stemmidi
