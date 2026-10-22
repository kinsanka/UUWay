/* Real native capability enumeration and rejection, without desktop/UU. */
#include "native_nvenc_query.h"
#include "native_nvenc_reference_config.h"
#include <vulkan/vulkan.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion = VK_API_VERSION_1_1};
    VkInstanceCreateInfo create = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
    VkInstance instance;
    assert(vkCreateInstance(&create, NULL, &instance) == VK_SUCCESS);
    VkPhysicalDevice devices[32]; uint32_t n = 32;
    assert(vkEnumeratePhysicalDevices(instance, &n, devices) == VK_SUCCESS);
    void *query = NULL;
    for (unsigned i = 0; i < n && !query; ++i) {
        VkPhysicalDeviceIDProperties id = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_ID_PROPERTIES};
        VkPhysicalDeviceProperties2 props = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &id};
        vkGetPhysicalDeviceProperties2(devices[i], &props);
        uurb_nvenc_query_open(id.deviceUUID, &query);
    }
    assert(query);
    GUID codecs[2]; uint32_t count = 0;
    assert(!uurb_nvenc_query(query, UURB_CODECS, NULL, codecs, 2, &count));
    assert(count == 1 && !memcmp(codecs, &NV_ENC_CODEC_H264_GUID, sizeof(GUID)));
    int cap;
    assert(uurb_nvenc_query(query, UURB_CAP, &NV_ENC_CODEC_HEVC_GUID, &cap, NV_ENC_CAPS_WIDTH_MAX, NULL) == NV_ENC_ERR_UNSUPPORTED_PARAM);
    NV_ENC_CONFIG preset = {.version = NV_ENC_CONFIG_VER}, cfg;
    NV_ENC_INITIALIZE_PARAMS init;
    unsigned char headers[65536]; uint32_t bytes = 0;
    uurb_nvenc_reference_config(&preset, 640, 360, 1, 4000000, &cfg, &init);
    assert(uurb_nvenc_query_sequence(query, &init, headers, sizeof(headers), &bytes) == NV_ENC_ERR_UNSUPPORTED_PARAM);
    uurb_nvenc_reference_config(&preset, 640, 360, 0, 4000000, &cfg, &init);
    assert(!uurb_nvenc_query_sequence(query, &init, headers, sizeof(headers), &bytes) && bytes > 0);
    assert(!uurb_nvenc_query_close(query)); vkDestroyInstance(instance, NULL);
    puts("VAAPI_CODEC_POLICY_PASS H264 advertised/headers valid; HEVC capability/sequence rejected");
    return 0;
}
