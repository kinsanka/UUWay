#ifndef UURB_NATIVE_PERF_TRACE_H
#define UURB_NATIVE_PERF_TRACE_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
/* Opt-in, bounded aggregate timings; never pixels, window titles or accounts. */
struct uurb_perf_trace {
    uint64_t started, samples, first, second, maximum;
    unsigned reports;
};
static inline uint64_t uurb_perf_now(void)
{
    const char *setting = getenv("UURB_PERF_TRACE");
    struct timespec now;
    if (!setting || setting[0] != '1' || setting[1] || clock_gettime(CLOCK_MONOTONIC, &now)) return 0;
    return (uint64_t)now.tv_sec * 1000000000ull + now.tv_nsec;
}
static inline void uurb_perf_sample(struct uurb_perf_trace *s, const char *stage,
    uint64_t start, uint64_t middle, uint64_t finish)
{
    if (!start || middle < start || finish < middle || s->reports >= 24) return;
    if (!s->started) s->started = start;
    s->samples++; s->first += middle - start; s->second += finish - middle;
    if (finish - start > s->maximum) s->maximum = finish - start;
    uint64_t elapsed = finish - s->started;
    if (elapsed < 5000000000ull) return;
    fprintf(stderr, "UURB_NATIVE_PERF {\"stage\":\"%s\",\"frames\":%llu,\"fps\":%.2f,"
        "\"first_us_avg\":%.2f,\"second_us_avg\":%.2f,\"total_us_max\":%.2f}\n",
        stage, (unsigned long long)s->samples, (double)s->samples * 1e9 / elapsed,
        (double)s->first / s->samples / 1000, (double)s->second / s->samples / 1000,
        (double)s->maximum / 1000);
    s->started = finish; s->samples = s->first = s->second = s->maximum = 0; s->reports++;
}
#endif
