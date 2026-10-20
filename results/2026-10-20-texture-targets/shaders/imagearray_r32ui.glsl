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
precision highp uimage2DArray;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
layout(r32ui, binding=0) uniform highp uimage2DArray img;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec3 p=ivec3(int(i%8u),int((i/8u)%8u),int(i/64u)); imageStore(img, p, uvec4(i*2246822519u+7u)); memoryBarrierImage(); data[8u+i]=imageLoad(img, p).r; } }
