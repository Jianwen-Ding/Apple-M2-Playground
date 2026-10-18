#version 320 es
precision highp int;
precision highp float;
precision highp sampler2D;
precision highp image2D;
layout(local_size_x=32, local_size_y=1, local_size_z=1) in;
layout(std430, binding=0) buffer Output { uint data[]; };
uniform uint count;
layout(rgba8, binding=0) readonly uniform highp image2D img;
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count && i<256u){ ivec2 p=ivec2(int(i%16u),int(i/16u)); vec4 v=imageLoad(img, p); data[8u+i]=floatBitsToUint(v.r); data[8u+256u+i]=floatBitsToUint(v.g); } }
