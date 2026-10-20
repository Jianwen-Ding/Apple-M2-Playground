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
layout(binding=0) uniform highp sampler2DArray tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float fx=float(i%64u)/64.0; float l=float(i/64u)*1.3+0.2; data[8u+i]=floatBitsToUint(textureLod(tex, vec3((2.5+fx)/8.0, (4.5+0.25)/8.0, l), 0.0).r); } }
