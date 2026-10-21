/* B29: sample an r32f texture from a compute shader through Mesa's Vulkan driver (Honeykrisp), with the image in a
 * linear layout at a chosen row pitch and the sampler state CUDA needs. Mesa builds every descriptor; nothing is
 * hand-encoded. Bounded: one dispatch, a fence wait of 10 s.
 *
 *   vulkan_texture SHADER.spv OUT.bin COUNT
 *   VKT_W, VKT_H     texture size (texels)
 *   VKT_DATA         W x H float32, row-major (packed)
 *   VKT_PITCH        0: VK_IMAGE_TILING_LINEAR at the pitch Mesa chooses (printed); N > 0: the LINEAR DRM format
 *                    modifier with row pitch N bytes (VK_EXT_image_drm_format_modifier, explicit layout)
 *   VKT_FILTER       nearest | linear          VKT_ADDR  clamp | border (border colour opaque white)
 *   VKT_UNNORM       1: unnormalized (pixel) coordinates
 * The shader: binding 0 = std430 uint buffer (COUNT words written to OUT.bin), binding 1 = sampler2D. */
#include <vulkan/vulkan.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

static void require(int ok, const char *stage) {
    if (!ok) { printf("{\"error\":\"%s\"}\n", stage); exit(1); }
}
static void check(VkResult r, const char *stage) {
    if (r != VK_SUCCESS) { printf("{\"error\":\"%s\",\"result\":%d}\n", stage, r); exit(1); }
}
static void *readfile(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb"); require(f != NULL, "open");
    fseek(f, 0, SEEK_END); long n = ftell(f); rewind(f);
    require(n > 0 && n <= (64 << 20), "size");
    void *p = malloc((size_t)n); require(p != NULL, "malloc");
    require(fread(p, 1, (size_t)n, f) == (size_t)n, "read"); fclose(f);
    *size = (size_t)n; return p;
}
static unsigned envu(const char *k, unsigned d) { const char *v = getenv(k); return v ? (unsigned)strtoul(v, NULL, 0) : d; }
static int enveq(const char *k, const char *s) { const char *v = getenv(k); return v && !strcmp(v, s); }

static uint32_t memtype(VkPhysicalDevice pd, uint32_t bits, VkMemoryPropertyFlags want) {
    VkPhysicalDeviceMemoryProperties mp; vkGetPhysicalDeviceMemoryProperties(pd, &mp);
    for (uint32_t i = 0; i < mp.memoryTypeCount; i++)
        if ((bits & (1u << i)) && (mp.memoryTypes[i].propertyFlags & want) == want) return i;
    require(0, "memory-type"); return 0;
}

int main(int argc, char **argv) {
    require(argc == 4, "usage: vulkan_texture SHADER.spv OUT.bin COUNT");
    unsigned count = (unsigned)strtoul(argv[3], NULL, 0);
    require(count > 0 && count <= (1u << 20), "count");
    unsigned w = envu("VKT_W", 16), h = envu("VKT_H", 1), pitch = envu("VKT_PITCH", 0);
    require(w > 0 && w <= 16384 && h > 0 && h <= 16384, "texture-size");
    size_t dsize; float *data = readfile(getenv("VKT_DATA"), &dsize);
    require(dsize == (size_t)w * h * 4, "data-size");
    size_t ssize; uint32_t *spv = readfile(argv[1], &ssize);

    VkApplicationInfo ai = {VK_STRUCTURE_TYPE_APPLICATION_INFO, 0, "b29", 0, "b29", 0, VK_API_VERSION_1_3};
    VkInstanceCreateInfo ici = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, 0, 0, &ai};
    VkInstance inst; check(vkCreateInstance(&ici, 0, &inst), "instance");
    uint32_t npd = 4; VkPhysicalDevice pds[4]; vkEnumeratePhysicalDevices(inst, &npd, pds);
    VkPhysicalDevice pd = VK_NULL_HANDLE;
    for (uint32_t i = 0; i < npd; i++) {
        VkPhysicalDeviceProperties p; vkGetPhysicalDeviceProperties(pds[i], &p);
        if (strstr(p.deviceName, "Apple")) { pd = pds[i]; printf("{\"device\":\"%s\"}\n", p.deviceName); }
    }
    require(pd != VK_NULL_HANDLE, "no-apple-device (llvmpipe fallback refused)");
    float prio = 1.0f;
    VkDeviceQueueCreateInfo qci = {VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, 0, 0, 0, 1, &prio};
    const char *exts[] = {"VK_EXT_image_drm_format_modifier"};
    VkDeviceCreateInfo dci = {VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, 0, 0, 1, &qci, 0, 0, pitch ? 1u : 0u, exts};
    VkDevice dev; check(vkCreateDevice(pd, &dci, 0, &dev), "device");
    VkQueue queue; vkGetDeviceQueue(dev, 0, 0, &queue);

    /* the image: r32f, sampled, linear */
    VkSubresourceLayout plane = {0, (VkDeviceSize)pitch * h, pitch, 0, 0};
    VkImageDrmFormatModifierExplicitCreateInfoEXT mod = {VK_STRUCTURE_TYPE_IMAGE_DRM_FORMAT_MODIFIER_EXPLICIT_CREATE_INFO_EXT, 0,
        0 /* DRM_FORMAT_MOD_LINEAR */, 1, &plane};
    VkImageCreateInfo imci = {VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, pitch ? &mod : 0, 0, VK_IMAGE_TYPE_2D, VK_FORMAT_R32_SFLOAT,
        {w, h, 1}, 1, 1, VK_SAMPLE_COUNT_1_BIT, pitch ? VK_IMAGE_TILING_DRM_FORMAT_MODIFIER_EXT : VK_IMAGE_TILING_LINEAR,
        VK_IMAGE_USAGE_SAMPLED_BIT, VK_SHARING_MODE_EXCLUSIVE, 0, 0, VK_IMAGE_LAYOUT_PREINITIALIZED};
    VkImage img; VkResult ir = vkCreateImage(dev, &imci, 0, &img);
    if (ir != VK_SUCCESS) { printf("{\"image_rejected\":true,\"pitch\":%u,\"result\":%d}\n", pitch, ir); return 2; }
    VkMemoryRequirements mr; vkGetImageMemoryRequirements(dev, img, &mr);
    VkMemoryAllocateInfo mai = {VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO, 0, mr.size,
        memtype(pd, mr.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT)};
    VkDeviceMemory imem; check(vkAllocateMemory(dev, &mai, 0, &imem), "image-memory");
    check(vkBindImageMemory(dev, img, imem, 0), "image-bind");
    VkImageSubresource sub = {pitch ? VK_IMAGE_ASPECT_MEMORY_PLANE_0_BIT_EXT : VK_IMAGE_ASPECT_COLOR_BIT, 0, 0};
    VkSubresourceLayout lay; vkGetImageSubresourceLayout(dev, img, &sub, &lay);
    printf("{\"row_pitch\":%llu,\"offset\":%llu,\"size\":%llu,\"requested_pitch\":%u}\n",
           (unsigned long long)lay.rowPitch, (unsigned long long)lay.offset, (unsigned long long)lay.size, pitch);
    char *ip; check(vkMapMemory(dev, imem, 0, VK_WHOLE_SIZE, 0, (void **)&ip), "image-map");
    memset(ip, 0xcd, (size_t)mr.size);                 /* padding between rows is junk, never zero */
    for (unsigned y = 0; y < h; y++) memcpy(ip + lay.offset + (size_t)y * lay.rowPitch, data + (size_t)y * w, (size_t)w * 4);
    vkUnmapMemory(dev, imem);

    VkImageViewCreateInfo vci = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, 0, 0, img, VK_IMAGE_VIEW_TYPE_2D, VK_FORMAT_R32_SFLOAT,
        {0, 0, 0, 0}, {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    VkImageView view; check(vkCreateImageView(dev, &vci, 0, &view), "view");
    VkFilter flt = enveq("VKT_FILTER", "linear") ? VK_FILTER_LINEAR : VK_FILTER_NEAREST;
    VkSamplerAddressMode am = enveq("VKT_ADDR", "border") ? VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_BORDER : VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    VkSamplerCreateInfo sci = {VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO, 0, 0, flt, flt, VK_SAMPLER_MIPMAP_MODE_NEAREST, am, am, am,
        0, VK_FALSE, 1, VK_FALSE, VK_COMPARE_OP_ALWAYS, 0, 0, VK_BORDER_COLOR_FLOAT_OPAQUE_WHITE, envu("VKT_UNNORM", 0) ? VK_TRUE : VK_FALSE};
    VkSampler smp; check(vkCreateSampler(dev, &sci, 0, &smp), "sampler");

    /* output buffer */
    VkBufferCreateInfo bci = {VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, 0, 0, (VkDeviceSize)count * 4, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT};
    VkBuffer buf; check(vkCreateBuffer(dev, &bci, 0, &buf), "buffer");
    vkGetBufferMemoryRequirements(dev, buf, &mr);
    mai.allocationSize = mr.size;
    mai.memoryTypeIndex = memtype(pd, mr.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    VkDeviceMemory bmem; check(vkAllocateMemory(dev, &mai, 0, &bmem), "buffer-memory");
    check(vkBindBufferMemory(dev, buf, bmem, 0), "buffer-bind");
    uint32_t *bp; check(vkMapMemory(dev, bmem, 0, VK_WHOLE_SIZE, 0, (void **)&bp), "buffer-map");
    for (unsigned i = 0; i < count; i++) bp[i] = 0xcdcdcdcd;

    /* pipeline */
    VkDescriptorSetLayoutBinding b[2] = {{0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, 0},
                                         {1, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1, VK_SHADER_STAGE_COMPUTE_BIT, 0}};
    VkDescriptorSetLayoutCreateInfo dlci = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, 0, 0, 2, b};
    VkDescriptorSetLayout dsl; check(vkCreateDescriptorSetLayout(dev, &dlci, 0, &dsl), "set-layout");
    VkPipelineLayoutCreateInfo plci = {VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, 0, 0, 1, &dsl};
    VkPipelineLayout pl; check(vkCreatePipelineLayout(dev, &plci, 0, &pl), "pipeline-layout");
    VkShaderModuleCreateInfo smci = {VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, 0, 0, ssize, spv};
    VkShaderModule sm; check(vkCreateShaderModule(dev, &smci, 0, &sm), "shader");
    VkComputePipelineCreateInfo cpci = {VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO, 0, 0,
        {VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, 0, 0, VK_SHADER_STAGE_COMPUTE_BIT, sm, "main", 0}, pl};
    VkPipeline pipe; check(vkCreateComputePipelines(dev, VK_NULL_HANDLE, 1, &cpci, 0, &pipe), "pipeline");
    VkDescriptorPoolSize ps[2] = {{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1}, {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1}};
    VkDescriptorPoolCreateInfo dpci = {VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO, 0, 0, 1, 2, ps};
    VkDescriptorPool dp; check(vkCreateDescriptorPool(dev, &dpci, 0, &dp), "pool");
    VkDescriptorSetAllocateInfo dsai = {VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO, 0, dp, 1, &dsl};
    VkDescriptorSet ds; check(vkAllocateDescriptorSets(dev, &dsai, &ds), "set");
    VkDescriptorBufferInfo dbi = {buf, 0, VK_WHOLE_SIZE};
    VkDescriptorImageInfo dii = {smp, view, VK_IMAGE_LAYOUT_GENERAL};
    VkWriteDescriptorSet wr[2] = {{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, 0, ds, 0, 0, 1, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 0, &dbi, 0},
                                  {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, 0, ds, 1, 0, 1, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, &dii, 0, 0}};
    vkUpdateDescriptorSets(dev, 2, wr, 0, 0);

    /* record: preinitialized -> general, dispatch */
    VkCommandPoolCreateInfo cpi = {VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO, 0, 0, 0};
    VkCommandPool cp; check(vkCreateCommandPool(dev, &cpi, 0, &cp), "command-pool");
    VkCommandBufferAllocateInfo cbai = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO, 0, cp, VK_COMMAND_BUFFER_LEVEL_PRIMARY, 1};
    VkCommandBuffer cb; check(vkAllocateCommandBuffers(dev, &cbai, &cb), "command-buffer");
    VkCommandBufferBeginInfo cbbi = {VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO, 0, VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT};
    check(vkBeginCommandBuffer(cb, &cbbi), "begin");
    VkImageMemoryBarrier imb = {VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER, 0, VK_ACCESS_HOST_WRITE_BIT, VK_ACCESS_SHADER_READ_BIT,
        VK_IMAGE_LAYOUT_PREINITIALIZED, VK_IMAGE_LAYOUT_GENERAL, VK_QUEUE_FAMILY_IGNORED, VK_QUEUE_FAMILY_IGNORED, img,
        {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_HOST_BIT, VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT, 0, 0, 0, 0, 0, 1, &imb);
    vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pipe);
    vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_COMPUTE, pl, 0, 1, &ds, 0, 0);
    vkCmdDispatch(cb, (count + 31) / 32, 1, 1);
    check(vkEndCommandBuffer(cb), "end");
    VkFenceCreateInfo fci = {VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
    VkFence fence; check(vkCreateFence(dev, &fci, 0, &fence), "fence");
    VkSubmitInfo si = {VK_STRUCTURE_TYPE_SUBMIT_INFO, 0, 0, 0, 0, 1, &cb};
    check(vkQueueSubmit(queue, 1, &si, fence), "submit");
    check(vkWaitForFences(dev, 1, &fence, VK_TRUE, 10000000000ull), "wait");
    FILE *o = fopen(argv[2], "wb"); require(o != NULL, "out-open");
    require(fwrite(bp, 4, count, o) == count, "out-write"); fclose(o);
    printf("{\"ok\":true,\"count\":%u}\n", count);
    vkDestroyFence(dev, fence, 0); vkDestroyCommandPool(dev, cp, 0); vkDestroyDescriptorPool(dev, dp, 0);
    vkDestroyPipeline(dev, pipe, 0); vkDestroyShaderModule(dev, sm, 0); vkDestroyPipelineLayout(dev, pl, 0);
    vkDestroyDescriptorSetLayout(dev, dsl, 0); vkDestroySampler(dev, smp, 0); vkDestroyImageView(dev, view, 0);
    vkUnmapMemory(dev, bmem); vkDestroyBuffer(dev, buf, 0); vkFreeMemory(dev, bmem, 0);
    vkDestroyImage(dev, img, 0); vkFreeMemory(dev, imem, 0); vkDestroyDevice(dev, 0); vkDestroyInstance(inst, 0);
    return 0;
}
