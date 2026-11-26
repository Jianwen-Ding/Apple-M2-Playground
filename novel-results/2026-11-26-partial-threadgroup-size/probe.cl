kernel void probe(global uint* slots, global uint* counter) {
  uint s = atomic_add(counter, 1u);
  global uint* r = slots + 8 * s;
  r[0] = get_global_id(0); r[1] = get_global_id(1);
  r[2] = get_local_id(0); r[3] = get_local_id(1);
  r[4] = get_group_id(0); r[5] = get_group_id(1);
  r[6] = get_local_size(0); r[7] = get_local_size(1);
}
