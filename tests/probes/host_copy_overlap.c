/* Real DXVK texture check: the producer may overwrite its host buffer as soon
 * as UpdateSubresource returns, even while the consumer retains its texture. */
#define _GNU_SOURCE
#define COBJMACROS
#include "uu_d3d11_capture_texture.h"
#include <sys/mman.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)
int main(void)
{
    enum { WIDTH = 640, HEIGHT = 360, BYTES = WIDTH * HEIGHT * 4 };
    int fd = memfd_create("host-copy-test", MFD_CLOEXEC | MFD_ALLOW_SEALING);
    CHECK(fd >= 0 && !ftruncate(fd, BYTES));
    CHECK(!fcntl(fd, F_ADD_SEALS, F_SEAL_SHRINK | F_SEAL_GROW | F_SEAL_SEAL));
    unsigned char *host = mmap(NULL, BYTES, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    CHECK(host != MAP_FAILED);
    ID3D11Device *device = NULL;
    ID3D11DeviceContext *context = NULL;
    CHECK(SUCCEEDED(D3D11CreateDevice(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0,
        NULL, 0, D3D11_SDK_VERSION, &device, NULL, &context)));
    struct uurb_gpu_message message = {.magic = UURB_GPU_CHANNEL_MAGIC, .version = UURB_GPU_CHANNEL_VERSION,
        .kind = UURB_GPU_FRAME, .width = WIDTH, .height = HEIGHT, .sequence = 1, .timestamp = 1,
        .allocation_bytes = BYTES, .uuid = {1}, .ready_ns = 1};
    struct uurb_capture_texture *source = NULL;
    CHECK(SUCCEEDED(uurb_capture_texture_open(device, dup(fd), &message, &source)));
    D3D11_TEXTURE2D_DESC desc = {.Width = WIDTH, .Height = HEIGHT, .MipLevels = 1, .ArraySize = 1,
        .Format = DXGI_FORMAT_B8G8R8A8_UNORM, .SampleDesc = {1, 0}, .Usage = D3D11_USAGE_STAGING,
        .CPUAccessFlags = D3D11_CPU_ACCESS_READ};
    ID3D11Texture2D *readback = NULL;
    CHECK(SUCCEEDED(ID3D11Device_CreateTexture2D(device, &desc, NULL, &readback)));
    for (unsigned frame = 0; frame < 64; ++frame) {
        for (unsigned y = 0; y < HEIGHT; ++y) for (unsigned x = 0; x < WIDTH; ++x) {
            unsigned char *p = host + (y * WIDTH + x) * 4;
            p[0] = (x + frame * 3) & 255; p[1] = (y + frame * 5) & 255;
            p[2] = (x + y + frame * 7) & 255; p[3] = 255;
        }
        CHECK(SUCCEEDED(uurb_capture_texture_update(source)));
        /* Deliberately race GPU execution with immediate producer reuse. */
        memset(host, 0, BYTES);
        ID3D11DeviceContext_CopyResource(context, (ID3D11Resource *)readback,
            (ID3D11Resource *)uurb_capture_texture_get(source));
        D3D11_MAPPED_SUBRESOURCE mapped;
        CHECK(SUCCEEDED(ID3D11DeviceContext_Map(context, (ID3D11Resource *)readback, 0, D3D11_MAP_READ, 0, &mapped)));
        for (unsigned y = 0; y < HEIGHT; ++y) for (unsigned x = 0; x < WIDTH; ++x) {
            const unsigned char *p = (const unsigned char *)mapped.pData + y * mapped.RowPitch + x * 4;
            CHECK(p[0] == ((x + frame * 3) & 255) && p[1] == ((y + frame * 5) & 255) &&
                p[2] == ((x + y + frame * 7) & 255) && p[3] == 255);
        }
        ID3D11DeviceContext_Unmap(context, (ID3D11Resource *)readback, 0);
    }
    ID3D11Texture2D_Release(readback); uurb_capture_texture_close(source);
    ID3D11DeviceContext_Release(context); ID3D11Device_Release(device);
    CHECK(!munmap(host, BYTES) && !close(fd));
    puts("HOST_COPY_OVERLAP: 64 changing GPU textures; every pixel survives immediate producer overwrite");
    return 0;
}
