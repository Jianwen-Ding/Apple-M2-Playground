#version 320 es
precision highp int;
precision highp float;
precision highp sampler2D;
precision highp image2D;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
precision highp usampler2D;
layout(binding=0) uniform highp usampler2D tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ ivec2 p = i < 32u ? ivec2(int(i)-8, 5) : ivec2(5, int(i-32u)-8); data[8u+i]=texelFetch(tex, p, 0).r; } }
