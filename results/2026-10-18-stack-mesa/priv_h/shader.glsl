#version 320 es
precision highp int;
precision highp float;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
uint pick(uint i) { mediump float a[512]; for (uint k=0u; k<512u; k++) a[k] = float((i*k)&255u) * 0.5; return floatBitsToUint(float(a[(i*7u)&511u] + a[(i*13u+5u)&511u])); }
void main() { uint i=gl_GlobalInvocationID.x; if (i < count) data[8u+i]=pick(i); }
