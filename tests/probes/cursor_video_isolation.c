#define main unused_capture_main
#include "../../src/uu_pipewire_native_probe.c"
#undef main
#include <assert.h>

static unsigned recycled, encoded, stopped;
int pw_stream_queue_buffer(struct pw_stream *stream, struct pw_buffer *buffer)
{ (void)stream; (void)buffer; recycled++; return 0; }
int pw_main_loop_quit(struct pw_main_loop *loop)
{ (void)loop; stopped++; return 0; }
int uurb_vk_importer_check(struct uurb_vk_importer *s, int fd, uint32_t w, uint32_t h,
    uint32_t f, uint64_t m, uint32_t o, uint32_t stride)
{ (void)s; (void)fd; (void)w; (void)h; (void)f; (void)m; (void)o; (void)stride; abort(); }
int uurb_capture_encoder_cursor_frame(struct uurb_capture_encoder *s, uint64_t timestamp)
{ (void)s; (void)timestamp; abort(); }
int uurb_capture_encoder_frame(struct uurb_capture_encoder *s, const void *key, int fd,
    uint32_t w, uint32_t h, uint32_t f, uint64_t m, uint32_t o, uint32_t stride, uint64_t timestamp)
{
    (void)s; (void)key; (void)m; (void)o;
    assert(fd >= 0 && w == 2 && h == 2 && f == DRM_FORMAT_ARGB8888 && stride == 8 && timestamp > 0);
    encoded++; return 0;
}
int main(void)
{
    unsetenv("UURB_CAPTURE_TIMESTAMP_SOURCE");
    struct uurb_cursor_snapshot *cursor = calloc(1, sizeof(*cursor));
    struct uurb_cursor_snapshot *before = calloc(1, sizeof(*before));
    assert(cursor && before);
    cursor->header.generation = 1; cursor->header.active = 1; cursor->header.visible = 1;
    *before = *cursor;
    struct probe p = {.negotiated = 1, .status_fd = -1, .cursor = cursor,
        .encoder = (void *)1, .video = {.format = SPA_VIDEO_FORMAT_BGRA, .size = {2,2}}};
    struct spa_meta_cursor shape = {.id = 1, .position = {5,6}, .bitmap_offset = UINT32_MAX};
    struct spa_meta_header header = {.pts = 1000};
    struct spa_meta metas[] = {{.type = SPA_META_Cursor, .size = sizeof(shape), .data = &shape},
        {.type = SPA_META_Header, .size = sizeof(header), .data = &header}};
    int fd = open("/dev/null", O_RDONLY); assert(fd >= 0);
    struct spa_chunk chunk = {.size = 16, .stride = 8};
    struct spa_data plane = {.type = SPA_DATA_DmaBuf, .fd = fd, .chunk = &chunk};
    struct spa_buffer buffer = {.n_metas = 2, .metas = metas, .n_datas = 1, .datas = &plane};
    struct pw_buffer frame = {.buffer = &buffer};
    process_frame(&p, &frame);
    assert(!p.failed && !stopped && encoded == 1 && p.frames == 1 && p.cursor_rejected == 1);
    assert(!memcmp(before, cursor, sizeof(*cursor)));
    supersede_frame(&p, &frame);
    assert(!p.failed && !stopped && encoded == 1 && p.cursor_rejected == 2);
    chunk.size = 0; process_frame(&p, &frame);
    assert(!p.failed && !stopped && encoded == 1 && p.cursor_rejected == 3);
    assert(!memcmp(before, cursor, sizeof(*cursor)));
    metas[0].size = 1; chunk.flags = SPA_CHUNK_FLAG_CORRUPTED;
    process_frame(&p, &frame);
    assert(!p.failed && !stopped && encoded == 1 && p.cursor_rejected == 4);
    assert(!memcmp(before, cursor, sizeof(*cursor)));
    metas[0].size = sizeof(shape); chunk.flags = 0;
    shape.bitmap_offset = 0; chunk.size = 16; header.pts++;
    process_frame(&p, &frame);
    assert(!p.failed && encoded == 2 && cursor->header.x == 5 && p.cursor_updates == 1);
    chunk.flags = SPA_CHUNK_FLAG_CORRUPTED; process_frame(&p, &frame);
    assert(p.failed && stopped == 1 && encoded == 2 && recycled == 6);
    close(fd); free(before); free(cursor);
    puts("CURSOR_VIDEO_ISOLATION_PASS video survives malformed cursor, next cursor recovers, corrupt video rejected");
    return 0;
}
