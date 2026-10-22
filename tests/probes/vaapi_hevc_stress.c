#define _POSIX_C_SOURCE 200809L
/* Synthetic full-HD encoding with frequent real rate reconfigurations.
 * No desktop capture, Wine prefix or user application is accessed. */
#include "native_vaapi_encoder.h"
#include "native_nvenc_reference_config.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
static uint64_t now_ns(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) abort();
    return (uint64_t)t.tv_sec * 1000000000ull + t.tv_nsec;
}
int main(int argc, char **argv)
{
    CHECK(argc == 2 || (argc == 3 && !strcmp(argv[2], "h264")));
    int hevc = argc == 2;
    const unsigned width = 1920, height = 1080, count = 1200;
    unsigned char *pixels = malloc((size_t)width * height * 3 / 2);
    CHECK(pixels);
    NV_ENC_CONFIG preset = {.version = NV_ENC_CONFIG_VER}, config;
    NV_ENC_INITIALIZE_PARAMS init;
    uurb_nvenc_reference_config(&preset, width, height, hevc, 15000000, &config, &init);
    config.rcParams.enableAQ = 1;
    struct uurb_encoder *s = uurb_vaapi_open(NULL, &init); CHECK(s);
    FILE *out = fopen(argv[1], "wb"); CHECK(out);
    unsigned reconfigurations = 0;
    uint64_t encode_ns = 0, encode_max_ns = 0, reconfigure_ns = 0;
    for (unsigned i = 0; i < count; ++i) {
        for (unsigned y = 0; y < height; ++y)
            for (unsigned x = 0; x < width; ++x)
                pixels[(size_t)y * width + x] = 32 + (((x + i * 13) / 48 + (y + i * 7) / 48) & 1) * 180;
        memset(pixels + width * height, 96 + i % 64, width * height / 2);
        int changed = i && !(i % 24);
        if (changed) {
            unsigned phase = i / 24;
            config.rcParams.averageBitRate = config.rcParams.maxBitRate = phase & 1 ? 12000000 : 15000000;
            config.rcParams.vbvBufferSize = config.rcParams.vbvInitialDelay = config.rcParams.averageBitRate / (6 + phase % 4);
            init.frameRateNum = phase & 1 ? 45 : 60;
            NV_ENC_RECONFIGURE_PARAMS p = {.version = NV_ENC_RECONFIGURE_PARAMS_VER,
                .reInitEncodeParams = init, .forceIDR = 1};
            uint64_t started = now_ns();
            CHECK(!uurb_encoder_reconfigure_config(s, &p));
            reconfigure_ns += now_ns() - started;
            reconfigurations++;
        }
        struct uurb_packet packet = {0};
        uint64_t started = now_ns();
        CHECK(!uurb_vaapi_encode_nv12(s, pixels, width, 1000 + i, i % 60 == 0, &packet));
        uint64_t elapsed = now_ns() - started;
        encode_ns += elapsed;
        if (elapsed > encode_max_ns) encode_max_ns = elapsed;
        CHECK(packet.timestamp == 1000 + i && packet.size && packet.data);
        if (changed || i % 60 == 0) CHECK(packet.idr);
        CHECK(fwrite(packet.data, 1, packet.size, out) == packet.size);
        CHECK(!uurb_encoder_release_packet(s));
    }
    CHECK(!fclose(out)); CHECK(!uurb_encoder_close(s)); free(pixels);
    printf("%s stress: %u full-HD frames, %u rate changes, timestamps/IDRs OK\n", hevc ? "HEVC" : "H264", count, reconfigurations);
    printf("TIMING {\"codec\":\"%s\",\"encode_us_avg\":%.3f,\"encode_us_max\":%.3f,\"reconfigure_us_avg\":%.3f}\n",
        hevc ? "hevc" : "h264", (double)encode_ns / count / 1000, (double)encode_max_ns / 1000,
        (double)reconfigure_ns / reconfigurations / 1000);
    return 0;
}
