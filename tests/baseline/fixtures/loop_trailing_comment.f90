program fixture
  integer :: i, total
  total = 0
  do i = 1, 3
    total = total + i ! trailing comment
  end do
  print *, total
end program fixture
