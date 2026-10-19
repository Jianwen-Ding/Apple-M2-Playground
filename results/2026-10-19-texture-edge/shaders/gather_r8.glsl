#version 320 es
precision highp int;
precision highp float;
precision highp sampler2D;
precision highp image2D;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
layout(binding=0) uniform highp sampler2D tex;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ vec2 uv = (i < 32u ? vec2(float(i)+0.5, 5.0) : vec2(5.0, float(i-32u)+0.5))/16.0; vec4 g=textureGather(tex, uv); data[8u+i]=uint(g.r*255.0+0.5)+uint(g.g*255.0+0.5)*256u+uint(g.b*255.0+0.5)*65536u+uint(g.a*255.0+0.5)*16777216u; } }
