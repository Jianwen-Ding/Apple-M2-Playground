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
layout(binding=0) uniform highp samplerCube tex;
const vec3 D[65] = vec3[](vec3(1.0,0.1,1.0),vec3(1.0,0.1,0.96875),vec3(1.0,0.1,0.9375),vec3(1.0,0.1,0.90625),vec3(1.0,0.1,0.875),vec3(1.0,0.1,0.84375),vec3(1.0,0.1,0.8125),vec3(1.0,0.1,0.78125),vec3(1.0,0.1,0.75),vec3(1.0,0.1,0.71875),vec3(1.0,0.1,0.6875),vec3(1.0,0.1,0.65625),vec3(1.0,0.1,0.625),vec3(1.0,0.1,0.59375),vec3(1.0,0.1,0.5625),vec3(1.0,0.1,0.53125),vec3(1.0,0.1,0.5),vec3(1.0,0.1,0.46875),vec3(1.0,0.1,0.4375),vec3(1.0,0.1,0.40625),vec3(1.0,0.1,0.375),vec3(1.0,0.1,0.34375),vec3(1.0,0.1,0.3125),vec3(1.0,0.1,0.28125),vec3(1.0,0.1,0.25),vec3(1.0,0.1,0.21875),vec3(1.0,0.1,0.1875),vec3(1.0,0.1,0.15625),vec3(1.0,0.1,0.125),vec3(1.0,0.1,0.09375),vec3(1.0,0.1,0.0625),vec3(1.0,0.1,0.03125),vec3(1.0,0.1,0.0),vec3(0.96875,0.1,1.0),vec3(0.9375,0.1,1.0),vec3(0.90625,0.1,1.0),vec3(0.875,0.1,1.0),vec3(0.84375,0.1,1.0),vec3(0.8125,0.1,1.0),vec3(0.78125,0.1,1.0),vec3(0.75,0.1,1.0),vec3(0.71875,0.1,1.0),vec3(0.6875,0.1,1.0),vec3(0.65625,0.1,1.0),vec3(0.625,0.1,1.0),vec3(0.59375,0.1,1.0),vec3(0.5625,0.1,1.0),vec3(0.53125,0.1,1.0),vec3(0.5,0.1,1.0),vec3(0.46875,0.1,1.0),vec3(0.4375,0.1,1.0),vec3(0.40625,0.1,1.0),vec3(0.375,0.1,1.0),vec3(0.34375,0.1,1.0),vec3(0.3125,0.1,1.0),vec3(0.28125,0.1,1.0),vec3(0.25,0.1,1.0),vec3(0.21875,0.1,1.0),vec3(0.1875,0.1,1.0),vec3(0.15625,0.1,1.0),vec3(0.125,0.1,1.0),vec3(0.09375,0.1,1.0),vec3(0.0625,0.1,1.0),vec3(0.03125,0.1,1.0),vec3(0.0,0.1,1.0));
void main(){ uint i=gl_GlobalInvocationID.x; if(i<count){ data[8u+i]=floatBitsToUint(textureLod(tex, D[i], 0.0).r); } }
