#version 320 es
precision highp int;
precision highp float;
precision highp sampler2D;
precision highp image2D;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
layout(binding=0) uniform highp sampler2D tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ vec2 dx = vec2((1.0+float(i))/16.0, 0.0); vec2 dy = vec2(0.0, (1.0+float(i))/16.0); data[8u+i]=floatBitsToUint(textureGrad(tex, vec2(8.5/16.0, 8.5/16.0), dx, dy).r); } }
