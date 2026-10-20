#version 320 es
precision highp int;
precision highp float;
precision highp sampler3D;
precision highp usampler3D;
precision highp sampler2DArray;
precision highp usampler2DArray;
precision highp samplerCube;
precision highp usamplerCube;
precision highp samplerBuffer;
precision highp usamplerBuffer;
precision highp sampler2D;
precision highp image3D;
precision highp image2DArray;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
layout(binding=0) uniform highp usampler3D tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec3 p; if(i<512u) p=ivec3(int(i%8u),int((i/8u)%8u),int(i/64u)); else { int k=int(i-512u); int a=k/32; int t=k%32-12; p = a==0 ? ivec3(t,3,4) : a==1 ? ivec3(3,t,4) : ivec3(3,4,t); } data[8u+i]=texelFetch(tex, p, 0).r; } }
