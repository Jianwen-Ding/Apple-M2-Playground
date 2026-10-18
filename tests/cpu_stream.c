/* CPU memory streamer for the SLC-sharing test (scripts/run_drm_slc.py --cpu-threads N): N threads each read a private 64 MiB buffer in a loop
 * until the stop file exists (checked once per pass). usage: cpu_stream THREADS STOPFILE */
#define _POSIX_C_SOURCE 200809L
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static const char *stopfile;
static volatile uint64_t sink;
static void *run(void *arg) {
    (void)arg;
    size_t n = (64u << 20) / sizeof(uint64_t);
    uint64_t *buf = malloc(n * sizeof *buf);
    if (!buf) return NULL;
    for (size_t i = 0; i < n; i++) buf[i] = i * 0x9e3779b97f4a7c15ull;
    uint64_t acc = 0;
    while (access(stopfile, F_OK) != 0) {
        for (size_t i = 0; i < n; i += 8) acc += buf[i] + buf[i+1] + buf[i+2] + buf[i+3] + buf[i+4] + buf[i+5] + buf[i+6] + buf[i+7];
    }
    sink = acc;
    free(buf);
    return NULL;
}
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    int threads = atoi(argv[1]);
    stopfile = argv[2];
    if (threads < 1 || threads > 16) return 2;
    pthread_t t[16];
    for (int i = 0; i < threads; i++) pthread_create(&t[i], NULL, run, NULL);
    for (int i = 0; i < threads; i++) pthread_join(t[i], NULL);
    return 0;
}
