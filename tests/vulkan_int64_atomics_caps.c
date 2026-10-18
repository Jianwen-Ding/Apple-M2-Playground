/* Prints whether each Vulkan device reports 64-bit atomics (Vulkan 1.2 shaderBufferInt64Atomics / shaderSharedInt64Atomics and the
   VK_KHR_shader_atomic_int64 feature struct). Build: cc tests/vulkan_int64_atomics_caps.c -I<mesa>/include -o caps /usr/lib64/libvulkan.so.1
   Run with the Asahi ICD only: LD_LIBRARY_PATH=<vulkan-runtime>/usr/lib64 VK_DRIVER_FILES=/usr/share/vulkan/icd.d/asahi_icd.aarch64.json ./caps */
#include <vulkan/vulkan.h>
#include <stdio.h>
#include <string.h>
int main(void){
  VkApplicationInfo ai={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.apiVersion=VK_API_VERSION_1_3};
  VkInstanceCreateInfo ci={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&ai};
  VkInstance inst; if(vkCreateInstance(&ci,0,&inst)){puts("no instance");return 1;}
  uint32_t n=0; vkEnumeratePhysicalDevices(inst,&n,0); VkPhysicalDevice d[8]; if(n>8)n=8; vkEnumeratePhysicalDevices(inst,&n,d);
  for(uint32_t i=0;i<n;i++){
    VkPhysicalDeviceProperties p; vkGetPhysicalDeviceProperties(d[i],&p);
    VkPhysicalDeviceVulkan12Features f12={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
    VkPhysicalDeviceShaderAtomicInt64Features ai64={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SHADER_ATOMIC_INT64_FEATURES};
    VkPhysicalDeviceFeatures2 f2={.sType=VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2,.pNext=&f12};
    f12.pNext=0; vkGetPhysicalDeviceFeatures2(d[i],&f2);
    f2.pNext=&ai64; vkGetPhysicalDeviceFeatures2(d[i],&f2);
    printf("%s: shaderInt64=%u bufferInt64Atomics(1.2)=%u sharedInt64Atomics(1.2)=%u bufferInt64Atomics(ext struct)=%u shared=%u\n",p.deviceName,f2.features.shaderInt64,f12.shaderBufferInt64Atomics,f12.shaderSharedInt64Atomics,ai64.shaderBufferInt64Atomics,ai64.shaderSharedInt64Atomics);
  }
  return 0;}
