#define _GNU_SOURCE
#include <pipewire/pipewire.h>
#include <spa/buffer/meta.h>
#include <spa/param/buffers.h>
#include <spa/pod/builder.h>
#include <spa/pod/parser.h>
#include <dlfcn.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>

/* Scope this library to the UU PipeWire producer in Umbriel only. Preserve the
 * existing bounded 384px cursor snapshot ABI; negotiate room for a producer's
 * 512px metadata allocation without changing accepted bitmap dimensions. */
static int (*real_update)(struct pw_stream *, const struct spa_pod **, uint32_t);
static pthread_once_t initialized = PTHREAD_ONCE_INIT;

static void resolve_symbols(void)
{
    *(void **)(&real_update) = dlsym(RTLD_NEXT, "pw_stream_update_params");
}

int pw_stream_update_params(struct pw_stream *stream,
                           const struct spa_pod **params, uint32_t count)
{
    pthread_once(&initialized, resolve_symbols);
    if (!real_update) return -38;
    if (!params || count > 32) return real_update(stream, params, count);
    const struct spa_pod *forward[32];
    uint8_t storage[32][256] __attribute__((aligned(8)));
    for (uint32_t index = 0; index < count; index++) {
        forward[index] = params[index];
        uint32_t type = 0;
        int32_t size = 0;
        if (!params[index] ||
            spa_pod_parse_object(params[index], SPA_TYPE_OBJECT_ParamMeta, NULL,
                SPA_PARAM_META_type, SPA_POD_Id(&type),
                SPA_PARAM_META_size, SPA_POD_Int(&size)) < 0 ||
            type != SPA_META_Cursor) continue;
        const int32_t minimum = sizeof(struct spa_meta_cursor) + sizeof(struct spa_meta_bitmap);
        const int32_t maximum = minimum + 512 * 512 * 4;
        if (size < minimum || size > maximum) continue;
        struct spa_pod_builder builder = SPA_POD_BUILDER_INIT(storage[index], sizeof(storage[index]));
        const struct spa_pod *replacement = spa_pod_builder_add_object(&builder,
            SPA_TYPE_OBJECT_ParamMeta, SPA_PARAM_Meta,
            SPA_PARAM_META_type, SPA_POD_Id(SPA_META_Cursor),
            SPA_PARAM_META_size, SPA_POD_CHOICE_RANGE_Int(maximum, minimum, maximum));
        if (replacement) {
            forward[index] = replacement;
            fprintf(stderr, "UURB_UMBRIEL_CURSOR_META {\"previous\":%d,\"minimum\":%d,\"preferred\":%d}\n",
                    size, minimum, maximum);
        }
    }
    return real_update(stream, forward, count);
}
