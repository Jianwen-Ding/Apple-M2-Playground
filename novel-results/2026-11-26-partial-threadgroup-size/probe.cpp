#include "harness.h"
#include <map>
static void run(uint32_t w, uint32_t h, uint32_t lx, uint32_t ly) {
    MTL::Buffer* slots = t::zeros(w * h * 32 + 64);
    MTL::Buffer* counter = t::zeros(4);
    t::dispatch(t::pipeline("probe.air", "probe"), {slots, counter}, MTL::Size(w, h, 1), MTL::Size(lx, ly, 1));
    uint32_t n = t::data<uint32_t>(counter)[0];
    printf("grid %ux%u local %ux%u: %u threads\n", w, h, lx, ly, n);
    std::map<std::pair<uint32_t,uint32_t>, int> seen;
    uint32_t* r = t::data<uint32_t>(slots);
    for (uint32_t i = 0; i < n; i++) {
        uint32_t* e = r + 8 * i;
        seen[{e[0], e[1]}]++;
        if (e[4] == (w - 1) / lx && e[5] == 0)
            printf("  partial group thread: gid (%u,%u) lid (%u,%u) grp (%u,%u) local_size (%u,%u)\n", e[0], e[1], e[2], e[3], e[4], e[5], e[6], e[7]);
    }
    int bad = 0;
    for (uint32_t y = 0; y < h; y++) for (uint32_t x = 0; x < w; x++) if (seen[{x, y}] != 1) bad++;
    printf("  positions not seen exactly once: %d\n", bad);
}
TEST(probe) { run(33, 17, 8, 8); run(10, 3, 4, 2); run(40, 3, 32, 2); }
TEST_MAIN
