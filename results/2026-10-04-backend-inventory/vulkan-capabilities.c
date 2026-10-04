#include <vulkan/vulkan.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
int main(void) {
 void *lib=dlopen("libvulkan.so.1", RTLD_NOW|RTLD_LOCAL);
 if(!lib){fprintf(stderr,"dlopen: %s\n",dlerror());return 1;}
 PFN_vkGetInstanceProcAddr get=(PFN_vkGetInstanceProcAddr)dlsym(lib,"vkGetInstanceProcAddr");
 if(!get)return 2;
 PFN_vkCreateInstance create=(PFN_vkCreateInstance)get(VK_NULL_HANDLE,"vkCreateInstance");
 VkApplicationInfo app={.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO,.pApplicationName="agx-p2-capability-only",.apiVersion=VK_API_VERSION_1_1};
 VkInstanceCreateInfo ci={.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,.pApplicationInfo=&app};
 VkInstance instance=VK_NULL_HANDLE;
 VkResult result=create(&ci,NULL,&instance);
 printf("vkCreateInstance=%d\n",result);fflush(stdout);
 if(result!=VK_SUCCESS)return 3;
 PFN_vkDestroyInstance destroy=(PFN_vkDestroyInstance)get(instance,"vkDestroyInstance");
 PFN_vkEnumeratePhysicalDevices enumerate=(PFN_vkEnumeratePhysicalDevices)get(instance,"vkEnumeratePhysicalDevices");
 PFN_vkGetPhysicalDeviceProperties props=(PFN_vkGetPhysicalDeviceProperties)get(instance,"vkGetPhysicalDeviceProperties");
 PFN_vkGetPhysicalDeviceQueueFamilyProperties queues=(PFN_vkGetPhysicalDeviceQueueFamilyProperties)get(instance,"vkGetPhysicalDeviceQueueFamilyProperties");
 PFN_vkGetPhysicalDeviceMemoryProperties memory=(PFN_vkGetPhysicalDeviceMemoryProperties)get(instance,"vkGetPhysicalDeviceMemoryProperties");
 uint32_t count=0;result=enumerate(instance,&count,NULL);
 printf("vkEnumeratePhysicalDevices(count)=%d count=%u\n",result,count);fflush(stdout);
 if(result!=VK_SUCCESS || count>16){destroy(instance,NULL);return 4;}
 VkPhysicalDevice devices[16];result=enumerate(instance,&count,devices);
 printf("vkEnumeratePhysicalDevices(list)=%d count=%u\n",result,count);
 if(result!=VK_SUCCESS){destroy(instance,NULL);return 5;}
 for(uint32_t i=0;i<count;i++){
  VkPhysicalDeviceProperties p;props(devices[i],&p);
  printf("device[%u] name=%s vendor=0x%x device=0x%x type=%u api=%u.%u.%u driver=0x%x\n",i,p.deviceName,p.vendorID,p.deviceID,p.deviceType,VK_VERSION_MAJOR(p.apiVersion),VK_VERSION_MINOR(p.apiVersion),VK_VERSION_PATCH(p.apiVersion),p.driverVersion);
  uint32_t n=0;queues(devices[i],&n,NULL);if(n>32){destroy(instance,NULL);return 6;}
  VkQueueFamilyProperties q[32];queues(devices[i],&n,q);
  for(uint32_t j=0;j<n;j++)printf("queue[%u] flags=0x%x count=%u timestampValidBits=%u\n",j,q[j].queueFlags,q[j].queueCount,q[j].timestampValidBits);
  VkPhysicalDeviceMemoryProperties m;memory(devices[i],&m);
  for(uint32_t j=0;j<m.memoryTypeCount;j++)printf("memoryType[%u] flags=0x%x heap=%u\n",j,m.memoryTypes[j].propertyFlags,m.memoryTypes[j].heapIndex);
 }
 destroy(instance,NULL);dlclose(lib);return count?0:7;
}
