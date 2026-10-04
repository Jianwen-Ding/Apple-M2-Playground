/* Capability queries only: no logical device, shader, buffer, or dispatch. */
#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void string(const char *s) {
    putchar('"');
    for (; *s; s++) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') printf("\\%c", c);
        else if (c < 32) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}
static void version(uint32_t v) {
    printf("\"%u.%u.%u\"", VK_API_VERSION_MAJOR(v), VK_API_VERSION_MINOR(v), VK_API_VERSION_PATCH(v));
}
#define LOAD(name) PFN_##name name = (PFN_##name)get(instance, #name); if (!name) { fprintf(stderr, "missing %s\n", #name); return 2; }
int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    void *lib = dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!lib) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 1; }
    PFN_vkGetInstanceProcAddr get = (PFN_vkGetInstanceProcAddr)dlsym(lib, "vkGetInstanceProcAddr");
    if (!get) return 2;
    VkInstance instance = VK_NULL_HANDLE;
    LOAD(vkCreateInstance);
    PFN_vkEnumerateInstanceVersion loader_version = (PFN_vkEnumerateInstanceVersion)get(instance, "vkEnumerateInstanceVersion");
    uint32_t lv = VK_API_VERSION_1_0;
    VkResult result = loader_version ? loader_version(&lv) : VK_SUCCESS;
    if (result != VK_SUCCESS || lv < VK_API_VERSION_1_1) return 2;
    VkApplicationInfo app = {.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
        .pApplicationName = "agx-capabilities-only", .apiVersion = VK_API_VERSION_1_1};
    VkInstanceCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo = &app};
    result = vkCreateInstance(&ci, NULL, &instance);
    if (result != VK_SUCCESS) { printf("{\"vkCreateInstance\":%d}\n", result); return 3; }
    LOAD(vkDestroyInstance);
    LOAD(vkEnumeratePhysicalDevices);
    LOAD(vkEnumerateDeviceExtensionProperties);
    LOAD(vkGetPhysicalDeviceProperties2);
    LOAD(vkGetPhysicalDeviceFeatures2);
    LOAD(vkGetPhysicalDeviceQueueFamilyProperties);
    LOAD(vkGetPhysicalDeviceMemoryProperties);
    uint32_t count = 0;
    result = vkEnumeratePhysicalDevices(instance, &count, NULL);
    if (result != VK_SUCCESS || count == 0 || count > 16) { fprintf(stderr, "device count result=%d count=%u\n", result, count); return 4; }
    VkPhysicalDevice devices[16];
    result = vkEnumeratePhysicalDevices(instance, &count, devices);
    if (result != VK_SUCCESS || count != 1) { fprintf(stderr, "expected one Asahi device result=%d count=%u\n", result, count); return 4; }
    VkPhysicalDevice dev = devices[0];
    uint32_t ne = 0;
    result = vkEnumerateDeviceExtensionProperties(dev, NULL, &ne, NULL);
    if (result != VK_SUCCESS || ne > 512) return 5;
    VkExtensionProperties ext[512];
    result = vkEnumerateDeviceExtensionProperties(dev, NULL, &ne, ext);
    if (result != VK_SUCCESS) return 5;
    bool shader = false, drm = false, driver_extension = false;
    for (uint32_t i = 0; i < ne; i++) {
        shader |= strcmp(ext[i].extensionName, VK_EXT_SHADER_OBJECT_EXTENSION_NAME) == 0;
        drm |= strcmp(ext[i].extensionName, VK_EXT_PHYSICAL_DEVICE_DRM_EXTENSION_NAME) == 0;
        driver_extension |= strcmp(ext[i].extensionName, VK_KHR_DRIVER_PROPERTIES_EXTENSION_NAME) == 0;
    }
    VkPhysicalDeviceProperties basic;
    PFN_vkGetPhysicalDeviceProperties basic_properties = (PFN_vkGetPhysicalDeviceProperties)get(instance, "vkGetPhysicalDeviceProperties");
    if (!basic_properties) return 2;
    basic_properties(dev, &basic);
    if (basic.apiVersion < VK_API_VERSION_1_1) return 5;
    bool driver_supported = basic.apiVersion >= VK_API_VERSION_1_2 || driver_extension;
    VkPhysicalDeviceShaderObjectPropertiesEXT so = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_OBJECT_PROPERTIES_EXT};
    VkPhysicalDeviceDrmPropertiesEXT dp = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRM_PROPERTIES_EXT, .pNext = shader ? &so : NULL};
    VkPhysicalDeviceDriverProperties driver = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES, .pNext = drm ? (void *)&dp : shader ? (void *)&so : NULL};
    VkPhysicalDeviceProperties2 props = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = driver_supported ? (void *)&driver : drm ? (void *)&dp : shader ? (void *)&so : NULL};
    vkGetPhysicalDeviceProperties2(dev, &props);
    VkPhysicalDeviceShaderObjectFeaturesEXT sf = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_OBJECT_FEATURES_EXT};
    VkPhysicalDeviceFeatures2 features = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = shader ? &sf : NULL};
    vkGetPhysicalDeviceFeatures2(dev, &features);
    uint32_t nq = 0;
    vkGetPhysicalDeviceQueueFamilyProperties(dev, &nq, NULL);
    if (nq > 32) return 6;
    VkQueueFamilyProperties q[32];
    vkGetPhysicalDeviceQueueFamilyProperties(dev, &nq, q);
    bool compute = false;
    for (uint32_t i = 0; i < nq; i++) compute |= q[i].queueCount && (q[i].queueFlags & VK_QUEUE_COMPUTE_BIT);
    VkPhysicalDeviceMemoryProperties mem;
    vkGetPhysicalDeviceMemoryProperties(dev, &mem);
    bool accepted = driver.driverID == VK_DRIVER_ID_MESA_HONEYKRISP &&
        props.properties.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU && compute && drm && dp.hasRender;
    printf("{\"vkCreateInstance\":0,\"loader_api\":"); version(lv);
    printf(",\"requested_instance_api\":\"1.1.0\",\"physical_device_count\":%u,\"accepted_asahi\":%s,\"device\":{\"name\":", count, accepted ? "true" : "false"); string(props.properties.deviceName);
    printf(",\"api\":"); version(props.properties.apiVersion);
    printf(",\"vendor_id\":%u,\"device_id\":%u,\"device_type\":%u,\"driver_version_raw\":%u,\"driver_id\":%u,\"driver_name\":", props.properties.vendorID, props.properties.deviceID, props.properties.deviceType, props.properties.driverVersion, driver.driverID); string(driver.driverName);
    printf(",\"driver_info\":"); string(driver.driverInfo);
    printf(",\"drm_extension\":%s,\"has_render\":%s,\"render_major\":%lld,\"render_minor\":%lld,\"shader_object_extension\":%s,\"shader_object_feature\":%s,\"shader_binary_uuid\":", drm ? "true" : "false", dp.hasRender ? "true" : "false", (long long)dp.renderMajor, (long long)dp.renderMinor, shader ? "true" : "false", shader && sf.shaderObject ? "true" : "false");
    if (shader) { putchar('"'); for (unsigned i = 0; i < VK_UUID_SIZE; i++) printf("%02x", so.shaderBinaryUUID[i]); putchar('"'); } else printf("null");
    printf(",\"shader_binary_version\":"); if (shader) printf("%u", so.shaderBinaryVersion); else printf("null");
    printf(",\"features\":{\"shaderInt64\":%u,\"shaderInt16\":%u,\"shaderFloat64\":%u},\"compute_limits\":{\"max_invocations\":%u,\"max_workgroup_size\":[%u,%u,%u],\"max_workgroup_count\":[%u,%u,%u],\"shared_memory_bytes\":%u},\"queues\":[", features.features.shaderInt64, features.features.shaderInt16, features.features.shaderFloat64, props.properties.limits.maxComputeWorkGroupInvocations, props.properties.limits.maxComputeWorkGroupSize[0], props.properties.limits.maxComputeWorkGroupSize[1], props.properties.limits.maxComputeWorkGroupSize[2], props.properties.limits.maxComputeWorkGroupCount[0], props.properties.limits.maxComputeWorkGroupCount[1], props.properties.limits.maxComputeWorkGroupCount[2], props.properties.limits.maxComputeSharedMemorySize);
    for (uint32_t i = 0; i < nq; i++) printf("%s{\"index\":%u,\"flags\":%u,\"count\":%u,\"timestamp_valid_bits\":%u}", i ? "," : "", i, q[i].queueFlags, q[i].queueCount, q[i].timestampValidBits);
    printf("],\"memory_heaps\":[");
    for (uint32_t i = 0; i < mem.memoryHeapCount; i++) printf("%s{\"index\":%u,\"size_bytes\":%llu,\"flags\":%u}", i ? "," : "", i, (unsigned long long)mem.memoryHeaps[i].size, mem.memoryHeaps[i].flags);
    printf("],\"memory_types\":[");
    for (uint32_t i = 0; i < mem.memoryTypeCount; i++) printf("%s{\"index\":%u,\"flags\":%u,\"heap\":%u}", i ? "," : "", i, mem.memoryTypes[i].propertyFlags, mem.memoryTypes[i].heapIndex);
    printf("],\"extensions\":[");
    for (uint32_t i = 0; i < ne; i++) { if (i) putchar(','); printf("{\"name\":"); string(ext[i].extensionName); printf(",\"spec_version\":%u}", ext[i].specVersion); }
    printf("]}}\n");
    vkDestroyInstance(instance, NULL); dlclose(lib);
    return accepted ? 0 : 7;
}
