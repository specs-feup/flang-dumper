integer function adjust(value, delta) result(answer)
  integer, intent(in) :: value
  integer, optional, intent(in) :: delta
  if (present(delta)) then
    answer = value + delta
  else
    answer = value
  end if
end function adjust
