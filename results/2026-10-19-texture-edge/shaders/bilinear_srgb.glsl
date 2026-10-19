#version 320 es
precision highp int;
precision highp float;
precision highp sampler2D;
precision highp image2D;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
layout(binding=0) uniform highp sampler2D tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ float fx=float(i%256u)/256.0; float cx=float(i/256u); vec2 uv=(vec2(cx+0.5+fx, 3.5+0.375))/16.0; data[8u+i]=floatBitsToUint(textureLod(tex, uv, 0.0).r); } }
