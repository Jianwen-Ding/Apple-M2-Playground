#version 320 es
precision highp int;
precision highp float;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
uint pick(uint i) { uvec4 a[64]; for (uint k=0u; k<64u; k++) a[k] = uvec4(i*k, i^k, i+k*3u, i*5u+k); uvec4 r = a[(i*7u)&63u] + a[(i*13u+5u)&63u]; return r.x ^ r.y ^ r.z ^ r.w; }
void main() { uint i=gl_GlobalInvocationID.x; if (i < count) data[8u+i]=pick(i); }
