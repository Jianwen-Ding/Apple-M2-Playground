	.file	"llvm-link"
	.text
	.globl	stack_k                         // -- Begin function stack_k
	.p2align	1
	.type	stack_k,@function
stack_k:                                // @stack_k
	// uniform registers: 12 x 16-bit (threadgroups_per_grid at u3)
	// general purpose registers: 7 x 32-bit (up to 1024 threads per threadgroup)
	// threadgroup memory: 0 bytes
	// stack size: 1072 bytes
// %bb.0:
	mov_imm r0l, 0
	stack_adjust 268
	get_sr r1, sr48 (thread_position_in_threadgroup.x)
	get_sr r2, sr0 (threadgroup_position_in_grid.x)
	get_sr r3, sr4 (threads_per_threadgroup.x)
	imadd r1, r2, r3, r1
	if_icmp r0l, ult, r1, u2, 1
	jmp_exec_none .LBB0_4
// %bb.1:
	mov_imm r2, 0
	iadd r3, r1, 1
	if_fcmp r0l, eq, 0.0, 0.0, 1
	mov_imm r4, -1
	mov_imm r5, 0
	bitop 0101, r6, r2, 0
.LBB0_2:                                // =>This Inner Loop Header: Depth=1
	stack_store 0, i32, x, r5, r6
	iadd r4, r4, 1
	iadd r6, r6, 4
	iadd r5, r5, r3
	while_icmp r0l, ulte, r4, 254, 1
	jmp_exec_any .LBB0_2
// %bb.3:
	pop_exec r0l, 1
	imadd r3, r1, 148, 0
	mov_imm r4, 1020
	and	r3, r3, r4
	iadd r2, r2, r3
	stack_load 0, i32, x, r2, r2
	wait 0
	device_store 0, i32, x, r2, u0_u1, r1, unsigned
.LBB0_4:
	pop_exec r0l, 1
	stop
	trap
	trap
	trap
	trap
	trap
	trap
	trap
	trap
.Lfunc_end0:
	.size	stack_k, .Lfunc_end0-stack_k
                                        // -- End function
	.section	".note.GNU-stack","",@progbits
	.section	.agx.kernels,"",@progbits
	.p2align	2, 0x0
	.long	72
	.long	1
	.long	7
	.ascii	"stack_k"
	.zero	1
	.long	12
	.long	6
	.long	4294967295
	.long	7
	.long	0
	.long	1072
	.long	2
	.long	0
	.long	8
	.long	0
	.long	0
	.long	4
	.long	4
