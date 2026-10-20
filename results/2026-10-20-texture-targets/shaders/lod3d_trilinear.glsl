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
layout(binding=0) uniform highp sampler3D tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float lod=float[](-1.00,0.00,0.25,0.50,0.75,1.00,1.25,1.50,2.00,2.50,3.00,4.00)[i]; data[8u+i]=floatBitsToUint(textureLod(tex, vec3(4.0,4.0,4.0)/8.0, lod).r); } }
