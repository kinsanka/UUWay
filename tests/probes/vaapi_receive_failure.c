/* Test-only LD_PRELOAD shim: fail the tenth encoded packet once per codec.
 * This exercises LP recovery after valid headers and frames are delivered. */
#define _GNU_SOURCE
#include <libavcodec/avcodec.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
int avcodec_receive_packet(AVCodecContext *codec, AVPacket *packet)
{
    static unsigned calls[2];
    /* Wine's native encoder dependencies may be in a local ELF scope. */
    static void *library;
    if (!library) library = dlopen("libavcodec.so", RTLD_NOW | RTLD_LOCAL);
    int (*receive)(AVCodecContext *, AVPacket *) = library ? (void *)dlsym(library, "avcodec_receive_packet") : NULL;
    if (!receive) return AVERROR(ENOSYS);
    int index = codec && codec->codec && !strcmp(codec->codec->name, "h264_vaapi") ? 0 :
        codec && codec->codec && !strcmp(codec->codec->name, "hevc_vaapi") ? 1 : -1;
    if (index >= 0 && ++calls[index] == 10) {
        fprintf(stderr, "UURB_TEST_INJECTED_VAAPI_RECEIVE_FAILURE codec=%s\n", codec->codec->name);
        return AVERROR(EIO);
    }
    return receive(codec, packet);
}
