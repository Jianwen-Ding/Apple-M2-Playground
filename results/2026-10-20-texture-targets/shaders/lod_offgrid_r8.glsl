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
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ vec2 p = i < 64u ? vec2(6.5, 9.5) : vec2(6.5+0.3125, 9.5+0.6875); float lod = float(i%64u)/64.0; data[8u+i]=floatBitsToUint(textureLod(tex, p/16.0, lod).r); } }
