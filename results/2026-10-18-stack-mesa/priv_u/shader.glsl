#version 320 es
precision highp int;
precision highp float;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
uint pick(uint i) { uint a[1024]; for (uint k=0u; k<1024u; k++) a[k] = (i*k) ^ (0x1234u*k); return a[(i*7u)&1023u] + a[(i*13u+5u)&1023u]; }
void main() { uint i=gl_GlobalInvocationID.x; if (i < count) data[8u+i]=pick(i); }
