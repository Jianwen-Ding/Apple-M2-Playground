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
layout(binding=0) uniform highp sampler2D tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float x = i < 4096u ? 4.5+float(i)/4096.0 : 4.5+float(i-4096u)/64.0 + 1.0/8192.0; data[8u+i]=floatBitsToUint(textureLod(tex, vec2(x, 7.5)/16.0, 0.0).r); } }
