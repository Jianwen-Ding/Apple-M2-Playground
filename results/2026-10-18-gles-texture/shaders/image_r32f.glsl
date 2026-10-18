#version 320 es
precision highp int;
precision highp float;
precision highp sampler2D;
precision highp image2D;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
layout(r32f, binding=0) uniform highp image2D img;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec2 p=ivec2(int(i%32u),int(i/32u)); imageStore(img, p, vec4(uintBitsToFloat(0x3f800000u + i*977u), 0.0, 0.0, 0.0)); memoryBarrierImage(); data[8u+i]=floatBitsToUint(imageLoad(img, p).r); } }
