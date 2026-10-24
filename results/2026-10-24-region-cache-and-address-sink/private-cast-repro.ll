define agx_kernel void @constant_private_cast(ptr addrspace(1) %out) {
  store i32 ptrtoint (ptr addrspace(5) addrspacecast (ptr inttoptr (i64 -1408 to ptr) to ptr addrspace(5)) to i32), ptr addrspace(1) %out
  ret void
}
