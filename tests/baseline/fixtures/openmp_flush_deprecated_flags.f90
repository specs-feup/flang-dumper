program flags_probe
  integer :: x
  !$omp flush seq_cst(x)
  !$omp flush(x) seq_cst
end program flags_probe
